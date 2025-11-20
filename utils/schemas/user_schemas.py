# utils/schemas/user_schemas.py
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class UserBase(BaseModel):
    """Base User schema"""
    email: EmailStr = Field(..., max_length=255)
    full_name: str = Field(..., max_length=255)


class UserCreate(BaseModel):
    """Create user schema"""
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., max_length=255)
    roles_id: List[UUID] = Field(..., min_items=1, description="List of role IDs")
    
    @field_validator('roles_id')
    @classmethod
    def validate_roles(cls, v: List[UUID]) -> List[UUID]:
        if not v or len(v) == 0:
            raise ValueError("Choose at least one role")
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "newuser@example.com",
                "password": "securepassword123",
                "full_name": "John Doe",
                "roles_id": ["uuid1", "uuid2"]
            }
        }
    )


class UserUpdateBasicInfo(BaseModel):
    """Update user basic info schema"""
    email: Optional[EmailStr] = Field(None, max_length=255)
    full_name: Optional[str] = Field(None, max_length=255)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "updateduser@example.com",
                "full_name": "John Doe Updated"
            }
        }
    )


class UserUpdatePassword(BaseModel):
    """Update user password schema"""
    new_password: str = Field(..., min_length=8, max_length=128)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "new_password": "newpassword123"
            }
        }
    )


class UserUpdateRoles(BaseModel):
    """Update user roles schema"""
    roles_id: List[UUID] = Field(..., min_items=1)
    
    @field_validator('roles_id')
    @classmethod
    def validate_roles(cls, v: List[UUID]) -> List[UUID]:
        if not v or len(v) == 0:
            raise ValueError("Choose at least one role")
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "roles_id": ["uuid1", "uuid2"]
            }
        }
    )


# ✅ Schema for updating own profile
class MyProfileUpdate(BaseModel):
    """Update my profile schema"""
    email: Optional[EmailStr] = Field(None, max_length=255)
    full_name: Optional[str] = Field(None, max_length=255, min_length=2)
    
    @field_validator('full_name')
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Full name must be at least 2 characters long")
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "newemail@example.com",
                "full_name": "Updated Name"
            }
        }
    )


# ✅ Schema for changing own password
class MyPasswordChange(BaseModel):
    """Change my password schema"""
    current_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str, info) -> str:
        # Check if new password is different from current
        if 'current_password' in info.data and v == info.data['current_password']:
            raise ValueError("New password must be different from current password")
        
        # Validate strength
        from utils.security import validate_password_strength
        is_valid, error_message = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_message)
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_password": "oldpassword123",
                "new_password": "newpassword123"
            }
        }
    )


# ✅ Bulk operations schema
class BulkUserOperation(BaseModel):
    """Bulk user operation schema"""
    user_ids: List[UUID] = Field(..., min_items=1, max_items=100, description="List of user IDs (max 100)")
    
    @field_validator('user_ids')
    @classmethod
    def validate_user_ids(cls, v: List[UUID]) -> List[UUID]:
        if not v or len(v) == 0:
            raise ValueError("At least one user ID is required")
        if len(v) > 100:
            raise ValueError("Maximum 100 users allowed per operation")
        # Remove duplicates
        return list(set(v))
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_ids": ["uuid1", "uuid2", "uuid3"]
            }
        }
    )


# ✅ Bulk operation response
class BulkOperationResponse(BaseModel):
    """Bulk operation response schema"""
    message: str
    total_requested: int
    successful: int
    failed: int
    errors: Optional[List[dict]] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Bulk operation completed",
                "total_requested": 10,
                "successful": 8,
                "failed": 2,
                "errors": [
                    {
                        "user_id": "uuid1",
                        "error": "User not found"
                    },
                    {
                        "user_id": "uuid2",
                        "error": "User is already deactivated"
                    }
                ]
            }
        }
    )


