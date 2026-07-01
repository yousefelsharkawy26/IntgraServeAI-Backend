# models/user.py
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid as UUID
from models.base import BaseModel, TimestampMixin
import uuid

# Many-to-Many relationship table
user_roles = Table(
    'user_roles',
    BaseModel.metadata,
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('assigned_at', DateTime(timezone=True), server_default='now()')
)


class Role(BaseModel):
    """Roles table"""
    __tablename__ = 'roles'
    
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Relationships
    users = relationship('User', secondary=user_roles, back_populates='roles')
    
    def __repr__(self):
        return f"<Role {self.name}>"


class User(BaseModel, TimestampMixin):
    """Users table"""
    __tablename__ = 'users'
    
    email = Column(String(255), unique=True, nullable=False, index=True)
    email_confirmed = Column(Boolean, default=False, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    roles = relationship('Role', secondary=user_roles, back_populates='users')
    assigned_tickets = relationship('Ticket', back_populates='assignee', foreign_keys='Ticket.assignee_id')
    audit_logs = relationship('AuditLog', back_populates='user')
    
    def __repr__(self):
        return f"<User {self.email}>"