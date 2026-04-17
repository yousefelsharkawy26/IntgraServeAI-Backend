# apis/v1/agent_config.py

from fastapi import APIRouter, Depends, status, Body
from typing import Dict, Any
from uuid import UUID

from services.agent_config_service import AgentConfigService
from utils.dependencies import require_admin
from models.user import User
from utils.schemas.agent_config_schemas import (
    AgentConfigResponse, ConfigSectionResponse, ConfigUpdateResponse,
    BackupListResponse, RestoreBackupResponse, BackupDeleteResponse, BackupDeleteAllResponse
)
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

def get_config_service() -> AgentConfigService:
    return AgentConfigService()

@router.get("", response_model=AgentConfigResponse, summary="Get Full Agent Configuration")
async def get_full_config(service: AgentConfigService = Depends(get_config_service), _: User = Depends(require_admin)):
    config = service.get_full_config()
    # Pydantic will automatically parse the response, so we just return the dict
    return config

@router.put("", response_model=ConfigUpdateResponse, summary="Update Full Agent Configuration")
async def update_full_config(config_data: Dict[str, Any] = Body(...), current_user: User = Depends(require_admin), service: AgentConfigService = Depends(get_config_service)):
    backup_filename = service.update_full_config(config_data, current_user.id)
    logger.info(f"Full agent config updated by admin: {current_user.email}")
    return {"message": "Full configuration updated successfully", "section": "all", "backup_created": backup_filename}

@router.get("/sections/{section_name}", response_model=ConfigSectionResponse, summary="Get Configuration Section")
async def get_config_section(section_name: str, service: AgentConfigService = Depends(get_config_service), _: User = Depends(require_admin)):
    content = service.get_section(section_name)
    return {"section": section_name, "content": content}

@router.patch("/sections/{section_name}", response_model=ConfigUpdateResponse, summary="Update Configuration Section (Partial/Deep)")
async def update_config_section(section_name: str, update_data: Dict[str, Any] = Body(...), current_user: User = Depends(require_admin), service: AgentConfigService = Depends(get_config_service)):
    backup_filename = service.update_section(section_name, update_data, current_user.id)
    logger.info(f"Agent config section '{section_name}' updated by admin: {current_user.email}")
    return {"message": f"Section '{section_name}' updated successfully", "section": section_name, "backup_created": backup_filename}

# --- Backup Endpoints ---

@router.get("/backups", response_model=BackupListResponse, summary="List All Backups")
async def list_backups(service: AgentConfigService = Depends(get_config_service), _: User = Depends(require_admin)):
    backups = service.list_backups()
    return {"total": len(backups), "backups": backups}

@router.get("/backups/{filename}", response_model=Dict[str, Any], summary="Get Backup Content")
async def get_backup_content(filename: str, service: AgentConfigService = Depends(get_config_service), _: User = Depends(require_admin)):
    return service.get_backup_content(filename)

@router.post("/backups/{filename}/restore", response_model=RestoreBackupResponse, summary="Restore From Backup")
async def restore_from_backup(filename: str, current_user: User = Depends(require_admin), service: AgentConfigService = Depends(get_config_service)):
    restored_from, backup_created = service.restore_from_backup(filename, current_user.id)
    logger.info(f"Agent config restored from '{filename}' by admin: {current_user.email}")
    return {"message": "Configuration restored successfully", "restored_from": restored_from, "backup_created": backup_created}

@router.delete("/backups/{filename}", response_model=BackupDeleteResponse, summary="Delete Single Backup")
async def delete_backup(filename: str, current_user: User = Depends(require_admin), service: AgentConfigService = Depends(get_config_service)):
    service.delete_backup(filename)
    logger.info(f"Agent config backup '{filename}' deleted by admin: {current_user.email}")
    return {"message": "Backup deleted successfully", "filename": filename}

@router.delete("/backups", response_model=BackupDeleteAllResponse, summary="Delete All Backups")
async def delete_all_backups(current_user: User = Depends(require_admin), service: AgentConfigService = Depends(get_config_service)):
    count = service.delete_all_backups()
    logger.warning(f"All {count} agent config backups deleted by admin: {current_user.email}")
    return {"message": f"Successfully deleted {count} backup(s).", "deleted_count": count}