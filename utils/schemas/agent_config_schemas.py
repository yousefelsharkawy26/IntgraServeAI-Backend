# utils/schemas/agent_config_schemas.py

from pydantic import BaseModel, Field, field_validator, HttpUrl, ConfigDict, model_validator
from typing import Optional, Dict, Any, Literal, List, Union
from uuid import UUID
from datetime import datetime
import re

# ==================== Helper Functions & Enums ====================

ENV_VAR_PATTERN = re.compile(r"^{{env\.([A-Z0-9_]+)}}$")

class BaseConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

def validate_env_var(value: str) -> str:
    """Validator for environment variable format {{env.VAR_NAME}}"""
    if isinstance(value, str) and not ENV_VAR_PATTERN.match(value):
        raise ValueError("Invalid environment variable format. Use {{env.VAR_NAME}}")
    return value

# ==================== Level 1: Nested Models (Required fields) ====================

class SystemContext(BaseConfigModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: str = Field(..., min_length=10)
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    tone: str = Field(..., min_length=5)

class ApiRequestDefaults(BaseConfigModel):
    protocol: Literal["http", "https"]
    base_url: HttpUrl
    timeout: int = Field(..., gt=0)
    headers: Dict[str, str]
    on_error: str

class RpcRequestDefaults(BaseConfigModel):
    protocol: Literal["grpc"]
    on_error: str

class EmbeddingConfig(BaseConfigModel):
    location: str
    provider: str
    model_name: str
    dimensions: int = Field(..., gt=0)
    rate_limit_delay_seconds: int = Field(..., ge=0)
    api_key: Optional[str] = None
    local_loading_params: Optional[Dict[str, Any]] = None

class VectorQueryDefaults(BaseConfigModel):
    connector: str
    connection_string: str
    embedding_config: EmbeddingConfig
    on_error: str

class InternalDefaults(BaseConfigModel):
    on_error: str

class LLMLocalLoadingParams(BaseConfigModel):
    base_url: HttpUrl
    gguf_file: str
    context_window: int = Field(..., gt=0)
    gpu_layers: int = Field(..., ge=0)
    quantization: Literal["int4", "int8", "f16", "f32"]

class LLMConfig(BaseConfigModel):
    location: str
    provider: str
    model_name: str
    rate_limit_delay_seconds: int = Field(..., ge=0)
    temperature: float = Field(..., ge=0.0, le=2.0)
    max_tokens: int = Field(..., gt=0)
    local_loading_params: Optional[LLMLocalLoadingParams] = None
    system_prompt_template: str

class GlobalDefaults(BaseConfigModel):
    api_request: Optional[ApiRequestDefaults] = None
    rpc_request: Optional[RpcRequestDefaults] = None
    vector_query: Optional[VectorQueryDefaults] = None
    internal: Optional[InternalDefaults] = None

# ==================== Level 2: Main Config Model (for Read/Full Update) ====================

class AgentConfig(BaseConfigModel):
    system_context: SystemContext
    global_defaults: Optional[GlobalDefaults] = None
    llm_config: LLMConfig

# ==================== Level 3: Partial Update Models (All fields optional) ====================

class SystemContextUpdate(BaseConfigModel):
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = Field(None, min_length=10)
    version: Optional[str] = Field(None, pattern=r"^\d+\.\d+\.\d+$")
    tone: Optional[str] = Field(None, min_length=5)

class ApiRequestDefaultsUpdate(BaseConfigModel):
    protocol: Optional[Literal["http", "https"]] = None
    base_url: Optional[HttpUrl] = None
    timeout: Optional[int] = Field(None, gt=0)
    headers: Optional[Dict[str, str]] = None
    on_error: Optional[str] = None

class GlobalDefaultsUpdate(BaseConfigModel):
    api_request: Optional[ApiRequestDefaultsUpdate] = None
    # Add other defaults if they become updatable in the future

class LLMLocalLoadingParamsUpdate(BaseConfigModel):
    base_url: Optional[HttpUrl] = None
    gguf_file: Optional[str] = None
    context_window: Optional[int] = Field(None, gt=0)
    gpu_layers: Optional[int] = Field(None, ge=0)
    quantization: Optional[Literal["int4", "int8", "f16", "f32"]] = None

class LLMConfigUpdate(BaseConfigModel):
    location: Optional[str] = None
    provider: Optional[str] = None
    model_name: Optional[str] = None
    rate_limit_delay_seconds: Optional[int] = Field(None, ge=0)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0)
    local_loading_params: Optional[LLMLocalLoadingParamsUpdate] = None
    system_prompt_template: Optional[str] = None

# ==================== API Response Schemas ====================

class Metadata(BaseModel):
    last_updated: Optional[datetime] = None
    updated_by: Optional[UUID] = None
    restored_from: Optional[str] = None

class AgentConfigResponse(AgentConfig):
    metadata: Metadata

class ConfigSectionResponse(BaseModel):
    section: str
    content: Dict[str, Any]

class ConfigUpdateResponse(BaseModel):
    message: str
    section: str
    backup_created: Optional[str] = None

class BackupInfo(BaseModel):
    filename: str
    created_at: datetime
    size_kb: float

class BackupListResponse(BaseModel):
    total: int
    backups: List[BackupInfo]

class RestoreBackupResponse(BaseModel):
    message: str
    restored_from: str
    backup_created: str

class CompareResult(BaseModel):
    added_keys: List[str]
    removed_keys: List[str]
    changed_keys: List[str]

class CompareResponse(BaseModel):
    filename: str
    has_changes: bool
    changes: Dict[str, CompareResult]