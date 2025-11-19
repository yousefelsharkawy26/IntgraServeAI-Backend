from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from core.database import get_db
from services.role_service import RoleService
from utils.schemas.role_schemas import RoleResponse
from utils.dependencies import require_admin
from models.user import User
from utils.exceptions import NotFoundException

router = APIRouter()


@router.get(
    "",
    response_model=List[RoleResponse],
    status_code=status.HTTP_200_OK,
    summary="List All Roles",
    description="Retrieves a list of all roles in the system. Admin only."
)
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get all roles
    
    **Admin only**
    
    Returns list of all system roles.
    """
    role_service = RoleService(db)
    roles = await role_service.get_all_roles()
    return roles


@router.get(
    "/{role_id}",
    response_model=RoleResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "Role not found",
            "content": {
                "application/json": {
                    "example": {"message": "Role not found"}
                }
            }
        }
    },
    summary="Get Role By ID",
    description="Retrieves details of a specific role by its ID. Admin only."
)
async def get_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get role by ID
    
    **Admin only**
    
    - **role_id**: Role UUID
    
    Returns role details.
    """
    role_service = RoleService(db)
    role = await role_service.get_role_by_id(role_id)
    
    if not role:
        raise NotFoundException("Role not found")
    
    return role