from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
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