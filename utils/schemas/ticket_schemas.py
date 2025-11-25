# utils/schemas/ticket_schemas.py
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from models.ticket import TicketStatus, TicketPriority, TicketType, SenderType


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
    priority: TicketPriority = Field(
        ...,
        description="Ticket priority (required)"
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
                "priority": "high"
            }
        }
    )


class TicketStatusUpdate(BaseModel):
    """Update ticket status"""
    status: TicketStatus = Field(..., description="New ticket status")
    notes: Optional[str] = Field(None, max_length=1000, description="Optional notes for status change")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "in_progress",
                "notes": "Started working on this issue"
            }
        }
    )


class TicketReassign(BaseModel):
    """Reassign ticket - Toggle between Tech and Support"""
    reason: Optional[str] = Field(
        None, 
        max_length=500, 
        description="Reason for reassignment"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reason": "Escalating to technical team"
            }
        }
    )


class TicketResolve(BaseModel):
    """Resolve ticket"""
    resolution_notes: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Resolution notes"
    )
    
    @field_validator('resolution_notes')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resolution_notes": "Issue was caused by outdated browser cache. Customer cleared cache and the problem was resolved."
            }
        }
    )


class TicketCancel(BaseModel):
    """Cancel ticket"""
    cancellation_reason: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Reason for cancellation"
    )
    
    @field_validator('cancellation_reason')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "cancellation_reason": "Duplicate of ticket #12345"
            }
        }
    )


# ==================== Message Schemas ====================

class TicketMessageCreate(BaseModel):
    """Create a new message in ticket (Authenticated)"""
    message_text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Message text"
    )
    is_internal_note: bool = Field(
        False,
        description="Internal note (not visible to customer)"
    )
    
    @field_validator('message_text')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message_text": "I have checked the logs and found the issue. Working on a fix.",
                "is_internal_note": True
            }
        }
    )


class TicketMessageResponse(BaseModel):
    """Ticket message response"""
    id: UUID
    ticket_id: UUID
    sender_type: SenderType
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    message_text: str
    is_internal_note: bool
    attachments: Optional[dict] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class TicketMessagesListResponse(BaseModel):
    """List of ticket messages"""
    page: int
    limit: int
    total: int
    messages: List[TicketMessageResponse]
    
    model_config = ConfigDict(from_attributes=True)


# ==================== Response Schemas ====================

# ✅ Simplified response for lists (Admin All, My Tickets, Unassigned)
class TicketSimpleResponse(BaseModel):
    """Simplified ticket response for lists"""
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
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "ticket_type": "support",
                "title": "Cannot login to my account",
                "customer_email": "customer@example.com",
                "customer_name": "Ahmed Mohamed",
                "status": "open",
                "priority": "high",
                "assignee_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "assignee_name": "John Doe",
                "created_at": "2025-01-20T10:30:00Z"
            }
        }
    )


class TicketSimpleListResponse(BaseModel):
    """Paginated list of simplified tickets"""
    page: int
    limit: int
    total: int
    tickets: List[TicketSimpleResponse]
    
    model_config = ConfigDict(from_attributes=True)


# ✅ External customer simplified response
class ExternalTicketSimpleResponse(BaseModel):
    """Simplified ticket response for external customers"""
    id: UUID
    title: str
    status: TicketStatus
    priority: TicketPriority
    assignee_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "title": "Cannot login to my account",
                "status": "in_progress",
                "priority": "high",
                "assignee_name": "John Doe",
                "created_at": "2025-01-20T10:30:00Z",
                "updated_at": "2025-01-20T14:20:00Z"
            }
        }
    )


class ExternalTicketListResponse(BaseModel):
    """Paginated list of simplified tickets for external customers"""
    page: int
    limit: int
    total: int
    tickets: List[ExternalTicketSimpleResponse]
    
    model_config = ConfigDict(from_attributes=True)


# ✅ Full response for single ticket (user view)
class TicketResponse(BaseModel):
    """Standard ticket response for single ticket view"""
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


# ✅ Full detailed response for Admin single ticket view
class TicketDetailedResponse(BaseModel):
    """Detailed ticket information with ALL fields (Admin only)"""
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


class ExternalTicketCreateResponse(BaseModel):
    """Response after creating external ticket"""
    message: str
    ticket_id: UUID
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "message": "Ticket created successfully. We will reply as soon as possible.",
                "ticket_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
            }
        }
    )


class TicketMessageAddedResponse(BaseModel):
    """Response after adding message"""
    message: str
    message_id: UUID
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Message added successfully",
                "message_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
            }
        }
    )


class TicketAssignedResponse(BaseModel):
    """Response after assigning ticket"""
    message: str
    ticket_id: UUID
    assignee_name: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Ticket assigned to you successfully",
                "ticket_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "assignee_name": "John Doe"
            }
        }
    )


class TicketStatusUpdateResponse(BaseModel):
    """Response after updating ticket status"""
    message: str
    ticket_id: UUID
    old_status: TicketStatus
    new_status: TicketStatus
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Ticket status updated successfully",
                "ticket_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "old_status": "open",
                "new_status": "in_progress"
            }
        }
    )


class TicketReassignResponse(BaseModel):
    """Response after reassigning ticket"""
    message: str
    ticket_id: UUID
    new_ticket_type: TicketType
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "message": "Ticket transferred to Tech team (unassigned)",
                "ticket_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "new_ticket_type": "tech"
            }
        }
    )


class TicketResolvedResponse(BaseModel):
    """Response after resolving ticket"""
    message: str
    ticket_id: UUID
    resolved_at: datetime
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Ticket resolved successfully",
                "ticket_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "resolved_at": "2025-01-20T15:30:00Z"
            }
        }
    )


class TicketCanceledResponse(BaseModel):
    """Response after canceling ticket"""
    message: str
    ticket_id: UUID
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Ticket canceled successfully",
                "ticket_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
            }
        }
    )


class TicketClosedResponse(BaseModel):
    """Response after closing ticket"""
    message: str
    ticket_id: UUID
    closed_at: datetime
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Ticket closed successfully",
                "ticket_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "closed_at": "2025-01-20T16:00:00Z"
            }
        }
    )


class TicketDeletedResponse(BaseModel):
    """Response after deleting ticket"""
    message: str
    ticket_id: UUID
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Ticket deleted successfully",
                "ticket_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
            }
        }
    )


class FileUploadResponse(BaseModel):
    """File upload response"""
    filename: str
    file_path: str
    file_size: int
    content_type: str
    
    model_config = ConfigDict(from_attributes=True)


class TicketStatistics(BaseModel):
    """Ticket statistics for admin dashboard"""
    total_tickets: int
    open_tickets: int
    in_progress_tickets: int
    pending_tickets: int
    escalated_tickets: int
    resolved_tickets: int
    closed_tickets: int
    canceled_tickets: int
    
    # By Priority
    urgent_tickets: int
    high_priority_tickets: int
    medium_priority_tickets: int
    low_priority_tickets: int
    
    # By Type
    tech_tickets: int
    support_tickets: int
    
    # By Assignment
    assigned_tickets: int
    unassigned_tickets: int
    
    # SLA
    overdue_tickets: int
    due_soon_tickets: int
    
    # AI Stats
    ai_created_tickets: int
    manual_created_tickets: int
    
    # Averages
    avg_resolution_time_hours: Optional[float] = None
    avg_response_time_hours: Optional[float] = None
    
    # Recent Activity
    tickets_today: int
    tickets_this_week: int
    tickets_this_month: int
    
    model_config = ConfigDict(from_attributes=True)