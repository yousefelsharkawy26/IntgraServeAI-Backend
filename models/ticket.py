# models/ticket.py
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, Numeric, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid as UUID
from models.base import BaseModel, TimestampMixin, JSONVariant
import enum


class TicketType(str, enum.Enum):
    """Ticket Type Enum"""
    TECH = "tech"        # Technical/system issues
    SUPPORT = "support"  # Customer support


class TicketStatus(str, enum.Enum):
    """Ticket Status Enum"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"
    ESCALATED = "escalated"
    CANCELED = "canceled"


class TicketPriority(str, enum.Enum):
    """Ticket Priority Enum"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class SenderType(str, enum.Enum):
    """Sender Type Enum"""
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"
    AI = "ai"


class Ticket(BaseModel, TimestampMixin):
    """Tickets table"""
    __tablename__ = 'tickets'
    
    # Ticket Type
    ticket_type = Column(
        SQLEnum(TicketType), 
        nullable=False, 
        default=TicketType.SUPPORT,
        index=True
    )
    
    # Basic Information
    title = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=False)
    
    # Customer Information
    external_customer_id = Column(String(255), nullable=True, index=True)
    customer_email = Column(String(255), nullable=False, index=True)
    customer_name = Column(String(255), nullable=False)
    
    # AI Information
    ai_auto_created = Column(Boolean, default=False, nullable=False)
    ai_confidence = Column(Numeric(5, 2), nullable=True)  # 0.00 to 100.00
    
    # Status and Priority
    status = Column(SQLEnum(TicketStatus), default=TicketStatus.OPEN, nullable=False, index=True)
    priority = Column(SQLEnum(TicketPriority), default=TicketPriority.MEDIUM, nullable=False, index=True)
    
    # SLA and Closure
    sla_due_date = Column(DateTime(timezone=True), nullable=True, index=True)
    is_closed = Column(Boolean, default=False, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Resolution and Cancellation
    resolution_notes = Column(Text, nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    escalation_reason = Column(Text, nullable=True)
    
    # Assignment Tracking
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Foreign Keys
    assignee_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    previous_assignee_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    
    # Relationships
    assignee = relationship('User', back_populates='assigned_tickets', foreign_keys=[assignee_id])
    previous_assignee = relationship('User', foreign_keys=[previous_assignee_id])
    messages = relationship('TicketMessage', back_populates='ticket', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<Ticket {self.id}: {self.title}>"


class TicketMessage(BaseModel):
    """Ticket Messages table"""
    __tablename__ = 'ticket_messages'
    
    ticket_id = Column(UUID(as_uuid=True), ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False, index=True)
    sender_type = Column(SQLEnum(SenderType), nullable=False)
    sender_name = Column(String(255), nullable=True)
    sender_email = Column(String(255), nullable=True)
    message_text = Column(Text, nullable=False)
    is_internal_note = Column(Boolean, default=False, nullable=False)
    attachments = Column(JSONVariant, nullable=True)
    
    # Relationships
    ticket = relationship('Ticket', back_populates='messages')
    
    def __repr__(self):
        return f"<TicketMessage {self.id} for Ticket {self.ticket_id}>"