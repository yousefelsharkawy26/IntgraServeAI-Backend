import logging
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.user import User
from repositories.agent_config_backup_repository import AgentConfigBackupRepository
from repositories.agent_config_repository import AgentConfigRepository
from services.agent_config_backup_service import AgentConfigBackupService
from services.agent_config_service import AgentConfigService
from utils.dependencies import require_admin
from utils.schemas.agent_config_backup_schemas import (
    AgentConfigBackupCreate,
    AgentConfigBackupDeleteResponse,
    AgentConfigBackupDetail,
    AgentConfigBackupRestoreResponse,
    AgentConfigBackupSummary,
)
from utils.schemas.agent_config_schemas import AgentConfigResponse, AgentConfigUpdateResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def get_config_service(db: AsyncSession = Depends(get_db)) -> AgentConfigService:
    return AgentConfigService(AgentConfigRepository(db))


def get_backup_service(db: AsyncSession = Depends(get_db)) -> AgentConfigBackupService:
    return AgentConfigBackupService(
        AgentConfigBackupRepository(db),
        AgentConfigRepository(db),
    )


@router.get("", response_model=AgentConfigResponse, summary="Get Active Agent Configuration")
async def get_full_config(
    service: AgentConfigService = Depends(get_config_service),
    _: User = Depends(require_admin),
):
    return await service.get_full_config()


@router.put("", response_model=AgentConfigUpdateResponse, summary="Replace Active Agent Configuration")
async def update_full_config(
    config_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service),
):
    await service.update_full_config(config_data, current_user.id)
    logger.info("Full agent config updated by admin: %s", current_user.email)
    return {"message": "Full configuration updated successfully"}


@router.get("/backups", response_model=list[AgentConfigBackupSummary])
async def list_agent_config_backups(
    service: AgentConfigBackupService = Depends(get_backup_service),
    _: User = Depends(require_admin),
):
    return await service.list()


@router.post("/backups", response_model=AgentConfigBackupDetail, status_code=201)
async def create_agent_config_backup(
    payload: AgentConfigBackupCreate,
    service: AgentConfigBackupService = Depends(get_backup_service),
    current_user: User = Depends(require_admin),
):
    return await service.create(payload.name, current_user.id)


@router.get("/backups/{backup_id}", response_model=AgentConfigBackupDetail)
async def get_agent_config_backup(
    backup_id: UUID,
    service: AgentConfigBackupService = Depends(get_backup_service),
    _: User = Depends(require_admin),
):
    return await service.get(backup_id)


@router.post("/backups/{backup_id}/restore", response_model=AgentConfigBackupRestoreResponse)
async def restore_agent_config_backup(
    backup_id: UUID,
    service: AgentConfigBackupService = Depends(get_backup_service),
    current_user: User = Depends(require_admin),
):
    await service.restore(backup_id, current_user.id)
    return {"message": "Agent configuration restored successfully", "backup_id": backup_id}


@router.delete("/backups/{backup_id}", response_model=AgentConfigBackupDeleteResponse)
async def delete_agent_config_backup(
    backup_id: UUID,
    service: AgentConfigBackupService = Depends(get_backup_service),
    _: User = Depends(require_admin),
):
    await service.delete(backup_id)
    return {"message": "Agent configuration backup deleted successfully", "backup_id": backup_id}
