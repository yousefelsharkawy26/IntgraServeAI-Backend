from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class SystemContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=2, max_length=200)
    description: str = Field(..., min_length=10)
    version: str = Field(..., min_length=1, max_length=50)
    tone: str = Field(..., min_length=5, max_length=500)


class AgentConfig(RootModel[Dict[str, Any]]):
    """Existing full-config payload with an independent LLM selection."""

    @model_validator(mode="before")
    @classmethod
    def validate_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise TypeError("Configuration must be a dictionary.")
        for key in ("system_context", "llm_config_id"):
            if key not in data:
                raise ValueError(f"Missing required configuration field: '{key}'")
        SystemContext.model_validate(data["system_context"])
        UUID(str(data["llm_config_id"]))
        if data.get("global_defaults") is not None and not isinstance(data["global_defaults"], dict):
            raise ValueError("global_defaults must be an object")
        return data


class Metadata(BaseModel):
    last_updated: Optional[datetime] = None
    updated_by: Optional[UUID] = None


class AgentConfigResponse(BaseModel):
    system_context: Dict[str, Any]
    global_defaults: Dict[str, Any]
    llm_config_id: UUID
    metadata: Metadata


class AgentConfigUpdateResponse(BaseModel):
    message: str
