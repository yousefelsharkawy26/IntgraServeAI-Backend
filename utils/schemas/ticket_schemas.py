# utils/schemas/ticket_schemas.py
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from models.ticket import TicketStatus, TicketPriority, TicketCategory, TicketType


# ==================== Request Schemas ====================

class ExternalTicketCreate(BaseModel):
    """Schema for creating ticket from external system (no auth required)"""
    external_customer_id: Optional[str] = Field(
        None, 
        max_length=255, 
        description="Customer ID in external system"
    )
    customer_email: EmailStr = Field(
        ..., 
        description="Customer email address"
    )
    customer_name: str = Field(
        ..., 
        min_length=2, 
        max_length=255, 
        description="Customer full name"
    )
    title: str = Field(
        ..., 
        min_length=5, 
        max_length=500, 
        description="Ticket title/subject"
    )
    description: str = Field(
        ..., 
        min_length=10, 
        description="Detailed description of the issue"
    )
    priority: Optional[TicketPriority] = Field(
        TicketPriority.MEDIUM, 
        description="Ticket priority"
    )
    category: Optional[TicketCategory] = Field(
        None, 
        description="Ticket category"
    )
    
    @field_validator('title', 'description', 'customer_name')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove leading/trailing whitespace"""
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "external_customer_id": "CUST-12345",
                "customer_email": "customer@example.com",
                "customer_name": "Ahmed Mohamed",
                "title": "Cannot login to my account",
                "description": "I keep getting 'Invalid credentials' error when trying to login",
                "priority": "HIGH",
                "category": "TECHNICAL"
            }
        }
    )


# ==================== Response Schemas ====================

class TicketResponse(BaseModel):
    """Basic ticket information"""
    id: UUID
    ticket_type: TicketType
    title: str
    description: str
    customer_email: EmailStr
    customer_name: str
    external_customer_id: Optional[str]
    status: TicketStatus
    priority: TicketPriority
    category: Optional[TicketCategory]
    ai_auto_created: bool
    ai_confidence: Optional[float]
    sla_due_date: Optional[datetime]
    assignee_id: Optional[UUID]
    assignee_name: Optional[str] = None
    assigned_at: Optional[datetime]
    is_closed: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "ticket_type": "support",
                "title": "Cannot login",
                "description": "Getting invalid credentials error",
                "customer_email": "customer@example.com",
                "customer_name": "Ahmed Mohamed",
                "external_customer_id": "CUST-12345",
                "status": "OPEN",
                "priority": "HIGH",
                "category": "TECHNICAL",
                "ai_auto_created": False,
                "ai_confidence": None,
                "sla_due_date": "2025-01-23T10:00:00Z",
                "assignee_id": None,
                "assignee_name": None,
                "assigned_at": None,
                "is_closed": False,
                "created_at": "2025-01-22T10:00:00Z",
                "updated_at": "2025-01-22T10:00:00Z"
            }
        }
    )


class TicketListResponse(BaseModel):
    """Paginated list of tickets"""
    page: int
    limit: int
    total: int
    tickets: List[TicketResponse]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "page": 1,
                "limit": 10,
                "total": 25,
                "tickets": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "ticket_type": "support",
                        "title": "Cannot login",
                        "status": "OPEN",
                        "priority": "HIGH",
                        "customer_name": "Ahmed Mohamed",
                        "assignee_name": None,
                        "created_at": "2025-01-22T10:00:00Z"
                    }
                ]
            }
        }
    )


class ExternalTicketCreateResponse(BaseModel):
    """Response after creating external ticket"""
    message: str
    ticket_id: UUID
    status: TicketStatus
    estimated_response_time: Optional[str] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Ticket created successfully",
                "ticket_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "OPEN",
                "estimated_response_time": "4 hours"
            }
        }
    )