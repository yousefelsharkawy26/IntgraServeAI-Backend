# utils/schemas/role_schemas.py
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class RoleBase(BaseModel):
    """Base Role schema"""
    name: str = Field(..., max_length=100)
    description: Optional[str] = None


class RoleResponse(RoleBase):
    """Role response schema"""
    id: UUID
    created_at: datetime
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "uuid1",
                "name": "Admin",
                "description": "Administrator with full access",
                "created_at": "2025-01-01T09:00:00Z"
            }
        }
    )


class RoleUpdate(BaseModel):
    """Update role schema"""
    name: Optional[str] = Field(None, max_length=100, min_length=2)
    description: Optional[str] = Field(None, max_length=500)
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Role name must be at least 2 characters long")
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Super Admin",
                "description": "Super administrator with extended permissions"
            }
        }
    )


class RoleListResponse(BaseModel):
    """List of roles response"""
    roles: list[RoleResponse]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "roles": [
                    {
                        "id": "uuid1",
                        "name": "Admin",
                        "description": "Administrator with full access",
                        "created_at": "2025-01-01T09:00:00Z"
                    }
                ]
            }
        }
    )


class RoleSimple(BaseModel):
    """Simple role schema with id and name only"""
    id: UUID
    name: str
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "uuid1",
                "name": "Admin"
            }
        }
    )


class UserRolesResponse(BaseModel):
    """User roles response schema"""
    roles: List[RoleSimple]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "roles": [
                    {
                        "id": "uuid1",
                        "name": "Admin"
                    },
                    {
                        "id": "uuid2",
                        "name": "Tech User"
                    }
                ]
            }
        }
    )


# ✅ Role statistics response
class RoleStatistics(BaseModel):
    """Role statistics schema"""
    total_roles: int
    roles: List[dict]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_roles": 3,
                "roles": [
                    {
                        "id": "uuid1",
                        "name": "Admin",
                        "description": "Administrator",
                        "user_count": 5,
                        "active_users": 5,
                        "inactive_users": 0
                    },
                    {
                        "id": "uuid2",
                        "name": "Tech User",
                        "description": "Technical Support",
                        "user_count": 50,
                        "active_users": 48,
                        "inactive_users": 2
                    }
                ]
            }
        }
    )