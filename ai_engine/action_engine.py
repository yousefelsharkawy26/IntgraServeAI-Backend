# ai_engine/action_engine.py

import os
import sys
import tempfile
import importlib
import json
import logging
import requests
from typing import List, Dict, Any, Type, Optional
from pydantic import create_model, Field, BaseModel, ValidationError, model_validator
from jsonpath_ng import parse as jsonpath_parse
from langchain_core.tools import StructuredTool

from .config import AgentConfiguration, ActionDefinition, ResponseConfig
from .vector_search import generate_embedding, get_vector_driver
from .exceptions import *

# P1.1: Use module-level logger only; never call logging.basicConfig()
logger = logging.getLogger(__name__)


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

    # P1.14: Replace brittle string-matching with stable error-type inspection
    def _handle_validation_error(self, e: ValidationError, context_msg: str):
        for error in e.errors():
            ctx = error.get("ctx", {})
            original_exc = ctx.get("error")
            if original_exc and isinstance(original_exc, ActionEngineException):
                raise original_exc

            error_type = error.get("type", "")
            loc = error.get("loc", [])
            field_path = ".".join(str(x) for x in loc) if loc else "unknown"

            if error_type == "missing":
                raise MissingField(f"Missing required field: {field_path}")
            elif error_type in ("value_error", "literal_error"):
                msg = error.get("msg", "")
                raise InvalidActionStructure(f"Invalid value at {field_path}: {msg}")

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

    # P1.15: Add TypeError guard for non-dict action items
    def _parse_actions_list(self, actions_list: List[Dict]) -> List[ActionDefinition]:
        actions = []
        for index, item in enumerate(actions_list):
            try:
                if not isinstance(item, dict):
                    raise InvalidActionStructure(
                        f"Action at index {index} must be a dict, got {type(item).__name__}"
                    )
                actions.append(ActionDefinition(**item))
            except ValidationError as e:
                self._handle_validation_error(e, f"Error in Action at index {index}")
            except ActionEngineException as e:
                raise e
        return actions

    # P1.2: Lazy gRPC imports — only import grpc tooling when RPC is actually used
    def _compile_and_load_proto(self, proto_path: str):
        from grpc_tools import protoc

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

    # P1.3: Refactor to use immutable model_copy instead of in-place mutation
    def _apply_global_defaults(self):
        defaults = self.agent_config.global_defaults
        for action in self.actions:
            if not action.active:
                continue

            if action.type == "api_request" and defaults.api_request and action.execution_config:
                config = action.execution_config
                api_def = defaults.api_request

                # Compute merged headers (new dict, no mutation)
                merged_headers = api_def.headers.copy()
                if config.headers:
                    merged_headers.update(config.headers)

                # Compute protocol and timeout
                new_protocol = config.protocol or api_def.protocol
                new_timeout = config.timeout if config.timeout is not None else api_def.timeout

                # P1.4: Fix URL construction — all relative URLs resolve against base_url + protocol
                new_url = config.url
                if new_url and not new_url.startswith("http"):
                    if api_def.base_url:
                        clean_base = api_def.base_url.rstrip("/")
                        if not clean_base.startswith("http"):
                            clean_base = f"{new_protocol}://{clean_base}"
                        clean_path = new_url.lstrip("/")
                        new_url = f"{clean_base}/{clean_path}"
                    else:
                        new_url = f"{new_protocol}://{new_url}"

                # Create immutable copy with merged values
                action.execution_config = config.model_copy(update={
                    "headers": merged_headers,
                    "protocol": new_protocol,
                    "timeout": new_timeout,
                    "url": new_url,
                })

                self._apply_response_fallback(action, api_def.on_error)

            elif action.type == "vector_query" and defaults.vector_query and action.execution_config:
                config = action.execution_config
                vec_def = defaults.vector_query

                new_connector = config.connector or vec_def.connector
                new_connection_string = config.connection_string or vec_def.connection_string
                new_embedding_config = config.embedding_config or vec_def.embedding_config

                action.execution_config = config.model_copy(update={
                    "connector": new_connector,
                    "connection_string": new_connection_string,
                    "embedding_config": new_embedding_config,
                })

                self._apply_response_fallback(action, vec_def.on_error)

            elif action.type == "rpc_request" and defaults.rpc_request and action.execution_config:
                self._apply_response_fallback(action, defaults.rpc_request.on_error)

            elif action.type == "internal" and defaults.internal:
                self._apply_response_fallback(action, defaults.internal.on_error)

    # P1.7: Fix on_error fallback — explicitly check is None instead of falsy
    def _apply_response_fallback(self, action: ActionDefinition, fallback_error: str):
        if not action.response_config:
            from .config import ResponseConfig
            action.response_config = ResponseConfig(mode="json", on_error=fallback_error)
        elif action.response_config.on_error is None:
            action.response_config.on_error = fallback_error

    # P1.6: Add runtime enum validation via model_validator on the dynamic schema
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

        # Runtime enum validator for the dynamic model
        def _validate_enums(cls, values):
            for p_name, p in parameters.items():
                if p.enum and p_name in values and values[p_name] is not None:
                    if values[p_name] not in p.enum:
                        raise ValueError(f"Field '{p_name}' must be one of: {p.enum}")
            return values

        return create_model(
            "DynamicToolArgs",
            __validators__={"_check_enums": model_validator(mode="before")(_validate_enums)},
            **fields,
        )

    # P1.12: Unified confirmation gate — single source of truth for confirmation logic
    def _gate_confirmation(self, action: ActionDefinition, kwargs: dict) -> None:
        """Unified confirmation gate.

        Raises:
            ActionRequiresConfirmationError: If the action requires confirmation and
                has not been pre-approved.
        """
        if not action.requires_confirmation:
            return

        logger.warning(f"ACTION PAUSED: {action.name} requires user confirmation. Params: {kwargs}")
        raise ActionRequiresConfirmationError(
            f"PAUSE_FOR_HUMAN: {action.name}", action.name, kwargs
        )

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

        # P1.10: Verify no path placeholders remain unresolved
        if "{{" in url and "}}" in url:
            raise PathParamNotFound(f"URL contains unresolved path parameters: {url}")

        # P1.11: Filter out None values from query and body params
        query_params = {
            k: v for k, v in kwargs.items()
            if action.parameters[k].param_type == "query" and v is not None
        }

        body_params = {
            k: v for k, v in kwargs.items()
            if action.parameters[k].param_type == "body" and v is not None
        }

        if config.method == "GET" and body_params:
            raise BodyParamOnGetRequest("Cannot send body params on GET")

        logger.info(f"Executing HTTP {config.method} {url}")

        # P0.7: Safe timeout fallback
        timeout_seconds = (config.timeout or 10000) / 1000

        # P1.5: Wire HTTP auth field into requests.request
        request_auth = None
        if config.auth:
            if "username" in config.auth and "password" in config.auth:
                request_auth = (config.auth["username"], config.auth["password"])
            # Future: support bearer token, digest auth, etc.

        try:
            resp = requests.request(
                method=config.method,
                url=url,
                headers=config.headers,
                params=query_params,
                json=body_params if body_params else None,
                timeout=timeout_seconds,
                auth=request_auth,
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

    # P1.2: Lazy gRPC imports — only loaded when RPC action is executed
    def _execute_rpc(self, action: ActionDefinition, **kwargs):
        import grpc
        from google.protobuf.json_format import MessageToDict

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

        # P0.7: Safe timeout fallback
        timeout_seconds = (config.timeout or 10000) / 1000

        # P1.6: Channel created inside try to ensure close on unexpected errors
        channel = None
        try:
            channel = grpc.insecure_channel(config.host)
            stub_class = getattr(pb2_grpc, stub_class_name)
            stub = stub_class(channel)
            rpc_method = getattr(stub, config.method)

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
            if channel is not None:
                channel.close()

        response_dict = MessageToDict(response_obj, preserving_proto_field_name=True)

        return self._parse_response(response_dict, action.response_config)

    def _parse_response(self, data: Any, config: ResponseConfig) -> str:
        if not config:
            return str(data)

        values = {}

        # P1.13: Functionalize ResponseConfig.mode — only json mode performs extraction
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
                    # P1.12: Unified confirmation gate
                    self._gate_confirmation(act, kwargs)

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

    # P1.8: Harden execute_action_directly with active-check, schema validation, and confirmation gating
    def execute_action_directly(
        self,
        action_name: str,
        kwargs: dict,
        skip_confirmation: bool = False
    ) -> str:
        act = next((a for a in self.actions if a.name == action_name), None)
        if not act:
            raise ValueError(f"Action '{action_name}' not found.")

        if not act.active:
            raise ValueError(f"Action '{action_name}' is not active.")

        # Validate parameters against the Pydantic schema
        if act.parameters:
            ArgsSchema = self._create_args_schema(act.parameters)
            try:
                validated = ArgsSchema(**kwargs)
                kwargs = validated.model_dump()
            except ValidationError as e:
                raise InvalidActionStructure(
                    f"Parameter validation failed for '{action_name}': {e}"
                )

        # P1.12: Honor confirmation requirements unless explicitly skipped
        if not skip_confirmation:
            self._gate_confirmation(act, kwargs)

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