# models/__init__.py
from models.base import BaseModel
from models.user import User, Role, user_roles
from models.ticket import (
    Ticket, 
    TicketMessage, 
    TicketStatus, 
    TicketPriority, 
    TicketCategory, 
    TicketType,  # NEW
    SenderType
)
from models.chat import ChatConversation, ChatMessage, AgentRating, ResponseType
from models.system import SystemType, ActionProtocol, SystemAction, ActionExecutionLog
from models.auth import ApiAuthType, ApiAuthentication
from models.audit import AuditLog

__all__ = [
    # Base
    'BaseModel',
    
    # User models
    'User',
    'Role',
    'user_roles',
    
    # Ticket models
    'Ticket',
    'TicketMessage',
    'TicketStatus',
    'TicketPriority',
    'TicketCategory',
    'TicketType',  # NEW
    'SenderType',
    
    # Chat models
    'ChatConversation',
    'ChatMessage',
    'AgentRating',
    'ResponseType',
    
    # System models
    'SystemType',
    'ActionProtocol',
    'SystemAction',
    'ActionExecutionLog',
    
    # Auth models
    'ApiAuthType',
    'ApiAuthentication',
    
    # Audit
    'AuditLog',
]
