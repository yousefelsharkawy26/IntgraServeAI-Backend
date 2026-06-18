# ai_engine/config.py

import os
import re
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from .exceptions import *

def inject_env(text: Any) -> Any:
    """Recursively inject environment variables into strings."""
    if isinstance(text, str):
        pattern = r"\{\{env\.(.*?)\}\}"
        matches = re.findall(pattern, text)
        for var in matches:
            val = os.getenv(var)
            if not val:
                print(f"WARNING: Env var {var} not found, using empty string.")
                val = "" 
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
    param_type: Literal["query", "body", "path", "vector", "message_field"]
    description: str
    enum: Optional[List[Any]] = None

    @field_validator('type')
    def validate_type(cls, v):
        valid_types = ["string", "integer", "number", "boolean", "array", "object"]
        if v not in valid_types:
            raise InvalidParamValueType(f"Type {v} not supported")
        return v
    
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
    timeout: int = 5000
    connector: Optional[str] = None
    connection_string: Optional[str] = None
    collection_name: Optional[str] = None
    max_results: Optional[int] = 100
    auth: Optional[Dict[str, str]] = None
    embedding_config: Optional[EmbeddingConfig] = None
    host: Optional[str] = None
    service: Optional[str] = None
    proto_file: Optional[str] = None
    
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
    type: Literal["api_request", "sql_query", "vector_query", "rpc_request", "internal"]
    active: bool = True
    requires_confirmation: bool = False
    execution_config: Optional[ExecutionConfig] = None
    parameters: Optional[Dict[str, ActionParameter]] = {}
    response_config: Optional[ResponseConfig] = None

    @model_validator(mode='before')
    @classmethod
    def handle_aliases_and_validation(cls, values):
        if 'title' in values and 'name' not in values:
            values['name'] = values.pop('title')
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
        if self.type == "rpc_request":
            if not self.execution_config.host:
                raise InvalidActionStructure("RPC actions require 'host'")
        return self

class SystemContext(BaseModel):
    title: str
    description: str
    version: str
    tone: str

class ApiRequestDefaults(BaseModel):
    protocol: str = "https"
    base_url: str = ""
    timeout: int = 10000
    headers: Dict[str, str] = {}
    on_error: str = "System Error"

class RpcRequestDefaults(BaseModel):
    protocol: str = "grpc"
    on_error: str = "System Error"

class VectorQueryDefaults(BaseModel):
    connector: str = "postgres"
    connection_string: str = ""
    embedding_config: Optional[EmbeddingConfig] = None
    on_error: str = "System Error"

class InternalDefaults(BaseModel):
    on_error: str = "System Error"

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