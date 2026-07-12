import os
import sys
import socket
import asyncio
import tempfile
import importlib
import json
import re
import hashlib
import logging
import httpx
import grpc
from typing import List, Dict, Any, Type, Optional
from pydantic import create_model, Field, BaseModel, ValidationError, model_validator
from jsonpath_ng import parse as jsonpath_parse
from langchain_core.tools import StructuredTool

import ipaddress
from urllib.parse import urlparse, urlencode
from urllib import request as urllib_request
from urllib.error import HTTPError as UrllibHTTPError, URLError

from .config import AgentConfiguration, ActionDefinition, ResponseConfig, EmbeddingConfig
from .vector_search import generate_embedding, get_vector_driver
from core.config import BASE_DIR
from utils.exceptions import (
    ActionEngineException, MissingField, InvalidActionStructure, ProtoNotFound, MethodNotFound, ServiceNotFound,
    PathParamNotFound, BodyParamOnGetRequest, ActionRequiresConfirmationError,
    ParsingException, VectorSearchError, ExecutionException, EmbeddingGenerationError,
    UnsupportedDatabaseDriver, ActionNotFound, ActionNotActive, CorrelationIdAdapter, SSRFVulnerabilityError
)

logger = CorrelationIdAdapter(logging.getLogger(__name__))


