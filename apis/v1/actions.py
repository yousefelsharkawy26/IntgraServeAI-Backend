# apis/v1/actions.py
from fastapi import APIRouter, Depends, status, Query, Body
from typing import Optional, Dict, Any

from services.action_service import ActionService
from repositories.action_repository import ActionRepository
from core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
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
)
from utils.dependencies import require_admin, get_current_active_user
from models.user import User
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def get_action_service(db: AsyncSession = Depends(get_db)) -> ActionService:
    """Create a request-scoped service backed by the current DB transaction."""
    return ActionService(ActionRepository(db))


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
    current_user: User = Depends(get_current_active_user)
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
    description="Create a new action configuration. Cannot create internal actions.",
    tags=["Actions"]
)
async def create_action(
    action_data: ActionCreate,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Create a new action (API or RPC only, not internal)."""
    action_id, name = await action_service.create_action(action_data)
    logger.info(f"Action '{action_id}' created by admin: {current_user.email}")
    return ActionCreatedResponse(
        message="Action created successfully",
        id=action_id,
        name=name
    )


@router.get(
    "/{action_id}",
    response_model=ActionResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Action not found"}},
    summary="Get Action By ID",
    description="Get full details of a specific action.",
    tags=["Actions"]
)
async def get_action(
    action_id: str,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Get action details by ID."""
    action = await action_service.get_action_by_id(action_id)
    return action


@router.put(
    "/{action_id}",
    response_model=ActionUpdatedResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "Action not found"},
        422: {"description": "Cannot update internal actions"}
    },
    summary="Update Action",
    description="Update an existing action configuration. Cannot update internal actions.",
    tags=["Actions"]
)
async def update_action(
    action_id: str,
    update_data: ActionUpdate,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Update an existing action (not internal)."""
    updated_id, updated_name = await action_service.update_action(action_id, update_data)
    logger.info(f"Action '{action_id}' updated by admin: {current_user.email}")
    return ActionUpdatedResponse(
        message="Action updated successfully",
        id=updated_id,
        name=updated_name
    )


@router.delete(
    "/{action_id}",
    response_model=ActionDeletedResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "Action not found"},
        422: {"description": "Cannot delete internal actions"}
    },
    summary="Delete Action",
    description="Delete an action configuration. Cannot delete internal actions.",
    tags=["Actions"]
)
async def delete_action(
    action_id: str,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Delete an action (not internal)."""
    deleted_id, deleted_name = await action_service.delete_action(action_id)
    logger.info(f"Action '{action_id}' deleted by admin: {current_user.email}")
    return ActionDeletedResponse(
        message="Action deleted successfully",
        id=deleted_id,
        name=deleted_name
    )


@router.patch(
    "/{action_id}/toggle",
    response_model=ActionToggleResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Action not found"}},
    summary="Toggle Action Status",
    description="Toggle the active status of an action. Works for all actions including internal.",
    tags=["Actions"]
)
async def toggle_action_status(
    action_id: str,
    current_user: User = Depends(require_admin),
    action_service: ActionService = Depends(get_action_service)
):
    """Toggle action active status (allowed for all actions including internal)."""
    toggled_id, toggled_name, new_status = await action_service.toggle_action_status(action_id)
    status_text = "activated" if new_status else "deactivated"
    logger.info(f"Action '{action_id}' {status_text} by admin: {current_user.email}")
    return ActionToggleResponse(
        message=f"Action {status_text} successfully",
        id=toggled_id,
        name=toggled_name,
        active=new_status
    )
