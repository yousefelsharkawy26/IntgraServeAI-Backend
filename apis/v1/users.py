# apis/v1/users.py
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from core.database import get_db
from services.user_service import UserService
from utils.schemas.user_schemas import (
    UserCreate,
    UserUpdateBasicInfo,
    UserUpdatePassword,
    UserUpdateRoles,
    UserResponse,
    UserListResponse,
    UserLogsResponse,
    MyProfileUpdate,
    MyPasswordChange,
    UserStatistics,
    BulkUserOperation,
    BulkOperationResponse,
    UserActivityResponse
)
from utils.schemas.auth_schemas import MessageResponse
from utils.dependencies import require_admin, get_current_active_user
from models.user import User
from utils.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException,
    ValidationException
)

router = APIRouter()


# ==================== Public User Endpoints ====================

@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get My Profile",
    description="Retrieves the current authenticated user's profile information."
)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get current user's profile"""
    user_service = UserService(db)
    user = await user_service.get_user_with_roles(current_user.id)
    return user


@router.patch(
    "/me",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Profile updated successfully"},
        400: {"description": "No changes provided"},
        409: {"description": "Email already exists"}
    },
    summary="Update My Profile",
    description="Update current user's profile (email and/or full name)."
)
async def update_my_profile(
    update_data: MyProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update my profile"""
    user_service = UserService(db)
    await user_service.update_my_profile(current_user.id, update_data)
    return {"message": "Profile updated successfully"}


@router.patch(
    "/me/password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Password changed successfully"},
        401: {"description": "Current password is incorrect"}
    },
    summary="Change My Password",
    description="Change current user's password."
)
async def change_my_password(
    password_data: MyPasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Change my password"""
    user_service = UserService(db)
    await user_service.change_my_password(current_user.id, password_data)
    return {"message": "Password changed successfully"}


@router.get(
    "/me/logs",
    response_model=UserLogsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get My Action Logs",
    description="Retrieves audit logs for actions performed by the current authenticated user."
)
async def get_my_logs(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get current user's action logs"""
    user_service = UserService(db)
    logs, total = await user_service.get_user_logs(current_user.id, page, limit)
    
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "logs": logs
    }


# ==================== Admin User Management Endpoints ====================

@router.post(
    "",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "User created successfully"},
        409: {"description": "Email already exists"},
        422: {"description": "Validation errors"}
    },
    summary="Add User",
    description="Creates a new user account with defined roles. Admin only."
)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create new user"""
    user_service = UserService(db)
    await user_service.create_user(user_data, current_user.id)
    return {"message": "User created successfully"}


@router.get(
    "",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Users",
    description="Retrieves a list of users with optional filters and search (excluding current user). Admin only."
)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    role: Optional[str] = Query(None, description="Filter by role name"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    email_confirmed: Optional[bool] = Query(None, description="Filter by email confirmation"),
    search: Optional[str] = Query(None, min_length=2, description="Search by email or name"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    List users with filters and search
    
    **Admin only**
    
    - **page**: Page number (default: 1)
    - **limit**: Items per page (default: 10, max: 100)
    - **role**: Filter by role name (optional)
    - **is_active**: Filter by active status (optional)
    - **email_confirmed**: Filter by email confirmation (optional)
    - **search**: Search in email and full name (optional, min 2 chars)
    """
    user_service = UserService(db)
    users, total = await user_service.list_users(
        current_user_id=current_user.id,
        page=page,
        limit=limit,
        role=role,
        is_active=is_active,
        email_confirmed=email_confirmed,
        search=search
    )
    
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "users": users
    }


@router.get(
    "/statistics",
    response_model=UserStatistics,
    status_code=status.HTTP_200_OK,
    summary="Get User Statistics",
    description="Get comprehensive user statistics. Admin only."
)
async def get_user_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get user statistics"""
    user_service = UserService(db)
    stats = await user_service.get_user_statistics()
    return stats


@router.get(
    "/activity",
    response_model=UserActivityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get User Activity",
    description="Get user activity information (last login). Admin only."
)
async def get_user_activity(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("last_login", description="Sort by: last_login or created_at"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get user activity
    
    **Admin only**
    
    - **page**: Page number (default: 1)
    - **limit**: Items per page (default: 10, max: 100)
    - **sort_by**: Sort by last_login or created_at (default: last_login)
    """
    user_service = UserService(db)
    users, total = await user_service.get_user_activity(page, limit, sort_by)
    
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "users": users
    }


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "User not found"}
    },
    summary="Get User By ID",
    description="Retrieves user information with role names by user ID. Admin only."
)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get user by ID"""
    user_service = UserService(db)
    user = await user_service.get_user_with_roles(user_id)
    return user


@router.patch(
    "/{user_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "User updated successfully"},
        404: {"description": "User not found"}
    },
    summary="Update Basic Info",
    description="Updates user basic info: email and full name. Admin only."
)
async def update_user_info(
    user_id: UUID,
    update_data: UserUpdateBasicInfo,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update user basic information"""
    user_service = UserService(db)
    await user_service.update_basic_info(user_id, update_data, current_user.id)
    return {"message": "User info updated successfully"}


@router.patch(
    "/{user_id}/password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Password updated"},
        404: {"description": "User not found"}
    },
    summary="Update User Password",
    description="Updates user password. Admin only."
)
async def update_user_password(
    user_id: UUID,
    update_data: UserUpdatePassword,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update user password"""
    user_service = UserService(db)
    await user_service.update_password(user_id, update_data, current_user.id)
    return {"message": "User password updated successfully"}


@router.patch(
    "/{user_id}/roles",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Roles updated"},
        404: {"description": "User or role not found"},
        422: {"description": "Validation errors"}
    },
    summary="Update User Roles",
    description="Updates user roles. Admin only."
)
async def update_user_roles(
    user_id: UUID,
    update_data: UserUpdateRoles,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update user roles"""
    user_service = UserService(db)
    await user_service.update_roles(user_id, update_data, current_user.id)
    return {"message": "User roles updated successfully"}

# ✅ Bulk operations
@router.patch(
    "/bulk/activate",
    response_model=BulkOperationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Bulk activation completed"}
    },
    summary="Bulk Activate Users",
    description="Activate multiple users at once. Admin only. Max 100 users per request."
)
async def bulk_activate_users(
    operation_data: BulkUserOperation,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Bulk activate users
    
    **Admin only**
    
    - **user_ids**: List of user UUIDs to activate (max 100)
    
    Returns summary of successful and failed operations.
    """
    user_service = UserService(db)
    result = await user_service.bulk_activate_users(operation_data.user_ids, current_user.id)
    return result


@router.patch(
    "/bulk/deactivate",
    response_model=BulkOperationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Bulk deactivation completed"}
    },
    summary="Bulk Deactivate Users",
    description="Deactivate multiple users at once. Admin only. Max 100 users per request."
)
async def bulk_deactivate_users(
    operation_data: BulkUserOperation,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Bulk deactivate users
    
    **Admin only**
    
    - **user_ids**: List of user UUIDs to deactivate (max 100)
    
    Returns summary of successful and failed operations.
    """
    user_service = UserService(db)
    result = await user_service.bulk_deactivate_users(operation_data.user_ids, current_user.id)
    return result


@router.get(
    "/{user_id}/logs",
    response_model=UserLogsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "User not found"}
    },
    summary="View User Action Logs",
    description="Retrieves audit logs for actions performed BY a specific user. Admin only."
)
async def get_user_logs(
    user_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get user action logs"""
    user_service = UserService(db)
    logs, total = await user_service.get_user_logs(user_id, page, limit)
    
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "logs": logs
    }