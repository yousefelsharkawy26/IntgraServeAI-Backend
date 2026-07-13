from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AgentConfigBackupCreate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)


class AgentConfigBackupSummary(BaseModel):
    id: UUID
    agent_config_id: UUID
    name: str
    created_at: datetime
    created_by_id: Optional[UUID] = None


class AgentConfigBackupDetail(AgentConfigBackupSummary):
    snapshot: Dict[str, Any]


class AgentConfigBackupRestoreResponse(BaseModel):
    message: str
    backup_id: UUID


class AgentConfigBackupDeleteResponse(BaseModel):
    message: str
    backup_id: UUID