class ActionEngine:
    ALLOWED_PROTO_DIR: str = os.path.abspath(BASE_DIR / "protos")

    def __init__(self, agent_config_path: str, actions_list: list):
        self.agent_config: AgentConfiguration = self._load_agent_config(agent_config_path)
        if not isinstance(actions_list, list):
            raise InvalidActionStructure("Actions list must be a list of objects")
        self.actions: List[ActionDefinition] = self._parse_actions_list(actions_list)

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

            error_type = error.get("type", "")
            loc = error.get("loc", [])
            field_path = ".".join(str(x) for x in loc) if loc else "unknown"
            
            if error_type == "missing":
                raise MissingField(f"Missing required field: {field_path}")
            elif error_type in ("value_error", "literal_error"):
                msg = error.get("msg", "")
                raise InvalidActionStructure(f"Invalid value at {field_path}: {msg}")

        raise InvalidActionStructure(f"{context_msg}: {str(e)}")
    
    def _validate_url_safety(self, url: str) -> None:
        """Validates URLs to prevent Server-Side Request Forgery (SSRF) via DNS rebinding."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise SSRFVulnerabilityError(f"Unsupported URL scheme: {parsed.scheme}")

        hostname = parsed.hostname
        if not hostname:
            raise SSRFVulnerabilityError("Invalid URL: No hostname provided.")
        
        defaults = self.agent_config.global_defaults.api_request
        allowed_hosts = set(h.lower() for h in defaults.allowed_hostnames)

        # Block obvious local/private hostnames unless explicitly bypassed
        forbidden_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        if (hostname.lower() not in allowed_hosts) and (hostname.lower() in forbidden_hosts):
            raise SSRFVulnerabilityError(f"Access to internal hostname '{hostname}' is forbidden.")

        # Resolve the hostname to real IPs and validate against private/loopback ranges
        # This catches DNS rebinding where a hostname initially resolves to a public IP
        # but later resolves to 127.0.0.1 or a private IP.
        try:
            addr_info = socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
            for _, _, _, _, sockaddr in addr_info:
                resolved_ip = sockaddr[0]
                ip = ipaddress.ip_address(resolved_ip)
                if (hostname.lower() not in allowed_hosts) and (ip.is_private or ip.is_loopback):
                    raise SSRFVulnerabilityError(
                        f"Access to private IP '{resolved_ip}' resolved from hostname '{hostname}' is forbidden."
                    )
        except socket.gaierror as e:
            raise SSRFVulnerabilityError(f"Unable to resolve hostname '{hostname}': {e}")

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

    def _parse_actions_list(self, actions_list: List[Dict]) -> List[ActionDefinition]:
        actions = []
        for index, item in enumerate(actions_list):
            try:
                if not isinstance(item, dict):
                    raise InvalidActionStructure(
                        f"Action at index {index} must be a dict, got {type(item).__name__}"
                    )
                
                # Create a copy to avoid mutating the original dict from the database
                action_data = item.copy()
                
                # Filter out internal DB fields before applying to the Pydantic model
                action_data.pop("_backend_id", None)
                
                actions.append(ActionDefinition(**action_data))
            except ValidationError as e:
                self._handle_validation_error(e, f"Error in Action at index {index}")
            except ActionEngineException as e:
                raise e
        return actions
    
    def _compile_and_load_proto(self, proto_path: str):
        from grpc_tools import protoc
        
        if ".." in proto_path:
            raise ProtoNotFound(f"Invalid proto path: {proto_path}")

        abs_proto_path = os.path.abspath(proto_path)
        abs_allowed_dir = os.path.abspath(self.ALLOWED_PROTO_DIR)

        try:
            common = os.path.commonpath([abs_proto_path, abs_allowed_dir])
        except ValueError:
            raise ProtoNotFound(f"Proto path outside allowed directory: {proto_path}")

        if common != abs_allowed_dir:
            raise ProtoNotFound(f"Proto path outside allowed directory: {proto_path}")

        if not os.path.exists(abs_proto_path):
            raise ProtoNotFound(f"Proto file not found: {abs_proto_path}")

        proto_dir = os.path.dirname(abs_proto_path)
        proto_file = os.path.basename(abs_proto_path)
        
        cache_key = hashlib.md5(f"{abs_proto_path}:{os.getpid()}".encode()).hexdigest()
        out_dir = os.path.join(tempfile.gettempdir(), "ai_engine_proto_cache", cache_key)
        os.makedirs(out_dir, exist_ok=True)
        
        pb2_name = proto_file.replace('.proto', '_pb2')
        pb2_grpc_name = proto_file.replace('.proto', '_pb2_grpc')
        pb2_path = os.path.join(out_dir, f"{pb2_name}.py")
        
        if not os.path.exists(pb2_path):
            protoc_args = [
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
            pb2 = importlib.import_module(pb2_name)
            pb2_grpc = importlib.import_module(pb2_grpc_name)
            return pb2, pb2_grpc
        except Exception:
            sys.modules.pop(pb2_name, None)
            sys.modules.pop(pb2_grpc_name, None)
            raise
        finally:
            sys.path.remove(out_dir)

    def _apply_global_defaults(self):
        defaults = self.agent_config.global_defaults
        for action in self.actions:
            if not action.active:
                continue

            if action.type == "api_request" and defaults.api_request and action.execution_config:
                config = action.execution_config
                api_def = defaults.api_request

                new_protocol = config.protocol or api_def.protocol
                new_timeout = config.timeout if config.timeout is not None else api_def.timeout

                new_url = config.url
                is_absolute_url = bool(new_url and new_url.startswith(("http://", "https://")))

                # Global API headers often contain auth for the project's primary API.
                # Do not leak/inherit those headers for absolute third-party URLs
                # such as https://fakestoreapi.com/products unless explicitly set
                # on the action itself.
                merged_headers = {} if is_absolute_url else api_def.headers.copy()
                if config.headers:
                    merged_headers.update(config.headers)

                if new_url and not is_absolute_url:
                    if api_def.base_url:
                        clean_base = api_def.base_url.rstrip("/")
                        if not clean_base.startswith("http"):
                            clean_base = f"{new_protocol}://{clean_base}"
                        clean_path = new_url.lstrip("/")
                        new_url = f"{clean_base}/{clean_path}"
                    else:
                        new_url = f"{new_protocol}://{new_url}"

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

                action_config = config.embedding_config.model_dump() if config.embedding_config else {}
                global_config = vec_def.embedding_config.model_dump() if vec_def.embedding_config else {}
                merged_embedding_config = {
                    **global_config,
                    **{k: v for k, v in action_config.items() if v is not None},
                }

                action.execution_config = config.model_copy(update={
                    "connector": config.connector or vec_def.connector,
                    "connection_string": config.connection_string or vec_def.connection_string,
                    "embedding_config": EmbeddingConfig(**merged_embedding_config) if merged_embedding_config else None,
                    "max_results": config.max_results if config.max_results is not None else vec_def.max_results,
                })

                self._apply_response_fallback(action, vec_def.on_error)

            elif action.type == "rpc_request" and defaults.rpc_request and action.execution_config:
                config = action.execution_config
                rpc_def = defaults.rpc_request

                merged_headers = rpc_def.headers.copy()
                if config.headers:
                    merged_headers.update(config.headers)

                action.execution_config = config.model_copy(update={
                    "protocol": config.protocol or rpc_def.protocol,
                    "headers": merged_headers,
                })

                self._apply_response_fallback(action, rpc_def.on_error)

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

    def _gate_confirmation(self, action: ActionDefinition, kwargs: dict) -> None:
        if not action.requires_confirmation:
            return
        
        logger.warning(f"ACTION PAUSED: {action.name} requires user confirmation. Params: {kwargs}")
        raise ActionRequiresConfirmationError(
            f"PAUSE_FOR_HUMAN: {action.name}", action.name, kwargs
        )

    def _sanitize_path_param(self, name: str, value: Any) -> str:
        """Sanitize a path parameter value to prevent path traversal and injection.
        
        Raises:
            ExecutionException: If the value contains dangerous characters.
        """
        str_value = str(value)
        dangerous_chars = ['..', '\x00', '?', '#', '\\']
        for char in dangerous_chars:
            if char in str_value:
                raise ExecutionException(
                    f"Path parameter '{name}' contains invalid characters: {value!r}"
                )
        return str_value

    def _format_action_error(self, action: ActionDefinition, err_msg: str) -> str:
        fallback = action.response_config.on_error if action.response_config else None
        if not fallback:
            return err_msg
        if "{{error}}" in fallback:
            return fallback.replace("{{error}}", err_msg)
        return f"{fallback}: {err_msg}"

    def _describe_request_error(self, exc: Exception) -> str:
        details = str(exc).strip() or repr(exc)
        cause = getattr(exc, "__cause__", None)
        if cause:
            cause_text = str(cause).strip() or repr(cause)
            details = f"{details}; cause={cause_text}"
        return details

    def _urllib_request_sync(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        query_params: Dict[str, Any],
        body_params: Dict[str, Any],
        timeout_seconds: float,
    ) -> Any:
        if query_params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(query_params, doseq=True)}"

        body = None
        request_headers = dict(headers)
        if body_params:
            body = json.dumps(body_params).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        req = urllib_request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except ValueError:
                    return raw
        except UrllibHTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise ExecutionException(f"Error {e.code}: {raw}") from e
        except URLError as e:
            raise ExecutionException(f"API Request Failed: {self._describe_request_error(e)}") from e

    async def _execute_api_request(self, action: ActionDefinition, **kwargs):
        config = action.execution_config
        url = config.url

        path_params = {
            k: v for k, v in kwargs.items() if action.parameters[k].param_type == "path"
        }
        for k, v in path_params.items():
            if f"{{{k}}}" not in url:
                raise PathParamNotFound(f"Path parameter {{{k}}} missing in URL {url}")
            sanitized = self._sanitize_path_param(k, v)
            url = url.replace(f"{{{k}}}", sanitized)

            if re.search(r'\{[^{}]+\}', url):
                raise PathParamNotFound(f"URL contains unresolved path parameters: {url}")

        self._validate_url_safety(url)

        # Sanitize query parameters to prevent injection
        query_params = {
            k: self._sanitize_path_param(k, v) for k, v in kwargs.items()
            if action.parameters[k].param_type == "query" and v is not None
        }

        body_params = {
            k: v for k, v in kwargs.items()
            if action.parameters[k].param_type == "body" and v is not None
        }

        if config.method == "GET" and body_params:
            raise BodyParamOnGetRequest("Cannot send body params on GET")

        logger.info(f"Executing Async HTTP {config.method} {url}")

        timeout_seconds = (config.timeout if config.timeout is not None else 10000) / 1000.0

        # Some public APIs/CDNs, including fakestoreapi.com, reject default
        # Python/httpx user agents with 403. Send a stable product UA unless
        # the action explicitly configured one.
        request_headers = dict(config.headers or {})
        if not any(header.lower() == "user-agent" for header in request_headers):
            request_headers["User-Agent"] = "IntegraServeAI/1.0 (+https://integraserve.ai)"
        if not any(header.lower() == "accept" for header in request_headers):
            request_headers["Accept"] = "application/json, text/plain;q=0.9, */*;q=0.8"

        request_auth = None
        if config.auth and "username" in config.auth and "password" in config.auth:
            request_auth = (config.auth["username"], config.auth["password"])

        req_kwargs = {
            "method": config.method,
            "url": url,
            "headers": request_headers,
            "params": query_params,
        }
        if body_params:
            req_kwargs["json"] = body_params

        async def send_with_httpx(client: httpx.AsyncClient) -> Any:
            resp = await client.request(**req_kwargs)
            try:
                response_data = resp.json()
            except ValueError:
                response_data = resp.text

            # Raise HTTPStatusError for 4xx/5xx to be handled below
            resp.raise_for_status()
            return response_data

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, auth=request_auth) as client:
                data = await send_with_httpx(client)
                return self._parse_response(data, action.response_config)

        except httpx.HTTPStatusError as e:
            logger.error(f"API returned {e.response.status_code}: {e.response.text}")
            err_str = str(data) if 'data' in locals() else e.response.text
            raise ExecutionException(self._format_action_error(action, f"HTTP {e.response.status_code}: {err_str}")) from e

        except httpx.ConnectError as e:
            logger.warning(
                "HTTPX connect failed for %s; retrying with IPv4-only transport. Error: %s",
                url,
                self._describe_request_error(e),
            )

            ipv4_error = None
            try:
                # Some networks break TLS over IPv6 for Cloudflare-backed APIs.
                # Binding the local address to 0.0.0.0 forces an IPv4 connection
                # while preserving normal hostname verification/SNI.
                transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
                async with httpx.AsyncClient(
                    timeout=timeout_seconds,
                    auth=request_auth,
                    transport=transport,
                ) as client:
                    data = await send_with_httpx(client)
                    return self._parse_response(data, action.response_config)
            except httpx.HTTPStatusError as status_error:
                logger.error(
                    "API returned %s during IPv4 retry: %s",
                    status_error.response.status_code,
                    status_error.response.text,
                )
                err_str = status_error.response.text
                raise ExecutionException(
                    self._format_action_error(
                        action,
                        f"HTTP {status_error.response.status_code}: {err_str}",
                    )
                ) from status_error
            except Exception as retry_error:
                ipv4_error = retry_error

            logger.warning(
                "HTTPX IPv4 retry failed for %s; retrying with urllib fallback. Error: %s",
                url,
                self._describe_request_error(ipv4_error),
            )
            try:
                data = await asyncio.to_thread(
                    self._urllib_request_sync,
                    config.method,
                    url,
                    request_headers,
                    query_params,
                    body_params,
                    timeout_seconds,
                )
                return self._parse_response(data, action.response_config)
            except Exception as fallback_error:
                err_msg = (
                    f"httpx={self._describe_request_error(e)}; "
                    f"httpx_ipv4={self._describe_request_error(ipv4_error)}; "
                    f"urllib_fallback={self._describe_request_error(fallback_error)}"
                )
                logger.error("API Request Failed after all fallbacks: %s", err_msg, exc_info=True)
                raise ExecutionException(self._format_action_error(action, err_msg)) from fallback_error

        except httpx.RequestError as e:
            err_msg = self._describe_request_error(e)
            logger.exception("API Request Failed: %s", err_msg)
            raise ExecutionException(self._format_action_error(action, err_msg)) from e


    async def _execute_internal(self, action: ActionDefinition, **kwargs):
        return f"Internal Action '{action.name}' processed successfully. Params: {kwargs}"

    async def _execute_vector(self, action: ActionDefinition, **kwargs):
        config = action.execution_config
        
        topic_key = next((k for k, v in action.parameters.items() if v.param_type == "vector"), None)
        if not topic_key or topic_key not in kwargs:
            raise VectorSearchError("Vector query requires a parameter with param_type='vector'.")
            
        topic_text = kwargs[topic_key]
        logger.info(f"Executing Vector Search for topic: '{topic_text}'")

        try:
            if config.embedding_config is not None:
                query_vector = generate_embedding(topic_text, config.embedding_config)
                driver = get_vector_driver(config.connector)
                search_results = await driver.search(query_vector, config)
                return self._parse_response({"data": search_results}, action.response_config)
            
        except (UnsupportedDatabaseDriver, EmbeddingGenerationError, VectorSearchError) as e:
            logger.error(f"Vector search exception: {e}")
            raise
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            if action.response_config and action.response_config.on_error:
                return action.response_config.on_error.replace("{{error}}", str(e))
            raise ExecutionException(f"Vector Search Failed: {str(e)}") from e

    async def _execute_rpc(self, action: ActionDefinition, **kwargs):
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
            
        request_class = self._resolve_proto_message_class(pb2, method_descriptor.input_type)

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

        logger.info(f"Executing Async gRPC {config.host}/{config.service}/{config.method}")
        timeout_seconds = (config.timeout if config.timeout is not None else 10000) / 1000.0

        try:
            if config.allow_insecure:
                channel = grpc.aio.insecure_channel(config.host)
            else:
                credentials = grpc.ssl_channel_credentials()
                channel = grpc.aio.secure_channel(config.host, credentials)
            async with channel:
                stub_class = getattr(pb2_grpc, stub_class_name)
                stub = stub_class(channel)
                rpc_method = getattr(stub, config.method)

                response_obj = await rpc_method(
                    request_obj, 
                    metadata=metadata, 
                    timeout=timeout_seconds
                )
        except grpc.RpcError as e:
            logger.error(f"gRPC Error: Status {e.code()} - {e.details()}")
            if action.response_config and action.response_config.on_error:
                return action.response_config.on_error.replace("{{error}}", e.details())
            raise ExecutionException(f"gRPC Action Failed: {e.details()}") from e

        response_dict = MessageToDict(response_obj, preserving_proto_field_name=True)
        return self._parse_response(response_dict, action.response_config)


    def _resolve_proto_message_class(self, pb2_module, descriptor):
        if descriptor.containing_type is None:
            try:
                return getattr(pb2_module, descriptor.name)
            except AttributeError as e:
                raise ServiceNotFound(
                    f"Message type '{descriptor.name}' not found in protobuf module. "
                    f"Ensure the .proto file defines this message at the top level."
                ) from e
        
        parent_class = self._resolve_proto_message_class(pb2_module, descriptor.containing_type)
        try:
            return getattr(parent_class, descriptor.name)
        except AttributeError as e:
            raise ServiceNotFound(
                f"Nested message type '{descriptor.name}' not found in parent '{parent_class.__name__}'. "
                f"Ensure the .proto file defines this nested message correctly."
            ) from e

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
                def sync_runner(**kwargs):
                    raise NotImplementedError(f"Action {act.name} is entirely asynchronous.")

                async def async_runner(**kwargs):
                    self._gate_confirmation(act, kwargs)

                    if act.type == "api_request":
                        return await self._execute_api_request(act, **kwargs)
                    elif act.type == "internal":
                        return await self._execute_internal(act, **kwargs)
                    elif act.type == "vector_query":
                        return await self._execute_vector(act, **kwargs)
                    elif act.type == "rpc_request":
                        return await self._execute_rpc(act, **kwargs)
                    else:
                        return "Action type not implemented in engine."

                return sync_runner, async_runner
            
            args_schema = self._create_args_schema(action.parameters)
            sync_func, async_func = make_runner(action)

            tool = StructuredTool.from_function(
                func=sync_func,
                coroutine=async_func,
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
            if tmpl:
                prompt = (
                    tmpl.replace("{{title}}", ctx.title)
                    .replace("{{description}}", ctx.description)
                    .replace("{{tone}}", ctx.tone)
                )
                return prompt
        return f"System: {ctx.title}. {ctx.description}"

    async def execute_action_directly(
        self,
        action_name: str,
        kwargs: dict,
        skip_confirmation: bool = False
    ) -> str:
        act = next((a for a in self.actions if a.name == action_name), None)
        if not act:
            raise ActionNotFound(f"Action '{action_name}' not found.")

        if not act.active:
            raise ActionNotActive(f"Action '{action_name}' is not active.")

        if act.parameters:
            ArgsSchema = self._create_args_schema(act.parameters)
            try:
                validated = ArgsSchema(**kwargs)
                kwargs = validated.model_dump()
            except ValidationError as e:
                raise InvalidActionStructure(
                    f"Parameter validation failed for '{action_name}': {e}"
                )

        if not skip_confirmation:
            self._gate_confirmation(act, kwargs)

        try:
            if act.type == "api_request":
                return await self._execute_api_request(act, **kwargs)
            elif act.type == "internal":
                return await self._execute_internal(act, **kwargs)
            elif act.type == "vector_query":
                return await self._execute_vector(act, **kwargs)
            elif act.type == "rpc_request":
                return await self._execute_rpc(act, **kwargs)
            else:
                return "Action type not implemented in engine."
        except ActionEngineException:
            raise
        except Exception as e:
            logger.error(f"Manual execution failed: {str(e)}")
            return f"Action Failed: {str(e)}"