class UserResponse(BaseModel):
    """User response schema"""
    id: UUID
    email: EmailStr
    email_confirmed: bool
    full_name: str
    roles: List[str] = []
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "uuid1",
                "email": "user1@example.com",
                "email_confirmed": True,
                "full_name": "John Doe",
                "roles": ["Admin", "Tech User"],
                "is_active": True,
                "last_login": "2025-11-19T12:34:56Z",
                "created_at": "2025-11-01T09:00:00Z",
                "updated_at": "2025-11-15T14:00:00Z"
            }
        }
    )


class UserListResponse(BaseModel):
    """Paginated user list response"""
    page: int
    limit: int
    total: int
    users: List[UserResponse]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "page": 1,
                "limit": 10,
                "total": 2,
                "users": [
                    {
                        "id": "uuid1",
                        "email": "user1@example.com",
                        "email_confirmed": True,
                        "full_name": "John Doe",
                        "roles": ["Admin", "Tech User"],
                        "is_active": True,
                        "last_login": "2025-11-19T12:34:56Z",
                        "created_at": "2025-11-01T09:00:00Z",
                        "updated_at": "2025-11-15T14:00:00Z"
                    }
                ]
            }
        }
    )


# ✅ User statistics response
class UserStatistics(BaseModel):
    """User statistics schema"""
    total_users: int
    active_users: int
    inactive_users: int
    confirmed_emails: int
    unconfirmed_emails: int
    users_by_role: dict
    recent_registrations: int  # Last 7 days
    recent_logins: int  # Last 24 hours
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_users": 150,
                "active_users": 140,
                "inactive_users": 10,
                "confirmed_emails": 130,
                "unconfirmed_emails": 20,
                "users_by_role": {
                    "Admin": 5,
                    "Tech User": 50,
                    "Support User": 95
                },
                "recent_registrations": 12,
                "recent_logins": 85
            }
        }
    )


# ✅ User activity response
class UserActivity(BaseModel):
    """User activity schema"""
    id: UUID
    email: str
    full_name: str
    last_login: Optional[datetime]
    is_active: bool
    days_since_login: Optional[int]
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "uuid1",
                "email": "user@example.com",
                "full_name": "John Doe",
                "last_login": "2025-01-20T10:30:00Z",
                "is_active": True,
                "days_since_login": 2
            }
        }
    )


class UserActivityResponse(BaseModel):
    """User activity list response"""
    page: int
    limit: int
    total: int
    users: List[UserActivity]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "page": 1,
                "limit": 10,
                "total": 50,
                "users": [
                    {
                        "id": "uuid1",
                        "email": "user@example.com",
                        "full_name": "John Doe",
                        "last_login": "2025-01-20T10:30:00Z",
                        "is_active": True,
                        "days_since_login": 2
                    }
                ]
            }
        }
    )


class AuditLogResponse(BaseModel):
    """Audit log response schema"""
    id: UUID
    user_id: Optional[UUID] = None
    user_name: Optional[str] = None
    action_type: str
    target_table: str
    target_record_id: Optional[UUID]
    changed_values: Optional[dict]
    created_at: datetime
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "loguuid1",
                "user_id": "useruuid1",
                "user_name": "Admin User",
                "action_type": "UPDATE",
                "target_table": "users",
                "target_record_id": "useruuid2",
                "changed_values": {
                    "full_name": {
                        "old": "John Doe",
                        "new": "John Doe Updated"
                    }
                },
                "created_at": "2025-11-19T14:25:30Z"
            }
        }
    )


class UserLogsResponse(BaseModel):
    """User audit logs response"""
    page: int
    limit: int
    total: int
    logs: List[AuditLogResponse]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "page": 1,
                "limit": 10,
                "total": 2,
                "logs": [
                    {
                        "id": "loguuid1",
                        "user_id": "useruuid1",
                        "user_name": "Admin User",
                        "action_type": "UPDATE",
                        "target_table": "users",
                        "target_record_id": "useruuid2",
                        "changed_values": {
                            "full_name": {
                                "old": "John Doe",
                                "new": "John Doe Updated"
                            }
                        },
                        "created_at": "2025-11-19T14:25:30Z"
                    }
                ]
            }
        }
    )