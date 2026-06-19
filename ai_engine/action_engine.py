# ai_engine/action_engine.py

import os
import sys
import tempfile
import importlib
import grpc
from grpc_tools import protoc
from google.protobuf.json_format import MessageToDict
import json
import logging
import requests
from typing import List, Dict, Any, Type, Optional
from pydantic import create_model, Field, BaseModel, ValidationError
from jsonpath_ng import parse as jsonpath_parse
from langchain_core.tools import StructuredTool

from .config import AgentConfiguration, ActionDefinition, ResponseConfig
from .vector_search import generate_embedding, get_vector_driver
from .exceptions import *

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ActionEngine")


class ActionEngine:
    def __init__(self, agent_config_path: str, actions_config_path: str = None, actions_list: list = None):
        # BUGFIX: use `is None` so empty list [] is accepted
        if actions_config_path is None and actions_list is None:
            raise ValueError("Either actions_config_path or actions_list must be provided")

        self.agent_config: AgentConfiguration = self._load_agent_config(agent_config_path)
        
        if actions_list is not None:
            if not isinstance(actions_list, list):
                raise InvalidActionStructure("Actions list must be a list of objects")
            self.actions: List[ActionDefinition] = self._parse_actions_list(actions_list)
        else:
            self.actions: List[ActionDefinition] = self._load_actions_config(actions_config_path)

        # P0.8: Validate action name uniqueness
        seen_names = set()
        for action in self.actions:
            if action.name in seen_names:
                raise InvalidActionStructure(
                    f"Duplicate action name '{action.name}' detected. Action names must be unique."
                )
            seen_names.add(action.name)

        self._grpc_module_cache = {} 
        self._apply_global_defaults()

    def _handle_validation_error(self, e: ValidationError, context_msg: str):
        for error in e.errors():
            ctx = error.get("ctx", {})
            original_exc = ctx.get("error")
            if original_exc and isinstance(original_exc, ActionEngineException):
                raise original_exc

            msg = error.get("msg", "")
            if "MissingField" in msg:
                raise MissingField(msg)
            if "InvalidActionStructure" in msg:
                raise InvalidActionStructure(msg)

        raise InvalidActionStructure(f"{context_msg}: {str(e)}")

    def _load_agent_config(self, path: str) -> AgentConfiguration:
        try:
            with open(path, "r") as f:
                data = json.load(f)
                return AgentConfiguration(**data)
        except FileNotFoundError:
            raise ParsingException(f"Agent config file not found at {path}")
        except json.JSONDecodeError as e:
            raise ParsingException(f"Invalid JSON in agent config: {e}")
        except ActionEngineException as e:
            raise e
        except ValidationError as e:
            self._handle_validation_error(e, "Agent Config Validation Failed")
        except Exception as e:
            raise ParsingException(f"Unexpected error loading agent config: {e}")

    def _load_actions_config(self, path: str) -> List[ActionDefinition]:
        try:
            with open(path, "r") as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise InvalidActionStructure("Actions config must be a list of objects")

            return self._parse_actions_list(data)

        except FileNotFoundError:
            raise ParsingException(f"Actions config file not found at {path}")
        except json.JSONDecodeError as e:
            raise ParsingException(f"Invalid JSON in actions config: {e}")
        except ActionEngineException as e:
            raise e
        except Exception as e:
            raise ParsingException(f"Failed to load actions config: {e}")

    def _parse_actions_list(self, actions_list: List[Dict]) -> List[ActionDefinition]:
        actions = []
        for index, item in enumerate(actions_list):
            try:
                actions.append(ActionDefinition(**item))
            except ValidationError as e:
                self._handle_validation_error(e, f"Error in Action at index {index}")
            except ActionEngineException as e:
                raise e
        return actions
        
    def _compile_and_load_proto(self, proto_path: str):
        abs_proto_path = os.path.abspath(proto_path)
        
        if not os.path.exists(abs_proto_path):
            raise ProtoNotFound(f"Proto file not found: {abs_proto_path}")

        proto_dir = os.path.dirname(abs_proto_path)
        proto_file = os.path.basename(abs_proto_path)
        
        out_dir = tempfile.mkdtemp()
        
        protoc_args =[
            'grpc_tools.protoc',
            f'-I{proto_dir}',
            f'--python_out={out_dir}',
            f'--grpc_python_out={out_dir}',
            abs_proto_path
        ]
        
        if protoc.main(protoc_args) != 0:
            raise ExecutionException(f"Failed to compile proto file: {proto_file}")

        sys.path.insert(0, out_dir)
        try:
            pb2_name = proto_file.replace('.proto', '_pb2')
            pb2_grpc_name = proto_file.replace('.proto', '_pb2_grpc')
            
            pb2 = importlib.import_module(pb2_name)
            pb2_grpc = importlib.import_module(pb2_grpc_name)
        finally:
            sys.path.remove(out_dir)
            
        return pb2, pb2_grpc

    def _apply_global_defaults(self):
        defaults = self.agent_config.global_defaults
        for action in self.actions:
            if not action.active:
                continue

            if action.type == "api_request" and defaults.api_request:
                config = action.execution_config
                api_def = defaults.api_request

                merged_headers = api_def.headers.copy()
                if config.headers:
                    merged_headers.update(config.headers)
                config.headers = merged_headers

                if not config.protocol:
                    config.protocol = api_def.protocol
                
                # P0.7: Use sentinel None instead of magic number 5000
                if config.timeout is None:
                    config.timeout = api_def.timeout

                if config.url and config.url.startswith("/") and api_def.base_url:
                    clean_base = api_def.base_url.rstrip("/")
                    clean_path = config.url.lstrip("/")
                    if not clean_base.startswith("http"):
                        clean_base = f"{config.protocol}://{clean_base}"
                    config.url = f"{clean_base}/{clean_path}"

                elif config.url and not config.url.startswith("http"):
                    config.url = f"{config.protocol}://{config.url}"

                self._apply_response_fallback(action, api_def.on_error)

            elif action.type == "vector_query" and defaults.vector_query:
                config = action.execution_config
                vec_def = defaults.vector_query

                if not config.connector:
                    config.connector = vec_def.connector
                if not config.connection_string:
                    config.connection_string = vec_def.connection_string
                if not config.embedding_config:
                    config.embedding_config = vec_def.embedding_config

                self._apply_response_fallback(action, vec_def.on_error)

            elif action.type == "rpc_request" and defaults.rpc_request:
                self._apply_response_fallback(action, defaults.rpc_request.on_error)

            elif action.type == "internal" and defaults.internal:
                self._apply_response_fallback(action, defaults.internal.on_error)

    def _apply_response_fallback(self, action: ActionDefinition, fallback_error: str):
        if not action.response_config:
            from .config import ResponseConfig
            action.response_config = ResponseConfig(mode="json", on_error=fallback_error)
        elif action.response_config.on_error is None:
            action.response_config.on_error = fallback_error

    def _create_args_schema(self, parameters: Dict[str, Any]) -> Type[BaseModel]:
        fields = {}
        for name, param in parameters.items():
            type_mapping = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict
            }
            py_type = type_mapping.get(param.type, str)

            field_args = {"description": param.description}

            if param.enum:
                field_args["json_schema_extra"] = {"enum": param.enum}
                enum_str = ", ".join([f"'{str(e)}'" for e in param.enum])
                field_args["description"] += f" (Must be one of: {enum_str})"

            if param.required:
                default_val = ...
            else:
                default_val = param.default
                py_type = Optional[py_type]

            fields[name] = (py_type, Field(default=default_val, **field_args))

        return create_model("DynamicToolArgs", **fields)

    def _request_confirmation(self, action_name: str, params: Dict, is_approved: Optional[bool] = None) -> bool:
        if is_approved is True:
            logger.info(f"Confirmation pre-approved for {action_name}.")
            return True
        elif is_approved is False:
            raise UserDeniedConfirmation(f"User denied confirmation for {action_name}")
            
        logger.warning(f"ACTION PAUSED: {action_name} requires user confirmation. Params: {params}")
        raise ActionRequiresConfirmationError(f"PAUSE_FOR_HUMAN: {action_name}", action_name, params)
    
    def _execute_api_request(self, action: ActionDefinition, **kwargs):
        config = action.execution_config
        url = config.url

        path_params = {
            k: v for k, v in kwargs.items() if action.parameters[k].param_type == "path"
        }
        for k, v in path_params.items():
            if f"{{{k}}}" not in url:
                raise PathParamNotFound(f"Path parameter {{{k}}} missing in URL {url}")
            url = url.replace(f"{{{k}}}", str(v))

        query_params = {
            k: v for k, v in kwargs.items()
            if action.parameters[k].param_type == "query"
        }

        body_params = {
            k: v for k, v in kwargs.items() if action.parameters[k].param_type == "body"
        }

        if config.method == "GET" and body_params:
            raise BodyParamOnGetRequest("Cannot send body params on GET")

        logger.info(f"Executing HTTP {config.method} {url}")

        # P0.7: Safe timeout fallback if somehow not set
        timeout_seconds = (config.timeout or 10000) / 1000

        try:
            resp = requests.request(
                method=config.method,
                url=url,
                headers=config.headers,
                params=query_params,
                json=body_params if body_params else None,
                timeout=timeout_seconds,
            )
            try:
                data = resp.json()
            except:
                data = resp.text

            if resp.status_code >= 400:
                logger.error(f"API returned {resp.status_code}: {data}")
                if action.response_config and action.response_config.on_error:
                    return action.response_config.on_error.replace("{{error}}", str(data))
                return f"Error {resp.status_code}: {str(data)}"

            return self._parse_response(data, action.response_config)

        except Exception as e:
            logger.exception("API Request Failed")
            if action.response_config and action.response_config.on_error:
                return action.response_config.on_error.replace("{{error}}", str(e))
            return str(e)

    def _execute_internal(self, action: ActionDefinition, **kwargs):
        return (
            f"Internal Action '{action.name}' processed successfully. Params: {kwargs}"
        )

    def _execute_vector(self, action: ActionDefinition, **kwargs):
        config = action.execution_config
        
        topic_key = next((k for k, v in action.parameters.items() if v.param_type == "vector"), None)
        if not topic_key or topic_key not in kwargs:
            raise VectorSearchError("Vector query requires a parameter with param_type='vector'.")
            
        topic_text = kwargs[topic_key]
        
        logger.info(f"Executing Vector Search for topic: '{topic_text}'")

        try:
            query_vector = generate_embedding(topic_text, config.embedding_config)
            driver = get_vector_driver(config.connector)
            search_results = driver.search(query_vector, config)
            
        except UnsupportedDatabaseDriver as e:
            logger.error(f"Configuration Error: {e}")
            raise
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            if action.response_config and action.response_config.on_error:
                return action.response_config.on_error.replace("{{error}}", str(e))
            return f"Vector Database Error: {str(e)}"

        return self._parse_response({"data": search_results}, action.response_config)

    def _execute_rpc(self, action: ActionDefinition, **kwargs):
        config = action.execution_config
        
        if config.proto_file not in self._grpc_module_cache:
            self._grpc_module_cache[config.proto_file] = self._compile_and_load_proto(config.proto_file)
            
        pb2, pb2_grpc = self._grpc_module_cache[config.proto_file]

        stub_class_name = f"{config.service}Stub"
        if not hasattr(pb2_grpc, stub_class_name):
            raise ServiceNotFound(f"Service '{config.service}' not found in {config.proto_file}")
            
        service_descriptor = pb2.DESCRIPTOR.services_by_name.get(config.service)
        if not service_descriptor:
            raise ServiceNotFound(f"Service Descriptor '{config.service}' not found.")

        method_descriptor = service_descriptor.methods_by_name.get(config.method)
        if not method_descriptor:
            raise MethodNotFound(f"Method '{config.method}' not found in service '{config.service}'")
            
        request_class = getattr(pb2, method_descriptor.input_type.name)

        message_params = {
            k: v for k, v in kwargs.items() 
            if action.parameters[k].param_type == "message_field"
        }
        
        try:
            request_obj = request_class(**message_params)
        except Exception as e:
            raise ExecutionException(f"Failed to construct gRPC request message: {str(e)}")

        metadata = None
        if config.headers:
            metadata = tuple((k.lower(), str(v)) for k, v in config.headers.items())

        logger.info(f"Executing gRPC {config.host}/{config.service}/{config.method}")

        # P0.7: Safe timeout fallback if somehow not set
        timeout_seconds = (config.timeout or 10000) / 1000

        channel = grpc.insecure_channel(config.host)
        stub_class = getattr(pb2_grpc, stub_class_name)
        stub = stub_class(channel)
        rpc_method = getattr(stub, config.method)

        try:
            response_obj = rpc_method(
                request_obj, 
                metadata=metadata, 
                timeout=timeout_seconds
            )
        except grpc.RpcError as e:
            logger.error(f"gRPC Error: Status {e.code()} - {e.details()}")
            if action.response_config and action.response_config.on_error:
                return action.response_config.on_error.replace("{{error}}", e.details())
            return f"gRPC Action Failed: {e.details()}"
        finally:
            channel.close()

        response_dict = MessageToDict(response_obj, preserving_proto_field_name=True)
        
        return self._parse_response(response_dict, action.response_config)

    def _parse_response(self, data: Any, config: ResponseConfig) -> str:
        if not config:
            return str(data)

        values = {}

        if config.mode == "json" and config.values:
            for key, val_def in config.values.items():
                try:
                    expr = jsonpath_parse(val_def.path)
                    matches = expr.find(data)
                    if matches:
                        values[key] = matches[0].value
                    else:
                        values[key] = "N/A"
                except Exception:
                    values[key] = "ErrorParsing"

        if config.template:
            result = config.template
            for k, v in values.items():
                result = result.replace(f"{{{{{k}}}}}", str(v))

            if "{{value}}" in result:
                result = result.replace(
                    "{{value}}",
                    str(data) if isinstance(data, str) else json.dumps(data),
                )

            return result

        return str(data)

    def build_tools(self) -> List[StructuredTool]:
        tools = []
        for action in self.actions:
            if not action.active:
                continue

            def make_runner(act: ActionDefinition):
                def runner(**kwargs):
                    if act.requires_confirmation:
                        confirmed = self._request_confirmation(act.name, kwargs)
                        if not confirmed:
                            raise UserDeniedConfirmation(
                                f"User denied confirmation for {act.name}"
                            )

                    if act.type == "api_request":
                        return self._execute_api_request(act, **kwargs)
                    elif act.type == "internal":
                        return self._execute_internal(act, **kwargs)
                    elif act.type == "vector_query":
                        return self._execute_vector(act, **kwargs)
                    elif act.type == "rpc_request":
                        return self._execute_rpc(act, **kwargs)
                    else:
                        return "Action type not implemented in engine."

                return runner

            args_schema = self._create_args_schema(action.parameters)

            tool = StructuredTool.from_function(
                func=make_runner(action),
                name=action.name,
                description=action.description,
                args_schema=args_schema,
            )
            tools.append(tool)

        return tools

    def get_system_prompt(self) -> str:
        ctx = self.agent_config.system_context
        if self.agent_config.llm_config:
            tmpl = getattr(self.agent_config.llm_config, "system_prompt_template", "")
            prompt = (
                tmpl.replace("{{title}}", ctx.title)
                .replace("{{description}}", ctx.description)
                .replace("{{tone}}", ctx.tone)
            )
            return prompt
        return f"System: {ctx.title}. {ctx.description}"

    def execute_action_directly(self, action_name: str, kwargs: dict) -> str:
        act = next((a for a in self.actions if a.name == action_name), None)
        if not act:
            raise ValueError(f"Action '{action_name}' not found.")

        try:
            if act.type == "api_request":
                return self._execute_api_request(act, **kwargs)
            elif act.type == "internal":
                return self._execute_internal(act, **kwargs)
            elif act.type == "vector_query":
                return self._execute_vector(act, **kwargs)
            elif act.type == "rpc_request":
                return self._execute_rpc(act, **kwargs)
            else:
                return "Action type not implemented in engine."
        except Exception as e:
            logger.error(f"Manual execution failed: {str(e)}")
            return f"Action Failed: {str(e)}"