# utils/schemas/agent_config_schemas.py

from pydantic import BaseModel, Field, HttpUrl, ConfigDict, model_validator, RootModel
from typing import Optional, Dict, Any, Literal, List
from uuid import UUID
from datetime import datetime

# --- Strict Models for KNOWN Sections ---
# These ensure that if a known section exists, it has the correct structure.

class BaseConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="allow") # Allow any sub-keys like api_request, etc.

# --- Root Model for Flexible Validation ---
# This is the main model used for validation. It ensures required sections exist
# and validates known sections, while allowing any other new sections.

KNOWN_SECTIONS = {
    "system_context": SystemContext,
    "llm_config": LLMConfig,
    "global_defaults": GlobalDefaults
}

class AgentConfig(RootModel[Dict[str, Any]]):
    @model_validator(mode='before')
    @classmethod
    def validate_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise TypeError("Configuration must be a dictionary.")

        # 1. Ensure required sections exist
        required = ["system_context", "llm_config"]
        for key in required:
            if key not in data:
                raise ValueError(f"Missing required configuration section: '{key}'")

        # 2. Validate known sections against their strict models
        errors = {}
        for key, model in KNOWN_SECTIONS.items():
            if key in data and data[key] is not None:
                try:
                    model.model_validate(data[key])
                except Exception as e:
                    errors[key] = e.errors()
        
        if errors:
            # Re-raise as a single validation error for FastAPI to catch
            raise ValueError(f"Validation errors in known sections: {errors}")

        # 3. If everything is fine, return the data to be stored
        return data

# --- API Response Schemas (unchanged) ---

class Metadata(BaseModel):
    last_updated: Optional[datetime] = None
    updated_by: Optional[UUID] = None
    restored_from: Optional[str] = None

class AgentConfigResponse(BaseModel):
    # This allows any key, mirroring the flexible structure
    model_config = ConfigDict(extra="allow")
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

class BackupDeleteResponse(BaseModel):
    message: str
    filename: str

class BackupDeleteAllResponse(BaseModel):
    message: str
    deleted_count: int