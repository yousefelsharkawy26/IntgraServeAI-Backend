from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LLMConfigurationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    provider: str = Field(..., min_length=1, max_length=100)
    location: Literal["local", "remote"] = "remote"
    model_name: str = Field(..., min_length=1, max_length=255)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, gt=0)
    system_prompt_template: str = ""
    active: bool = True
    api_key_reference: Optional[str] = Field(default=None, max_length=255)
    config_json: Dict[str, Any] = Field(default_factory=dict)


class LLMConfigurationCreate(LLMConfigurationBase):
    api_key: Optional[SecretStr] = None


class LLMConfigurationReplace(LLMConfigurationBase):
    api_key: Optional[SecretStr] = None


class LLMConfigurationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=100)
    location: Optional[Literal["local", "remote"]] = None
    model_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    api_key: Optional[SecretStr] = None
    api_key_reference: Optional[str] = Field(default=None, max_length=255)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    system_prompt_template: Optional[str] = None
    active: Optional[bool] = None
    config_json: Optional[Dict[str, Any]] = None


class LLMConfigurationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    provider: str
    location: str
    model_name: str
    api_key_reference: Optional[str] = None
    has_api_key: bool
    temperature: float
    max_tokens: int
    system_prompt_template: str
    active: bool
    config_json: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProviderInfo(BaseModel):
    id: str
    name: str


class LLMConfigurationDeletedResponse(BaseModel):
    message: str
    id: UUID
