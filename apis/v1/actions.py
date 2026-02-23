# apis/v1/actions.py
from fastapi import APIRouter, Depends, status, Query, Body
from typing import Optional, Dict, Any, List

from services.action_service import ActionService
from utils.schemas.action_schemas import (
    ActionCreate,
    ActionUpdate,
    ActionResponse,
    ActionListResponse,
    ActionSummary,
    ActionCreatedResponse,
    ActionUpdatedResponse,
    ActionDeletedResponse,
    ActionToggleResponse,
    ActionValidateResponse,
    ActionTypesResponse,
    get_action_types_info,
    BackupInfo,
    BackupListResponse,
    BackupContentResponse,
    BackupRestoreResponse,
    BackupDeleteResponse,
    BackupDeleteAllResponse,
    BackupCompareResponse,
)
from utils.dependencies import require_admin
from models.user import User
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def get_action_service() -> ActionService:
    """Dependency to get ActionService instance"""
    return ActionService()


# ============================================================================
# Static Routes (MUST BE FIRST!)
# ============================================================================

@router.get(
    "/types",
    response_model=ActionTypesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Supported Action Types",
    description="Get information about all supported action types.",
    tags=["Actions"]
)
async def get_action_types(
    current_user: User = Depends(require_admin)
):
    """Get all supported action types with their configuration."""
    types_info = get_action_types_info()
    return ActionTypesResponse(types=types_info)


@router.post(
    "/validate",
    response_model=ActionValidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate Action",
    description="Validate an action structure without saving it.",
    tags=["Actions"]
)
async def validate_action(
    action_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Validate action structure without saving."""
    is_valid, message, warnings = await action_service.validate_action_only(action_data)
    return ActionValidateResponse(
        valid=is_valid,
        message=message,
        warnings=warnings if warnings else None
    )


# ============================================================================
# Backup Routes (MUST BE BEFORE /{name}!)
# ============================================================================

@router.get(
    "/backups",
    response_model=BackupListResponse,
    status_code=status.HTTP_200_OK,
    summary="List All Backups",
    description="Get a list of all backup files.",
    tags=["Backups"]
)
async def list_backups(
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """List all available backups (newest first)."""
    backups = await action_service.get_all_backups()
    return BackupListResponse(
        total=len(backups),
        backups=[BackupInfo(**b) for b in backups]
    )


@router.delete(
    "/backups",
    response_model=BackupDeleteAllResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete All Backups",
    description="Delete all backup files.",
    tags=["Backups"]
)
async def delete_all_backups(
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Delete all backups. WARNING: Permanent!"""
    result = await action_service.delete_all_backups()
    logger.info(f"All backups deleted by admin: {current_user.email}")
    return BackupDeleteAllResponse(**result)


@router.get(
    "/backups/{filename}",
    response_model=BackupContentResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Backup not found"}},
    summary="Get Backup Content",
    description="Get the content of a specific backup file.",
    tags=["Backups"]
)
async def get_backup_content(
    filename: str,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Get content of a specific backup."""
    content = await action_service.get_backup_content(filename)
    return BackupContentResponse(**content)


@router.get(
    "/backups/{filename}/compare",
    response_model=BackupCompareResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Backup not found"}},
    summary="Compare With Backup",
    description="Compare current actions with a backup.",
    tags=["Backups"]
)
async def compare_with_backup(
    filename: str,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Compare current state with a backup."""
    comparison = await action_service.compare_with_backup(filename)
    return BackupCompareResponse(**comparison)


@router.post(
    "/backups/{filename}/restore",
    response_model=BackupRestoreResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Backup not found"}},
    summary="Restore Backup",
    description="Restore actions from a backup. Current state backed up first.",
    tags=["Backups"]
)
async def restore_backup(
    filename: str,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Restore from backup. Current state auto-backed up first."""
    result = await action_service.restore_backup(filename)
    logger.info(f"Backup '{filename}' restored by admin: {current_user.email}")
    return BackupRestoreResponse(**result)


@router.delete(
    "/backups/{filename}",
    response_model=BackupDeleteResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Backup not found"}},
    summary="Delete Backup",
    description="Delete a specific backup file.",
    tags=["Backups"]
)
async def delete_backup(
    filename: str,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Delete a specific backup. WARNING: Permanent!"""
    result = await action_service.delete_backup(filename)
    logger.info(f"Backup '{filename}' deleted by admin: {current_user.email}")
    return BackupDeleteResponse(**result)


# ============================================================================
# Actions CRUD Routes
# ============================================================================

@router.get(
    "",
    response_model=ActionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List All Actions",
    description="Get a list of all actions with optional filters.",
    tags=["Actions"]
)
async def list_actions(
    type: Optional[str] = Query(None, description="Filter by action type"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, min_length=2, description="Search in name/description"),
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """List all actions with optional filtering."""
    actions, total = await action_service.get_all_actions(
        action_type=type,
        active=active,
        search=search
    )
    return ActionListResponse(total=total, actions=actions)


@router.post(
    "",
    response_model=ActionCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Action",
    description="Create a new action configuration.",
    tags=["Actions"]
)
async def create_action(
    action_data: ActionCreate,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Create a new action."""
    name = await action_service.create_action(action_data)
    logger.info(f"Action '{name}' created by admin: {current_user.email}")
    return ActionCreatedResponse(message="Action created successfully", name=name)


@router.get(
    "/{name}",
    response_model=ActionResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Action not found"}},
    summary="Get Action By Name",
    description="Get full details of a specific action.",
    tags=["Actions"]
)
async def get_action(
    name: str,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Get action details by name."""
    action = await action_service.get_action_by_name(name)
    return action


@router.put(
    "/{name}",
    response_model=ActionUpdatedResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Action not found"}},
    summary="Update Action",
    description="Update an existing action configuration.",
    tags=["Actions"]
)
async def update_action(
    name: str,
    update_data: ActionUpdate,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Update an existing action."""
    updated_name = await action_service.update_action(name, update_data)
    logger.info(f"Action '{name}' updated by admin: {current_user.email}")
    return ActionUpdatedResponse(message="Action updated successfully", name=updated_name)


@router.delete(
    "/{name}",
    response_model=ActionDeletedResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Action not found"}},
    summary="Delete Action",
    description="Delete an action configuration.",
    tags=["Actions"]
)
async def delete_action(
    name: str,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Delete an action."""
    deleted_name = await action_service.delete_action(name)
    logger.info(f"Action '{name}' deleted by admin: {current_user.email}")
    return ActionDeletedResponse(message="Action deleted successfully", name=deleted_name)


@router.patch(
    "/{name}/toggle",
    response_model=ActionToggleResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Action not found"}},
    summary="Toggle Action Status",
    description="Toggle the active status of an action.",
    tags=["Actions"]
)
async def toggle_action_status(
    name: str,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Toggle action active status."""
    toggled_name, new_status = await action_service.toggle_action_status(name)
    status_text = "activated" if new_status else "deactivated"
    logger.info(f"Action '{name}' {status_text} by admin: {current_user.email}")
    return ActionToggleResponse(
        message=f"Action {status_text} successfully",
        name=toggled_name,
        active=new_status
    )