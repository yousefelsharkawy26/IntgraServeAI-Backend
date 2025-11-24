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
    """Reassign ticket to role (escalate)"""
    role_id: UUID = Field(
        ..., 
        description="Role ID to escalate to"
    )
    reason: Optional[str] = Field(
        None, 
        max_length=500, 
        description="Reason for reassignment"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role_id": "123e4567-e89b-12d3-a456-426614174000",
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


class ExternalMessageCreate(BaseModel):
    """Create message from external customer (no auth)"""
    customer_email: EmailStr = Field(
        ...,
        description="Customer email (must match ticket owner)"
    )
    customer_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Customer name"
    )
    message_text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Message text"
    )
    
    @field_validator('message_text', 'customer_name')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customer_email": "customer@example.com",
                "customer_name": "Ahmed Mohamed",
                "message_text": "I tried clearing the cache but still having the same issue."
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

class TicketResponse(BaseModel):
    """Basic ticket information"""
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


class TicketListResponse(BaseModel):
    """Paginated list of tickets"""
    page: int
    limit: int
    total: int
    tickets: List[TicketResponse]
    
    model_config = ConfigDict(from_attributes=True)


class ExternalTicketCreateResponse(BaseModel):
    """Response after creating external ticket"""
    message: str
    ticket_id: UUID
    
    model_config = ConfigDict(from_attributes=True)


class ExternalMessageWithFilesResponse(BaseModel):
    """Response after creating external message with files"""
    message: str
    attachments: Optional[List[dict]] = None
    
    model_config = ConfigDict(from_attributes=True)


class FileUploadResponse(BaseModel):
    """File upload response"""
    filename: str
    file_path: str
    file_size: int
    content_type: str
    
    model_config = ConfigDict(from_attributes=True)


class TicketSummaryResponse(BaseModel):
    """Simplified ticket information for admin list"""
    id: UUID
    ticket_type: TicketType
    title: str
    status: TicketStatus
    priority: TicketPriority
    customer_name: str
    assignee_id: Optional[UUID] = None
    assignee_name: Optional[str] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class TicketSummaryListResponse(BaseModel):
    """Paginated list of simplified tickets"""
    page: int
    limit: int
    total: int
    tickets: List[TicketSummaryResponse]
    
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