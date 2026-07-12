import os
import re
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from utils.exceptions import InvalidParamValueType, MissingField, InvalidActionStructure

def inject_env(text: Any) -> Any:
    """Recursively inject environment variables into strings.
    
    Raises:
        MissingField: If a referenced environment variable is not set.
    """
    if isinstance(text, str):
        pattern = r"\{\{env\.([A-Za-z0-9_]+)\}\}"
        matches = re.findall(pattern, text)
        for var in matches:
            val = os.getenv(var)
            if val is None:
                raise MissingField(f"Environment variable '{var}' is required but not set.")
            text = text.replace(f"{{{{env.{var}}}}}", val)
        return text
    elif isinstance(text, dict):
        return {k: inject_env(v) for k, v in text.items()}
    elif isinstance(text, list):
        return [inject_env(v) for v in text]
    return text

class ActionParameter(BaseModel):
    type: Literal["string", "integer", "number", "boolean", "array", "object"]
    required: bool = False
    default: Optional[Any] = None
    param_type: Literal["query", "body", "path", "vector", "message_field", "internal"]
    description: str
    enum: Optional[List[Any]] = None

    @field_validator('type', mode='before')
    @classmethod
    def validate_type(cls, v):
        valid_types = ["string", "integer", "number", "boolean", "array", "object"]
        if v not in valid_types:
            raise InvalidParamValueType(f"Type {v} not supported")
        return v
    
    @model_validator(mode='after')
    def validate_default_consistency(self):
        """Ensure default value is compatible with the declared type and enum."""
        if self.default is not None:
            type_mapping = {
                "string": (str,),
                "integer": (int,),
                "number": (int, float),
                "boolean": (bool,),
                "array": (list,),
                "object": (dict,),
            }
            expected_types = type_mapping.get(self.type)
            
            if self.type == "integer":
                if isinstance(self.default, bool) or not isinstance(self.default, int):
                    raise InvalidParamValueType(
                        f"Default value {self.default!r} is not compatible with type 'integer'"
                    )
            elif self.type == "number":
                if isinstance(self.default, bool) or not isinstance(self.default, (int, float)):
                    raise InvalidParamValueType(
                        f"Default value {self.default!r} is not compatible with type 'number'"
                    )
            elif expected_types and not isinstance(self.default, expected_types):
                raise InvalidParamValueType(
                    f"Default value {self.default!r} is not compatible with type '{self.type}'"
                )
            
            if self.enum is not None and self.default not in self.enum:
                raise InvalidParamValueType(
                    f"Default value {self.default!r} is not in enum {self.enum}"
                )
        return self
    
class LocalLoadingParams(BaseModel):
    base_url: Optional[str] = None
    gguf_file: Optional[str] = None
    context_window: Optional[int] = None
    gpu_layers: Optional[int] = None
    quantization: Optional[str] = None

    @model_validator(mode='before')
    def inject_secrets(cls, values):
        return inject_env(values)

class EmbeddingConfig(BaseModel):
    location: Literal["local", "remote"] = "remote"
    provider: str
    model_name: str
    dimensions: Optional[int] = None
    rate_limit_delay_seconds: int = 0
    api_key: Optional[str] = None
    local_loading_params: Optional[LocalLoadingParams] = None

    @model_validator(mode='before')
    def inject_secrets(cls, values):
        return inject_env(values)

class LLMConfig(BaseModel):
    location: Literal["local", "remote"] = "remote"
    provider: str
    model_name: str
    rate_limit_delay_seconds: int = 0
    max_iterations: int = Field(default=20, ge=1, le=100)
    temperature: float = 0.7
    max_tokens: int = 2048
    api_key: Optional[str] = None
    local_loading_params: Optional[LocalLoadingParams] = None
    system_prompt_template: str = ""

    @model_validator(mode='before')
    def inject_secrets(cls, values):
        return inject_env(values)

