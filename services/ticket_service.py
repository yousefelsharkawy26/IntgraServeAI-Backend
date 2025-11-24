# services/ticket_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta, timezone

from models.ticket import Ticket, TicketStatus, TicketPriority, TicketType
from models.user import User
from models.audit import AuditLog
from utils.schemas.ticket_schemas import (
    ExternalTicketCreate,
    TicketResponse
)
from utils.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException
)
import logging

logger = logging.getLogger(__name__)


class TicketService:
    """Service for ticket management"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ==================== External Ticket Creation ====================
    
    async def create_external_ticket(
        self,
        ticket_data: ExternalTicketCreate
    ) -> Tuple[Ticket, str]:
        """
        Create ticket from external system (no authentication required)
        
        Args:
            ticket_data: Ticket creation data from external system
            
        Returns:
            Tuple of (Ticket object, estimated_response_time)
        """
        now = datetime.now(timezone.utc)
        
        # Calculate SLA due date based on priority
        sla_hours = self._get_sla_hours(ticket_data.priority)
        sla_due_date = now + timedelta(hours=sla_hours)
        
        # Create ticket
        ticket = Ticket(
            ticket_type=TicketType.SUPPORT,  # External tickets are always SUPPORT
            title=ticket_data.title,
            description=ticket_data.description,
            external_customer_id=ticket_data.external_customer_id,
            customer_email=ticket_data.customer_email,
            customer_name=ticket_data.customer_name,
            priority=ticket_data.priority,
            category=ticket_data.category,
            status=TicketStatus.OPEN,
            ai_auto_created=False,  # Created by external system, not AI
            sla_due_date=sla_due_date,
            is_closed=False,
            is_active=True,
            created_at=now,
            updated_at=now
        )
        
        self.db.add(ticket)
        await self.db.commit()
        await self.db.refresh(ticket)
        
        logger.info(f"External ticket created: {ticket.id} for {ticket.customer_email}")
        
        # Return estimated response time
        estimated_time = f"{sla_hours} hours"
        
        return ticket, estimated_time
    
    # ==================== My Tickets ====================
    
    async def get_my_tickets(
        self,
        current_user_id: UUID,
        user_roles: List[str],
        page: int = 1,
        limit: int = 10
    ) -> Tuple[List[TicketResponse], int]:
        """
        Get tickets assigned to current user
        
        Args:
            current_user_id: ID of current user
            user_roles: List of user role names
            page: Page number
            limit: Items per page
            
        Returns:
            Tuple of (list of tickets, total count)
        """
        # Base query: tickets assigned to me
        query = select(Ticket).options(
            selectinload(Ticket.assignee)
        ).where(
            Ticket.assignee_id == current_user_id,
            Ticket.is_active == True
        )
        
        # Filter by ticket type based on role
        if "Admin" not in user_roles:
            if "Tech User" in user_roles:
                query = query.where(Ticket.ticket_type == TicketType.TECH)
            elif "Support User" in user_roles:
                query = query.where(Ticket.ticket_type == TicketType.SUPPORT)
        
        # Get total count
        count_query = select(func.count()).select_from(Ticket).where(
            Ticket.assignee_id == current_user_id,
            Ticket.is_active == True
        )
        if "Admin" not in user_roles:
            if "Tech User" in user_roles:
                count_query = count_query.where(Ticket.ticket_type == TicketType.TECH)
            elif "Support User" in user_roles:
                count_query = count_query.where(Ticket.ticket_type == TicketType.SUPPORT)
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination and sorting
        offset = (page - 1) * limit
        query = query.order_by(Ticket.created_at.desc()).offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        tickets = result.scalars().all()
        
        # Convert to response format
        ticket_responses = self._convert_to_responses(tickets)
        
        return ticket_responses, total
    
    # ==================== Unassigned Tickets ====================
    
    async def get_unassigned_tickets(
        self,
        user_roles: List[str],
        page: int = 1,
        limit: int = 10
    ) -> Tuple[List[TicketResponse], int]:
        """
        Get unassigned tickets based on user role
        
        Args:
            user_roles: List of user role names
            page: Page number
            limit: Items per page
            
        Returns:
            Tuple of (list of tickets, total count)
        """
        # Base query: unassigned tickets
        query = select(Ticket).where(
            Ticket.assignee_id == None,
            Ticket.status == TicketStatus.OPEN,
            Ticket.is_active == True
        )
        
        # Filter by ticket type based on role
        if "Admin" not in user_roles:
            if "Tech User" in user_roles:
                query = query.where(Ticket.ticket_type == TicketType.TECH)
            elif "Support User" in user_roles:
                query = query.where(Ticket.ticket_type == TicketType.SUPPORT)
        
        # Get total count
        count_query = select(func.count()).select_from(Ticket).where(
            Ticket.assignee_id == None,
            Ticket.status == TicketStatus.OPEN,
            Ticket.is_active == True
        )
        if "Admin" not in user_roles:
            if "Tech User" in user_roles:
                count_query = count_query.where(Ticket.ticket_type == TicketType.TECH)
            elif "Support User" in user_roles:
                count_query = count_query.where(Ticket.ticket_type == TicketType.SUPPORT)
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination and sorting (priority first, then date)
        offset = (page - 1) * limit
        query = query.order_by(
            Ticket.priority.desc(),
            Ticket.created_at.asc()
        ).offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        tickets = result.scalars().all()
        
        # Convert to response format
        ticket_responses = self._convert_to_responses(tickets)
        
        return ticket_responses, total
    
    # ==================== Assign to Me ====================
    
    async def assign_to_me(
        self,
        ticket_id: UUID,
        current_user_id: UUID,
        user_roles: List[str]
    ) -> Ticket:
        """
        Self-assign an unassigned ticket
        
        Args:
            ticket_id: ID of ticket to assign
            current_user_id: ID of current user
            user_roles: List of user role names
            
        Returns:
            Updated Ticket object
            
        Raises:
            NotFoundException: If ticket not found
            BadRequestException: If ticket cannot be assigned
            ConflictException: If ticket already assigned
        """
        # Get ticket with lock (for atomic update - prevent race condition)
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .with_for_update()
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            raise NotFoundException("Ticket not found")
        
        if not ticket.is_active:
            raise BadRequestException("Ticket is not active")
        
        # Check if already assigned
        if ticket.assignee_id is not None:
            # Get assignee name
            assignee_result = await self.db.execute(
                select(User).where(User.id == ticket.assignee_id)
            )
            assignee = assignee_result.scalar_one_or_none()
            assignee_name = assignee.full_name if assignee else "another user"
            
            raise ConflictException(f"Ticket already assigned to {assignee_name}")
        
        # Check if status allows assignment
        if ticket.status != TicketStatus.OPEN:
            raise BadRequestException(f"Cannot assign ticket with status: {ticket.status}")
        
        # Validate ticket type matches user role
        if "Admin" not in user_roles:
            if "Tech User" in user_roles and ticket.ticket_type != TicketType.TECH:
                raise BadRequestException("Tech Users can only assign TECH tickets")
            elif "Support User" in user_roles and ticket.ticket_type != TicketType.SUPPORT:
                raise BadRequestException("Support Users can only assign SUPPORT tickets")
        
        # Assign ticket
        now = datetime.now(timezone.utc)
        ticket.assignee_id = current_user_id
        ticket.assigned_at = now
        ticket.status = TicketStatus.IN_PROGRESS
        ticket.updated_at = now
        
        # Create audit log
        await self._create_audit_log(
            user_id=current_user_id,
            action_type="ASSIGN_TO_SELF",
            target_table="tickets",
            target_record_id=ticket.id,
            changed_values={
                "assignee_id": {"old": None, "new": str(current_user_id)},
                "status": {"old": "OPEN", "new": "IN_PROGRESS"}
            }
        )
        
        await self.db.commit()
        await self.db.refresh(ticket)
        
        # Load assignee relationship
        result = await self.db.execute(
            select(Ticket)
            .options(selectinload(Ticket.assignee))
            .where(Ticket.id == ticket.id)
        )
        ticket = result.scalar_one()
        
        logger.info(f"Ticket {ticket.id} assigned to user {current_user_id}")
        
        return ticket
    
    # ==================== Helper Methods ====================
    
    def _get_sla_hours(self, priority: TicketPriority) -> int:
        """
        Calculate SLA hours based on priority
        
        Args:
            priority: Ticket priority
            
        Returns:
            Number of hours for SLA
        """
        sla_map = {
            TicketPriority.URGENT: 1,
            TicketPriority.HIGH: 4,
            TicketPriority.MEDIUM: 12,
            TicketPriority.LOW: 24
        }
        return sla_map.get(priority, 12)
    
    def _convert_to_responses(self, tickets: List[Ticket]) -> List[TicketResponse]:
        """
        Convert Ticket models to TicketResponse schemas
        
        Args:
            tickets: List of Ticket objects
            
        Returns:
            List of TicketResponse schemas
        """
        responses = []
        for ticket in tickets:
            ticket_dict = {
                "id": ticket.id,
                "ticket_type": ticket.ticket_type,
                "title": ticket.title,
                "description": ticket.description,
                "customer_email": ticket.customer_email,
                "customer_name": ticket.customer_name,
                "external_customer_id": ticket.external_customer_id,
                "status": ticket.status,
                "priority": ticket.priority,
                "category": ticket.category,
                "ai_auto_created": ticket.ai_auto_created,
                "ai_confidence": float(ticket.ai_confidence) if ticket.ai_confidence else None,
                "sla_due_date": ticket.sla_due_date,
                "assignee_id": ticket.assignee_id,
                "assignee_name": ticket.assignee.full_name if ticket.assignee else None,
                "assigned_at": ticket.assigned_at,
                "is_closed": ticket.is_closed,
                "created_at": ticket.created_at,
                "updated_at": ticket.updated_at
            }
            responses.append(TicketResponse(**ticket_dict))
        
        return responses
    
    async def _create_audit_log(
        self,
        user_id: UUID,
        action_type: str,
        target_table: str,
        target_record_id: UUID,
        changed_values: dict
    ) -> None:
        """
        Create audit log entry
        
        Args:
            user_id: ID of user performing action
            action_type: Type of action
            target_table: Table name
            target_record_id: ID of record being modified
            changed_values: Dictionary of changed values
        """
        audit_log = AuditLog(
            user_id=user_id,
            action_type=action_type,
            target_table=target_table,
            target_record_id=target_record_id,
            changed_values=changed_values,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(audit_log)