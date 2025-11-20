# apis/v1/roles.py
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from core.database import get_db
from services.role_service import RoleService
from utils.schemas.role_schemas import (
    RoleResponse,
    RoleUpdate,
    UserRolesResponse,
    RoleStatistics
)
from utils.schemas.user_schemas import UserListResponse
from utils.schemas.auth_schemas import MessageResponse
from utils.dependencies import require_admin, get_current_active_user
from models.user import User
from utils.exceptions import NotFoundException, ConflictException, BadRequestException

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
    """Get all roles"""
    role_service = RoleService(db)
    roles = await role_service.get_all_roles()
    return roles


@router.get(
    "/me",
    response_model=UserRolesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get My Roles",
    description="Retrieves roles (id and name only) assigned to the current authenticated user."
)
async def get_my_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get current user's roles"""
    role_service = RoleService(db)
    user_roles = await role_service.get_user_roles(current_user.id)
    return user_roles


@router.get(
    "/statistics",
    response_model=RoleStatistics,
    status_code=status.HTTP_200_OK,
    summary="Get Role Statistics",
    description="Get comprehensive role statistics. Admin only."
)
async def get_role_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get role statistics"""
    role_service = RoleService(db)
    stats = await role_service.get_role_statistics()
    return stats


@router.get(
    "/{role_id}",
    response_model=RoleResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "Role not found"}
    },
    summary="Get Role By ID",
    description="Retrieves details of a specific role by its ID. Admin only."
)
async def get_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get role by ID"""
    role_service = RoleService(db)
    role = await role_service.get_role_by_id(role_id)
    
    if not role:
        raise NotFoundException("Role not found")
    
    return role

@router.get(
    "/{role_id}/users",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "Role not found"}
    },
    summary="Get Users By Role",
    description="Retrieves all users with a specific role. Admin only."
)
async def get_users_by_role(
    role_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get users by role"""
    role_service = RoleService(db)
    users, total = await role_service.get_users_by_role(role_id, page, limit)
    
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "users": users
    }


@router.get(
    "/user/{user_id}",
    response_model=UserRolesResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "User not found"}
    },
    summary="Get User Roles",
    description="Retrieves roles (id and name only) assigned to a specific user. Admin only."
)
async def get_user_roles(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get roles for specific user"""
    role_service = RoleService(db)
    user_roles = await role_service.get_user_roles(user_id)
    return user_roles