class ExecutionConfig(BaseModel):
    protocol: Optional[str] = None
    method: str = "GET"
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = {}
    timeout: Optional[int] = None
    connector: Optional[str] = None
    connection_string: Optional[str] = None
    collection_name: Optional[str] = None
    max_results: Optional[int] = 100
    auth: Optional[Dict[str, str]] = None
    embedding_config: Optional[EmbeddingConfig] = None
    host: Optional[str] = None
    service: Optional[str] = None
    proto_file: Optional[str] = None
    allow_insecure: Optional[bool] = False
    driver_options: Optional[Dict[str, Any]] = None
    
    @model_validator(mode='before')
    def inject_secrets(cls, values):
        return inject_env(values)

class ResponseValue(BaseModel):
    type: Literal["string", "integer"]
    path: str

class ResponseConfig(BaseModel):
    mode: Literal["json", "xml", "html", "sql", "raw"]
    values: Optional[Dict[str, ResponseValue]] = None
    template: Optional[str] = None
    on_error: Optional[str] = None

class ActionDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(alias="name")
    description: str
    type: Literal["api_request", "sql_query", "vector_query", "rpc_request", "knowledge_query", "internal"]
    active: bool = True
    requires_confirmation: bool = False
    requires_human_input: bool = False  # Indicates tool needs human input after approval
    execution_config: Optional[ExecutionConfig] = None
    parameters: Optional[Dict[str, ActionParameter]] = {}
    response_config: Optional[ResponseConfig] = None

    @model_validator(mode='before')
    @classmethod
    def handle_aliases_and_validation(cls, values):
        if not isinstance(values, dict):
            return values

        if 'title' in values:
            if 'name' not in values:
                values['name'] = values.pop('title')
            else:
                values.pop('title', None)
        
        required = ['name', 'description', 'type']
        for r in required:
            if r not in values:
                raise MissingField(f"Action missing field: {r}")

        return values

    @model_validator(mode='after')
    def validate_logic(self):
        if self.type == "api_request":
            if not self.execution_config:
                raise MissingField("execution_config required for api_request")
            if not self.execution_config.url:
                raise MissingField("url is required for api_request")
            allowed = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}
            normalized = self.execution_config.method.upper()
            if normalized not in allowed:
                raise InvalidActionStructure(
                    f"HTTP method '{self.execution_config.method}' is not supported. "
                    f"Use one of: {', '.join(sorted(allowed))}"
                )
            self.execution_config.method = normalized
        if self.type == "rpc_request":
            if not self.execution_config:
                raise MissingField("execution_config required for rpc_request")
            if not self.execution_config.host:
                raise InvalidActionStructure("RPC actions require 'host'")
        return self

class SystemContext(BaseModel):
    title: str
    description: str
    version: str
    tone: str

class ApiRequestDefaults(BaseModel):
    allowed_hostnames: List[str] = []
    protocol: str = "https"
    base_url: str = ""
    timeout: int = 10000
    headers: Dict[str, str] = {}
    on_error: str = "System Error: {{error}}"

class RpcRequestDefaults(BaseModel):
    protocol: str = "grpc"
    headers: Dict[str, str] = {}
    on_error: str = "System Error: {{error}}"

class VectorQueryDefaults(BaseModel):
    connector: str = "postgres"
    connection_string: str = ""
    embedding_config: Optional[EmbeddingConfig] = None
    on_error: str = "System Error: {{error}}"

class InternalDefaults(BaseModel):
    on_error: str = "System Error: {{error}}"

class GlobalDefaults(BaseModel):
    api_request: Optional[ApiRequestDefaults] = Field(default_factory=ApiRequestDefaults)
    rpc_request: Optional[RpcRequestDefaults] = Field(default_factory=RpcRequestDefaults)
    vector_query: Optional[VectorQueryDefaults] = Field(default_factory=VectorQueryDefaults)
    internal: Optional[InternalDefaults] = Field(default_factory=InternalDefaults)

    @model_validator(mode='before')
    def inject_secrets(cls, values):
        return inject_env(values)

class AgentConfiguration(BaseModel):
    system_context: SystemContext
    global_defaults: GlobalDefaults
    llm_config: Optional[LLMConfig] = None
