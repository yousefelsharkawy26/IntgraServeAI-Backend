# utils/schemas/ticket_schemas.py
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List, Any, Dict
from datetime import datetime
from uuid import UUID
from models.ticket import TicketStatus, TicketPriority, TicketType, SenderType


# ==================== Request Schemas ====================

class ExternalTicketCreate(BaseModel):
    """Create ticket from external system"""
    external_customer_id: Optional[str] = Field(None, max_length=255)
    customer_email: EmailStr = Field(..., description="Customer email")
    customer_name: str = Field(..., min_length=2, max_length=255)
    title: str = Field(..., min_length=5, max_length=500)
    description: str = Field(..., min_length=10)
    priority: TicketPriority = Field(..., description="Priority level")
    
    @field_validator('title', 'description', 'customer_name')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "external_customer_id": "CUST-12345",
                "customer_email": "customer@example.com",
                "customer_name": "Ahmed Mohamed",
                "title": "Cannot login to my account",
                "description": "I keep getting 'Invalid credentials' error",
                "priority": "high"
            }
        }
    )


class TicketStatusUpdate(BaseModel):
    """Update ticket status"""
    status: TicketStatus = Field(...)
    notes: Optional[str] = Field(None, max_length=1000)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "in_progress",
                "notes": "Started working on this"
            }
        }
    )


class TicketReassign(BaseModel):
    """Reassign ticket"""
    reason: Optional[str] = Field(None, max_length=500)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"reason": "Escalating to technical team"}
        }
    )


class TicketResolve(BaseModel):
    """Resolve ticket"""
    resolution_notes: str = Field(..., min_length=10, max_length=2000)
    
    @field_validator('resolution_notes')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"resolution_notes": "Issue resolved by clearing cache"}
        }
    )


class TicketCancel(BaseModel):
    """Cancel ticket"""
    cancellation_reason: str = Field(..., min_length=5, max_length=500)
    
    @field_validator('cancellation_reason')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"cancellation_reason": "Duplicate ticket"}
        }
    )


# ==================== Attachment Schema ====================

class AttachmentInfo(BaseModel):
    """Attachment information"""
    filename: str
    file_path: str
    file_size: int
    content_type: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filename": "screenshot.png",
                "file_path": "uploads/tickets/uuid/messages/123_screenshot.png",
                "file_size": 245678,
                "content_type": "image/png"
            }
        }
    )


# ==================== Message Schemas ====================

class TicketMessageResponse(BaseModel):
    """Ticket message response"""
    id: UUID
    ticket_id: UUID
    sender_type: SenderType
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    message_text: str
    is_internal_note: bool
    attachments: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class TicketMessagesListResponse(BaseModel):
    """List of ticket messages"""
    page: int
    limit: int
    total: int
    messages: List[TicketMessageResponse]


# ==================== Ticket Response Schemas ====================

class TicketSimpleResponse(BaseModel):
    """Simplified ticket for lists"""
    id: UUID
    ticket_type: TicketType
    title: str
    customer_email: EmailStr
    customer_name: str
    status: TicketStatus
    priority: TicketPriority
    assignee_id: Optional[UUID] = None
    assignee_name: Optional[str] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class TicketSimpleListResponse(BaseModel):
    """Paginated list of tickets"""
    page: int
    limit: int
    total: int
    tickets: List[TicketSimpleResponse]


class ExternalTicketSimpleResponse(BaseModel):
    """Simplified ticket for external customers"""
    id: UUID
    title: str
    status: TicketStatus
    priority: TicketPriority
    assignee_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ExternalTicketListResponse(BaseModel):
    """Paginated list for external customers"""
    page: int
    limit: int
    total: int
    tickets: List[ExternalTicketSimpleResponse]


class TicketResponse(BaseModel):
    """Standard ticket response"""
    id: UUID
    ticket_type: TicketType
    title: str
    description: str
    customer_email: EmailStr
    customer_name: str
    external_customer_id: Optional[str] = None
    status: TicketStatus
    priority: TicketPriority
    ai_auto_created: bool
    ai_confidence: Optional[float] = None
    sla_due_date: Optional[datetime] = None
    assignee_id: Optional[UUID] = None
    assignee_name: Optional[str] = None
    assigned_at: Optional[datetime] = None
    is_closed: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class TicketDetailedResponse(BaseModel):
    """Detailed ticket response (Admin)"""
    id: UUID
    ticket_type: TicketType
    title: str
    description: str
    customer_email: EmailStr
    customer_name: str
    external_customer_id: Optional[str] = None
    status: TicketStatus
    priority: TicketPriority
    ai_auto_created: bool
    ai_confidence: Optional[float] = None
    sla_due_date: Optional[datetime] = None
    assignee_id: Optional[UUID] = None
    assignee_name: Optional[str] = None
    assigned_at: Optional[datetime] = None
    previous_assignee_id: Optional[UUID] = None
    is_closed: bool
    is_active: bool
    closed_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    cancellation_reason: Optional[str] = None
    escalation_reason: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# ==================== Action Response Schemas ====================

class ExternalTicketCreateResponse(BaseModel):
    """Response after creating ticket"""
    message: str
    ticket_id: UUID


class TicketMessageAddedResponse(BaseModel):
    """Response after adding message"""
    message: str
    message_id: UUID


class TicketAssignedResponse(BaseModel):
    """Response after assigning"""
    message: str
    ticket_id: UUID
    assignee_name: str


class TicketStatusUpdateResponse(BaseModel):
    """Response after status update"""
    message: str
    ticket_id: UUID
    old_status: TicketStatus
    new_status: TicketStatus


class TicketReassignResponse(BaseModel):
    """Response after reassign"""
    message: str
    ticket_id: UUID
    new_ticket_type: TicketType


class TicketResolvedResponse(BaseModel):
    """Response after resolve"""
    message: str
    ticket_id: UUID
    resolved_at: datetime


class TicketCanceledResponse(BaseModel):
    """Response after cancel"""
    message: str
    ticket_id: UUID


class TicketClosedResponse(BaseModel):
    """Response after close"""
    message: str
    ticket_id: UUID
    closed_at: datetime


class TicketDeletedResponse(BaseModel):
    """Response after delete"""
    message: str
    ticket_id: UUID


# ==================== Statistics ====================

class TicketStatistics(BaseModel):
    """Ticket statistics"""
    total_tickets: int
    open_tickets: int
    in_progress_tickets: int
    pending_tickets: int
    escalated_tickets: int
    resolved_tickets: int
    closed_tickets: int
    canceled_tickets: int
    urgent_tickets: int
    high_priority_tickets: int
    medium_priority_tickets: int
    low_priority_tickets: int
    tech_tickets: int
    support_tickets: int
    assigned_tickets: int
    unassigned_tickets: int
    overdue_tickets: int
    due_soon_tickets: int
    ai_created_tickets: int
    manual_created_tickets: int
    avg_resolution_time_hours: Optional[float] = None
    avg_response_time_hours: Optional[float] = None
    tickets_today: int
    tickets_this_week: int
    tickets_this_month: int
    
    model_config = ConfigDict(from_attributes=True)