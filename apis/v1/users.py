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
    UserLogsResponse
)
from utils.schemas.auth_schemas import MessageResponse
from utils.dependencies import require_admin
from models.user import User
from utils.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException,
    ValidationException
)

router = APIRouter()


@router.post(
    "",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "User created successfully",
            "content": {
                "application/json": {
                    "example": {"message": "User created successfully"}
                }
            }
        },
        409: {
            "description": "Email already exists",
            "content": {
                "application/json": {
                    "example": {"message": "Email 'user@example.com' already exists"}
                }
            }
        },
        422: {
            "description": "Validation errors",
            "content": {
                "application/json": {
                    "example": {
                        "errors": {
                            "email": "Invalid email format",
                            "roles": "Choose at least one role"
                        }
                    }
                }
            }
        }
    },
    summary="Add User",
    description="Creates a new user account with defined roles. Admin only."
)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Create new user
    
    **Admin only**
    
    - **email**: Valid email (required, max 255 chars)
    - **password**: User password (required, min 8 chars, max 128 chars)
    - **full_name**: Full name (required, max 255 chars)
    - **roles_id**: List of role UUIDs (required, at least one)
    """
    user_service = UserService(db)
    await user_service.create_user(user_data, current_user.id)
    return {"message": "User created successfully"}


@router.patch(
    "/{user_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "User updated successfully",
            "content": {
                "application/json": {
                    "example": {"message": "User info updated successfully"}
                }
            }
        },
        404: {
            "description": "User not found",
            "content": {
                "application/json": {
                    "example": {"message": "User not found"}
                }
            }
        }
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
    """
    Update user basic information
    
    **Admin only**
    
    - **email**: New email (optional, valid format, max 255 chars)
    - **full_name**: New full name (optional, max 255 chars)
    """
    user_service = UserService(db)
    await user_service.update_basic_info(user_id, update_data, current_user.id)
    return {"message": "User info updated successfully"}


@router.patch(
    "/{user_id}/password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Password updated",
            "content": {
                "application/json": {
                    "example": {"message": "User password updated successfully"}
                }
            }
        },
        404: {
            "description": "User not found",
            "content": {
                "application/json": {
                    "example": {"message": "User not found"}
                }
            }
        }
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
    """
    Update user password
    
    **Admin only**
    
    - **new_password**: New password (required, min 8 chars, max 128 chars)
    """
    user_service = UserService(db)
    await user_service.update_password(user_id, update_data, current_user.id)
    return {"message": "User password updated successfully"}


@router.patch(
    "/{user_id}/roles",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Roles updated",
            "content": {
                "application/json": {
                    "example": {"message": "User roles updated successfully"}
                }
            }
        },
        404: {
            "description": "User or role not found",
            "content": {
                "application/json": {
                    "example": {"message": "User not found"}
                }
            }
        },
        422: {
            "description": "Validation errors",
            "content": {
                "application/json": {
                    "example": {
                        "errors": {
                            "roles": "Choose at least one role"
                        }
                    }
                }
            }
        }
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
    """
    Update user roles
    
    **Admin only**
    
    - **roles_id**: List of role UUIDs (required, at least one)
    """
    user_service = UserService(db)
    await user_service.update_roles(user_id, update_data, current_user.id)
    return {"message": "User roles updated successfully"}


@router.patch(
    "/{user_id}/deactivate",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "User deactivated",
            "content": {
                "application/json": {
                    "example": {"message": "User deactivated successfully"}
                }
            }
        },
        400: {
            "description": "User already deactivated",
            "content": {
                "application/json": {
                    "example": {"message": "User is already deactivated"}
                }
            }
        },
        404: {
            "description": "User not found",
            "content": {
                "application/json": {
                    "example": {"message": "User not found"}
                }
            }
        }
    },
    summary="Deactivate User",
    description="Deactivates a user account. Admin only."
)
async def deactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Deactivate user
    
    **Admin only**
    
    Deactivates user account. User won't be able to login.
    """
    user_service = UserService(db)
    await user_service.deactivate_user(user_id, current_user.id)
    return {"message": "User deactivated successfully"}


@router.patch(
    "/{user_id}/activate",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "User activated",
            "content": {
                "application/json": {
                    "example": {"message": "User activated successfully"}
                }
            }
        },
        400: {
            "description": "User already active",
            "content": {
                "application/json": {
                    "example": {"message": "User is already active"}
                }
            }
        },
        404: {
            "description": "User not found",
            "content": {
                "application/json": {
                    "example": {"message": "User not found"}
                }
            }
        }
    },
    summary="Activate User",
    description="Reactivates a previously deactivated user account. Admin only."
)
async def activate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Activate user
    
    **Admin only**
    
    Reactivates previously deactivated user account.
    """
    user_service = UserService(db)
    await user_service.activate_user(user_id, current_user.id)
    return {"message": "User activated successfully"}


@router.get(
    "",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Users",
    description="Retrieves a list of users with optional filters. Admin only."
)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    role: Optional[str] = Query(None, description="Filter by role name"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    email_confirmed: Optional[bool] = Query(None, description="Filter by email confirmation"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    List users with filters
    
    **Admin only**
    
    - **page**: Page number (default: 1)
    - **limit**: Items per page (default: 10, max: 100)
    - **role**: Filter by role name (optional)
    - **is_active**: Filter by active status (optional)
    - **email_confirmed**: Filter by email confirmation (optional)
    """
    user_service = UserService(db)
    users, total = await user_service.list_users(
        page=page,
        limit=limit,
        role=role,
        is_active=is_active,
        email_confirmed=email_confirmed
    )
    
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "users": users
    }


@router.get(
    "/{user_id}/logs",
    response_model=UserLogsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "User not found",
            "content": {
                "application/json": {
                    "example": {"message": "User not found"}
                }
            }
        }
    },
    summary="View User Log",
    description="Retrieves audit logs for a specific user. Admin only."
)
async def get_user_logs(
    user_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get user audit logs
    
    **Admin only**
    
    - **user_id**: User UUID
    - **page**: Page number (default: 1)
    - **limit**: Items per page (default: 10, max: 100)
    
    Returns audit logs showing actions performed by or on this user.
    """
    user_service = UserService(db)
    logs, total = await user_service.get_user_logs(user_id, page, limit)
    
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "logs": logs
    }