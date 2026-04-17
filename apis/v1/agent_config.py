# apis/v1/agent_config.py

from fastapi import APIRouter, Depends, status, Body
from typing import Dict, Any, List
from uuid import UUID

from services.agent_config_service import AgentConfigService
from utils.dependencies import require_admin
from models.user import User
from utils.schemas.agent_config_schemas import (
    AgentConfigResponse, ConfigSectionResponse, ConfigUpdateResponse,
    BackupListResponse, BackupInfo, RestoreBackupResponse, CompareResponse
)
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Dependency to get the service instance
def get_config_service() -> AgentConfigService:
    return AgentConfigService()

@router.get(
    "",
    response_model=AgentConfigResponse,
    summary="Get Full Agent Configuration",
    description="Retrieves the entire agent configuration. Admin only.",
)
async def get_full_config(
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service)
):
    """Get the full agent configuration."""
    config = service.get_full_config()
    return config

@router.put(
    "",
    response_model=ConfigUpdateResponse,
    summary="Update Full Agent Configuration",
    description="Replaces the entire agent configuration. Admin only.",
)
async def update_full_config(
    config_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service)
):
    """Update the entire agent configuration."""
    backup_filename = service.update_full_config(config_data, current_user.id)
    logger.info(f"Full agent config updated by admin: {current_user.email}")
    return {
        "message": "Full configuration updated successfully",
        "section": "all",
        "backup_created": backup_filename
    }

@router.get(
    "/sections/{section_name}",
    response_model=ConfigSectionResponse,
    summary="Get Configuration Section",
    description="Retrieves a specific section of the agent configuration. Admin only.",
)
async def get_config_section(
    section_name: str,
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service)
):
    """Get a specific section of the config."""
    content = service.get_section(section_name)
    return {"section": section_name, "content": content}

@router.patch(
    "/sections/{section_name}",
    response_model=ConfigUpdateResponse,
    summary="Update Configuration Section (Partial)",
    description="Updates specific fields within a section of the agent configuration. Admin only.",
)
async def update_config_section(
    section_name: str,
    update_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service)
):
    """Partially update a specific section of the config."""
    backup_filename = service.update_section(section_name, update_data, current_user.id)
    logger.info(f"Agent config section '{section_name}' updated by admin: {current_user.email}")
    return {
        "message": f"Section '{section_name}' updated successfully",
        "section": section_name,
        "backup_created": backup_filename
    }

# --- Backup Endpoints ---

@router.get(
    "/backups",
    response_model=BackupListResponse,
    summary="List All Backups",
    description="Get a list of all available configuration backups. Admin only.",
)
async def list_backups(
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service)
):
    """List all available backups."""
    backups = service.list_backups()
    return BackupListResponse(total=len(backups), backups=[BackupInfo(**b) for b in backups])

@router.get(
    "/backups/{filename}",
    response_model=Dict[str, Any],
    summary="Get Backup Content",
    description="Retrieves the content of a specific backup file. Admin only.",
)
async def get_backup_content(
    filename: str,
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service)
):
    """Get the content of a specific backup."""
    return service.get_backup_content(filename)

@router.post(
    "/backups/{filename}/restore",
    response_model=RestoreBackupResponse,
    summary="Restore From Backup",
    description="Restores the agent configuration from a backup file. A backup of the current state is created automatically. Admin only.",
)
async def restore_from_backup(
    filename: str,
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service)
):
    """Restore configuration from a backup file."""
    restored_from, backup_created = service.restore_from_backup(filename, current_user.id)
    logger.info(f"Agent config restored from '{filename}' by admin: {current_user.email}")
    return {
        "message": "Configuration restored successfully",
        "restored_from": restored_from,
        "backup_created": backup_created
    }