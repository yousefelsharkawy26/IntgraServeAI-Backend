from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from utils.schemas.role_schemas import RoleResponse


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


class UserResponse(UserBase):
    """User response schema"""
    id: UUID
    email_confirmed: bool
    is_active: bool
    roles: List[RoleResponse] = []
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
                "roles": [
                    {
                        "id": "uuid1",
                        "name": "Admin",
                        "description": "Administrator",
                        "created_at": "2025-01-01T09:00:00Z"
                    }
                ],
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
                        "roles": [{"id": "uuid1", "name": "Admin", "description": "Administrator", "created_at": "2025-01-01T09:00:00Z"}],
                        "is_active": True,
                        "last_login": "2025-11-19T12:34:56Z",
                        "created_at": "2025-11-01T09:00:00Z",
                        "updated_at": "2025-11-15T14:00:00Z"
                    }
                ]
            }
        }
    )


class AuditLogResponse(BaseModel):
    """Audit log response schema"""
    id: UUID
    action_type: str
    target_table: str
    target_record_id: Optional[UUID]
    changed_values: Optional[dict]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


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
                        "action_type": "UPDATE",
                        "target_table": "users",
                        "target_record_id": "useruuid1",
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