# models/audit.py
from sqlalchemy import Column, String, Text, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid as UUID
from models.base import BaseModel, JSONVariant
import enum


class AuditLog(BaseModel):
    """Audit Logs table"""
    __tablename__ = 'audit_logs'
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    action_type = Column(String(100), nullable=False, index=True)  # CREATE, UPDATE, DELETE, LOGIN, etc.
    target_table = Column(String(100), nullable=False, index=True)  # Table name
    target_record_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Record ID
    changed_values = Column(JSONVariant, nullable=True)  # Store old and new values
    
    # Relationships
    user = relationship('User', back_populates='audit_logs')
    
    def __repr__(self):
        return f"<AuditLog {self.action_type} on {self.target_table}>"