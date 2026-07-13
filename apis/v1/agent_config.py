from typing import Any, Dict

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.user import User
from repositories.agent_config_repository import AgentConfigRepository
from services.agent_config_service import AgentConfigService
from utils.dependencies import require_admin
from utils.schemas.agent_config_schemas import (
    AgentConfigResponse,
    BackupDeleteAllResponse,
    BackupDeleteResponse,
    BackupListResponse,
    ConfigSectionResponse,
    ConfigUpdateResponse,
    RestoreBackupResponse,
)
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def get_config_service(db: AsyncSession = Depends(get_db)) -> AgentConfigService:
    return AgentConfigService(AgentConfigRepository(db))


@router.get("", response_model=AgentConfigResponse, summary="Get Full Agent Configuration")
async def get_full_config(
    service: AgentConfigService = Depends(get_config_service),
    _: User = Depends(require_admin),
):
    return await service.get_full_config()


@router.put("", response_model=ConfigUpdateResponse, summary="Update Full Agent Configuration")
async def update_full_config(
    config_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service),
):
    backup_filename = await service.update_full_config(config_data, current_user.id)
    logger.info("Full agent config updated by admin: %s", current_user.email)
    return {
        "message": "Full configuration updated successfully",
        "section": "all",
        "backup_created": backup_filename,
    }


@router.get("/sections/{section_name}", response_model=ConfigSectionResponse, summary="Get Configuration Section")
async def get_config_section(
    section_name: str,
    service: AgentConfigService = Depends(get_config_service),
    _: User = Depends(require_admin),
):
    return {"section": section_name, "content": await service.get_section(section_name)}


@router.patch("/sections/{section_name}", response_model=ConfigUpdateResponse, summary="Update Configuration Section (Partial/Deep)")
async def update_config_section(
    section_name: str,
    update_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service),
):
    backup_filename = await service.update_section(section_name, update_data, current_user.id)
    logger.info("Agent config section '%s' updated by admin: %s", section_name, current_user.email)
    return {
        "message": f"Section '{section_name}' updated successfully",
        "section": section_name,
        "backup_created": backup_filename,
    }


@router.get("/backups", response_model=BackupListResponse, summary="List All Backups")
async def list_backups(
    service: AgentConfigService = Depends(get_config_service),
    _: User = Depends(require_admin),
):
    backups = await service.list_backups()
    return {"total": len(backups), "backups": backups}


@router.get("/backups/{filename}", response_model=Dict[str, Any], summary="Get Backup Content")
async def get_backup_content(
    filename: str,
    service: AgentConfigService = Depends(get_config_service),
    _: User = Depends(require_admin),
):
    return await service.get_backup_content(filename)


@router.post("/backups/{filename}/restore", response_model=RestoreBackupResponse)
async def restore_from_backup(
    filename: str,
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service),
):
    restored_from, backup_created = await service.restore_from_backup(filename, current_user.id)
    logger.info("Agent config restored from '%s' by admin: %s", filename, current_user.email)
    return {
        "message": "Configuration restored successfully",
        "restored_from": restored_from,
        "backup_created": backup_created,
    }


@router.delete("/backups/{filename}", response_model=BackupDeleteResponse)
async def delete_backup(
    filename: str,
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service),
):
    await service.delete_backup(filename)
    logger.info("Agent config backup '%s' deleted by admin: %s", filename, current_user.email)
    return {"message": "Backup deleted successfully", "filename": filename}


@router.delete("/backups", response_model=BackupDeleteAllResponse)
async def delete_all_backups(
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service),
):
    count = await service.delete_all_backups()
    logger.warning("All %s agent config backups deleted by admin: %s", count, current_user.email)
    return {"message": f"Successfully deleted {count} backup(s).", "deleted_count": count}
