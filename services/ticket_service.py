# services/ticket_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta, timezone

from models.ticket import Ticket, TicketStatus, TicketPriority, TicketType, TicketMessage, SenderType
from models.user import User, Role
from models.audit import AuditLog
from utils.schemas.ticket_schemas import TicketResponse
from utils.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException
)
from utils.email_service import email_service
import logging

logger = logging.getLogger(__name__)


class TicketService:
    """Service for ticket management"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ==================== External Ticket Creation ====================
    
    async def create_external_ticket(
        self,
        ticket_data
    ) -> Ticket:
        """Create ticket from external system (no authentication required)"""
        now = datetime.now(timezone.utc)
        
        # Calculate SLA due date based on priority
        sla_hours = self._get_sla_hours(ticket_data.priority)
        sla_due_date = now + timedelta(hours=sla_hours)
        
        # Create ticket
        ticket = Ticket(
            ticket_type=TicketType.SUPPORT,
            title=ticket_data.title,
            description=ticket_data.description,
            external_customer_id=ticket_data.external_customer_id,
            customer_email=ticket_data.customer_email,
            customer_name=ticket_data.customer_name,
            priority=ticket_data.priority,
            status=TicketStatus.OPEN,
            ai_auto_created=False,
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
        
        return ticket
    
    # ==================== My Tickets with Filters & Sort ====================
    
    async def get_my_tickets(
        self,
        current_user_id: UUID,
        user_roles: List[str],
        page: int = 1,
        limit: int = 10,
        status: Optional[TicketStatus] = None,
        priority: Optional[TicketPriority] = None,
        ticket_type: Optional[TicketType] = None,
        sort_by: str = "created_at",
        search: Optional[str] = None
    ) -> Tuple[List[TicketResponse], int]:
        """Get tickets assigned to current user with filters"""
        # Base query
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
        
        # Apply filters
        if status:
            query = query.where(Ticket.status == status)
        
        if priority:
            query = query.where(Ticket.priority == priority)
        
        if ticket_type:
            query = query.where(Ticket.ticket_type == ticket_type)
        
        # Apply search
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Ticket.title.ilike(search_term),
                    Ticket.description.ilike(search_term),
                    Ticket.customer_name.ilike(search_term),
                    Ticket.customer_email.ilike(search_term)
                )
            )
        
        # Count query
        count_query = select(func.count()).select_from(Ticket).where(
            Ticket.assignee_id == current_user_id,
            Ticket.is_active == True
        )
        
        if "Admin" not in user_roles:
            if "Tech User" in user_roles:
                count_query = count_query.where(Ticket.ticket_type == TicketType.TECH)
            elif "Support User" in user_roles:
                count_query = count_query.where(Ticket.ticket_type == TicketType.SUPPORT)
        
        if status:
            count_query = count_query.where(Ticket.status == status)
        if priority:
            count_query = count_query.where(Ticket.priority == priority)
        if ticket_type:
            count_query = count_query.where(Ticket.ticket_type == ticket_type)
        if search:
            search_term = f"%{search}%"
            count_query = count_query.where(
                or_(
                    Ticket.title.ilike(search_term),
                    Ticket.description.ilike(search_term),
                    Ticket.customer_name.ilike(search_term),
                    Ticket.customer_email.ilike(search_term)
                )
            )
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply sorting
        sort_options = {
            "created_at": Ticket.created_at.desc(),
            "updated_at": Ticket.updated_at.desc(),
            "priority": Ticket.priority.desc(),
            "status": Ticket.status.asc(),
            "title": Ticket.title.asc()
        }
        sort_column = sort_options.get(sort_by, Ticket.created_at.desc())
        
        # Apply pagination and sorting
        offset = (page - 1) * limit
        query = query.order_by(sort_column).offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        tickets = result.scalars().all()
        
        # Convert to response format
        ticket_responses = self._convert_to_responses(tickets)
        
        return ticket_responses, total
    
    # ==================== Unassigned Tickets with Filters & Sort ====================
    
    async def get_unassigned_tickets(
        self,
        user_roles: List[str],
        page: int = 1,
        limit: int = 10,
        priority: Optional[TicketPriority] = None,
        ticket_type: Optional[TicketType] = None,
        sort_by: str = "priority",
        search: Optional[str] = None
    ) -> Tuple[List[TicketResponse], int]:
        """Get unassigned tickets with filters"""
        # Base query
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
        
        # Apply filters
        if priority:
            query = query.where(Ticket.priority == priority)
        
        if ticket_type:
            query = query.where(Ticket.ticket_type == ticket_type)
        
        # Apply search
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Ticket.title.ilike(search_term),
                    Ticket.description.ilike(search_term),
                    Ticket.customer_name.ilike(search_term)
                )
            )
        
        # Count query
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
        
        if priority:
            count_query = count_query.where(Ticket.priority == priority)
        if ticket_type:
            count_query = count_query.where(Ticket.ticket_type == ticket_type)
        if search:
            search_term = f"%{search}%"
            count_query = count_query.where(
                or_(
                    Ticket.title.ilike(search_term),
                    Ticket.description.ilike(search_term),
                    Ticket.customer_name.ilike(search_term)
                )
            )
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply sorting
        sort_options = {
            "priority": Ticket.priority.desc(),
            "created_at": Ticket.created_at.asc(),
            "title": Ticket.title.asc()
        }
        sort_column = sort_options.get(sort_by, Ticket.priority.desc())
        
        # Apply pagination and sorting
        offset = (page - 1) * limit
        query = query.order_by(sort_column, Ticket.created_at.asc()).offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        tickets = result.scalars().all()
        
        # Convert to response format
        ticket_responses = self._convert_to_responses(tickets)
        
        return ticket_responses, total
    
    # ==================== Admin - Get All Tickets with Filters & Sort ====================
    
    async def get_all_tickets_admin(
        self,
        page: int = 1,
        limit: int = 10,
        status: Optional[TicketStatus] = None,
        priority: Optional[TicketPriority] = None,
        ticket_type: Optional[TicketType] = None,
        is_closed: Optional[bool] = None,
        assignee_id: Optional[UUID] = None,
        sort_by: str = "created_at",
        search: Optional[str] = None
    ) -> Tuple[List[TicketResponse], int]:
        """Get all tickets (Admin only) with comprehensive filters"""
        # Base query
        query = select(Ticket).options(
            selectinload(Ticket.assignee)
        ).where(Ticket.is_active == True)
        
        # Apply filters
        if status:
            query = query.where(Ticket.status == status)
        
        if priority:
            query = query.where(Ticket.priority == priority)
        
        if ticket_type:
            query = query.where(Ticket.ticket_type == ticket_type)
        
        if is_closed is not None:
            query = query.where(Ticket.is_closed == is_closed)
        
        if assignee_id is not None:
            query = query.where(Ticket.assignee_id == assignee_id)
        
        # Apply search
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Ticket.title.ilike(search_term),
                    Ticket.description.ilike(search_term),
                    Ticket.customer_name.ilike(search_term),
                    Ticket.customer_email.ilike(search_term),
                    Ticket.external_customer_id.ilike(search_term)
                )
            )
        
        # Count query
        count_query = select(func.count()).select_from(Ticket).where(Ticket.is_active == True)
        
        if status:
            count_query = count_query.where(Ticket.status == status)
        if priority:
            count_query = count_query.where(Ticket.priority == priority)
        if ticket_type:
            count_query = count_query.where(Ticket.ticket_type == ticket_type)
        if is_closed is not None:
            count_query = count_query.where(Ticket.is_closed == is_closed)
        if assignee_id is not None:
            count_query = count_query.where(Ticket.assignee_id == assignee_id)
        if search:
            search_term = f"%{search}%"
            count_query = count_query.where(
                or_(
                    Ticket.title.ilike(search_term),
                    Ticket.description.ilike(search_term),
                    Ticket.customer_name.ilike(search_term),
                    Ticket.customer_email.ilike(search_term),
                    Ticket.external_customer_id.ilike(search_term)
                )
            )
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply sorting
        sort_options = {
            "created_at": Ticket.created_at.desc(),
            "updated_at": Ticket.updated_at.desc(),
            "priority": Ticket.priority.desc(),
            "status": Ticket.status.asc(),
            "title": Ticket.title.asc(),
            "customer_name": Ticket.customer_name.asc()
        }
        sort_column = sort_options.get(sort_by, Ticket.created_at.desc())
        
        # Apply pagination and sorting
        offset = (page - 1) * limit
        query = query.order_by(sort_column).offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        tickets = result.scalars().all()
        
        # Convert to response format
        ticket_responses = self._convert_to_responses(tickets)
        
        return ticket_responses, total
    
    # ==================== Get Ticket Details ====================
    
    async def get_ticket_details(
        self,
        ticket_id: UUID,
        current_user_id: UUID,
        user_roles: List[str]
    ) -> Ticket:
        """Get ticket details by ID"""
        # Get ticket with assignee
        result = await self.db.execute(
            select(Ticket)
            .options(selectinload(Ticket.assignee))
            .where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            raise NotFoundException("Ticket not found")
        
        # Validate access based on role
        if "Admin" not in user_roles:
            if "Tech User" in user_roles and ticket.ticket_type != TicketType.TECH:
                raise BadRequestException("Tech Users can only view TECH tickets")
            elif "Support User" in user_roles and ticket.ticket_type != TicketType.SUPPORT:
                raise BadRequestException("Support Users can only view SUPPORT tickets")
        
        return ticket
    
    # ==================== Get Ticket Details (Admin) ====================
    
    async def get_ticket_details_admin(
        self,
        ticket_id: UUID
    ) -> Ticket:
        """Get ticket details (Admin - no restrictions)"""
        result = await self.db.execute(
            select(Ticket)
            .options(selectinload(Ticket.assignee))
            .where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            raise NotFoundException("Ticket not found")
        
        return ticket
    
    # ==================== Assign to Me ====================
    
    async def assign_to_me(
        self,
        ticket_id: UUID,
        current_user_id: UUID,
        user_roles: List[str]
    ) -> Ticket:
        """Self-assign an unassigned ticket"""
        # Get ticket with lock
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
            assignee_result = await self.db.execute(
                select(User).where(User.id == ticket.assignee_id)
            )
            assignee = assignee_result.scalar_one_or_none()
            assignee_name = assignee.full_name if assignee else "another user"
            
            raise ConflictException(f"Ticket already assigned to {assignee_name}")
        
        # Check if status allows assignment
        if ticket.status != TicketStatus.OPEN:
            raise BadRequestException(f"Cannot assign ticket with status: {ticket.status.value}")
        
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
        
        # Send email notification
        try:
            email_service.send_ticket_assigned(
                to_email=ticket.customer_email,
                customer_name=ticket.customer_name,
                ticket_id=str(ticket.id),
                ticket_title=ticket.title,
                assignee_name=ticket.assignee.full_name
            )
        except Exception as e:
            logger.error(f"Failed to send assignment email: {str(e)}")
        
        return ticket
    
    # ==================== Update Ticket Status ====================
    
    async def update_ticket_status(
        self,
        ticket_id: UUID,
        new_status: TicketStatus,
        notes: Optional[str],
        current_user_id: UUID,
        user_roles: List[str]
    ) -> Ticket:
        """Update ticket status"""
        # Get ticket
        ticket = await self.get_ticket_details(ticket_id, current_user_id, user_roles)
        
        # Validate status transition
        self._validate_status_transition(ticket.status, new_status)
        
        # Validate user can modify this ticket
        if "Admin" not in user_roles:
            if ticket.assignee_id != current_user_id:
                raise BadRequestException("You can only update tickets assigned to you")
        
        # Update status
        old_status = ticket.status
        ticket.status = new_status
        ticket.updated_at = datetime.now(timezone.utc)
        
        # Create audit log
        changed_values = {
            "status": {"old": old_status.value, "new": new_status.value}
        }
        if notes:
            changed_values["notes"] = notes
        
        await self._create_audit_log(
            user_id=current_user_id,
            action_type="UPDATE_STATUS",
            target_table="tickets",
            target_record_id=ticket.id,
            changed_values=changed_values
        )
        
        await self.db.commit()
        await self.db.refresh(ticket)
        
        logger.info(f"Ticket {ticket.id} status updated from {old_status} to {new_status}")
        
        # Send email notification
        try:
            result = await self.db.execute(
                select(User).where(User.id == current_user_id)
            )
            user = result.scalar_one_or_none()
            updated_by = user.full_name if user else "Support Team"
            
            email_service.send_ticket_status_update(
                to_email=ticket.customer_email,
                customer_name=ticket.customer_name,
                ticket_id=str(ticket.id),
                ticket_title=ticket.title,
                old_status=old_status.value,
                new_status=new_status.value,
                updated_by=updated_by
            )
        except Exception as e:
            logger.error(f"Failed to send status update email: {str(e)}")
        
        return ticket
    
    # ==================== Reassign Ticket (by Role) ====================
    
    async def reassign_ticket_by_role(
        self,
        ticket_id: UUID,
        target_role: str,
        reason: Optional[str],
        current_user_id: UUID,
        user_roles: List[str]
    ) -> Ticket:
        """Reassign ticket to a role (escalate)"""
        # Get ticket
        ticket = await self.get_ticket_details(ticket_id, current_user_id, user_roles)
        
        # Validate ticket can be reassigned
        if ticket.is_closed:
            raise BadRequestException("Cannot reassign a closed ticket")
        
        if ticket.status == TicketStatus.CANCELED:
            raise BadRequestException("Cannot reassign a canceled ticket")
        
        # Validate user can reassign
        if "Admin" not in user_roles:
            if ticket.assignee_id != current_user_id:
                raise BadRequestException("You can only reassign tickets assigned to you")
        
        # Validate target role exists
        result = await self.db.execute(
            select(Role).where(Role.name == target_role)
        )
        role = result.scalar_one_or_none()
        
        if not role:
            raise NotFoundException(f"Role '{target_role}' not found")
        
        # Find active users with this role
        result = await self.db.execute(
            select(User)
            .join(User.roles)
            .where(Role.id == role.id, User.is_active == True)
            .order_by(func.random())
            .limit(1)
        )
        new_assignee = result.scalar_one_or_none()
        
        if not new_assignee:
            raise NotFoundException(f"No active users found with role '{target_role}'")
        
        # Validate ticket type matches role
        if target_role == "Tech User" and ticket.ticket_type != TicketType.TECH:
            raise BadRequestException("Cannot assign SUPPORT tickets to Tech User role")
        elif target_role == "Support User" and ticket.ticket_type != TicketType.SUPPORT:
            raise BadRequestException("Cannot assign TECH tickets to Support User role")
        
        # Update ticket
        old_assignee_id = ticket.assignee_id
        ticket.previous_assignee_id = old_assignee_id
        ticket.assignee_id = new_assignee.id
        ticket.assigned_at = datetime.now(timezone.utc)
        ticket.status = TicketStatus.ESCALATED
        ticket.escalation_reason = reason
        ticket.updated_at = datetime.now(timezone.utc)
        
        # Create audit log
        await self._create_audit_log(
            user_id=current_user_id,
            action_type="REASSIGN",
            target_table="tickets",
            target_record_id=ticket.id,
            changed_values={
                "assignee_id": {
                    "old": str(old_assignee_id) if old_assignee_id else None, 
                    "new": str(new_assignee.id)
                },
                "target_role": target_role,
                "new_assignee_name": new_assignee.full_name,
                "status": {"old": ticket.status.value, "new": TicketStatus.ESCALATED.value},
                "reason": reason
            }
        )
        
        await self.db.commit()
        await self.db.refresh(ticket)
        
        logger.info(f"Ticket {ticket.id} reassigned to role '{target_role}' - assigned to {new_assignee.full_name}")
        
        return ticket
    
    # ==================== Resolve Ticket ====================
    
    async def resolve_ticket(
        self,
        ticket_id: UUID,
        resolution_notes: str,
        current_user_id: UUID,
        user_roles: List[str]
    ) -> Ticket:
        """Resolve ticket"""
        # Get ticket
        ticket = await self.get_ticket_details(ticket_id, current_user_id, user_roles)
        
        # Validate ticket can be resolved
        if ticket.is_closed:
            raise BadRequestException("Ticket is already closed")
        
        if ticket.status == TicketStatus.CANCELED:
            raise BadRequestException("Cannot resolve a canceled ticket")
        
        if ticket.status == TicketStatus.RESOLVED:
            raise BadRequestException("Ticket is already resolved")
        
        # Validate user can resolve
        if "Admin" not in user_roles:
            if ticket.assignee_id != current_user_id:
                raise BadRequestException("You can only resolve tickets assigned to you")
        
        # Update ticket
        old_status = ticket.status
        ticket.status = TicketStatus.RESOLVED
        ticket.resolution_notes = resolution_notes
        ticket.resolved_at = datetime.now(timezone.utc)
        ticket.updated_at = datetime.now(timezone.utc)
        
        # Create audit log
        await self._create_audit_log(
            user_id=current_user_id,
            action_type="RESOLVE",
            target_table="tickets",
            target_record_id=ticket.id,
            changed_values={
                "status": {"old": old_status.value, "new": TicketStatus.RESOLVED.value},
                "resolution_notes": resolution_notes
            }
        )
        
        await self.db.commit()
        await self.db.refresh(ticket)
        
        logger.info(f"Ticket {ticket.id} resolved by user {current_user_id}")
        
        # Send email notification
        try:
            email_service.send_ticket_resolved(
                to_email=ticket.customer_email,
                customer_name=ticket.customer_name,
                ticket_id=str(ticket.id),
                ticket_title=ticket.title,
                resolution_notes=resolution_notes
            )
        except Exception as e:
            logger.error(f"Failed to send resolution email: {str(e)}")
        
        return ticket
    
    # ==================== Cancel Ticket ====================
    
    async def cancel_ticket(
        self,
        ticket_id: UUID,
        cancellation_reason: str,
        current_user_id: UUID,
        user_roles: List[str]
    ) -> Ticket:
        """Cancel ticket"""
        # Get ticket
        ticket = await self.get_ticket_details(ticket_id, current_user_id, user_roles)
        
        # Validate ticket can be canceled
        if ticket.is_closed:
            raise BadRequestException("Cannot cancel a closed ticket")
        
        if ticket.status == TicketStatus.CANCELED:
            raise BadRequestException("Ticket is already canceled")
        
        # Validate user can cancel
        if "Admin" not in user_roles:
            if ticket.assignee_id != current_user_id:
                raise BadRequestException("You can only cancel tickets assigned to you")
        
        # Update ticket
        old_status = ticket.status
        ticket.status = TicketStatus.CANCELED
        ticket.cancellation_reason = cancellation_reason
        ticket.updated_at = datetime.now(timezone.utc)
        
        # Create audit log
        await self._create_audit_log(
            user_id=current_user_id,
            action_type="CANCEL",
            target_table="tickets",
            target_record_id=ticket.id,
            changed_values={
                "status": {"old": old_status.value, "new": TicketStatus.CANCELED.value},
                "cancellation_reason": cancellation_reason
            }
        )
        
        await self.db.commit()
        await self.db.refresh(ticket)
        
        logger.info(f"Ticket {ticket.id} canceled by user {current_user_id}")
        
        return ticket
    
    # ==================== Close Ticket ====================
    
    async def close_ticket(
        self,
        ticket_id: UUID,
        current_user_id: UUID,
        user_roles: List[str]
    ) -> Ticket:
        """Close ticket (only if resolved)"""
        # Get ticket
        ticket = await self.get_ticket_details(ticket_id, current_user_id, user_roles)
        
        # Validate ticket can be closed
        if ticket.is_closed:
            raise BadRequestException("Ticket is already closed")
        
        if ticket.status != TicketStatus.RESOLVED:
            raise BadRequestException("Only resolved tickets can be closed")
        
        # Validate user can close
        if "Admin" not in user_roles:
            if ticket.assignee_id != current_user_id:
                raise BadRequestException("You can only close tickets assigned to you")
        
        # Update ticket
        ticket.status = TicketStatus.CLOSED
        ticket.is_closed = True
        ticket.closed_at = datetime.now(timezone.utc)
        ticket.updated_at = datetime.now(timezone.utc)
        
        # Create audit log
        await self._create_audit_log(
            user_id=current_user_id,
            action_type="CLOSE",
            target_table="tickets",
            target_record_id=ticket.id,
            changed_values={
                "status": {"old": TicketStatus.RESOLVED.value, "new": TicketStatus.CLOSED.value},
                "is_closed": {"old": False, "new": True}
            }
        )
        
        await self.db.commit()
        await self.db.refresh(ticket)
        
        logger.info(f"Ticket {ticket.id} closed by user {current_user_id}")
        
        return ticket
    
    # ==================== Get Ticket Messages ====================
    
    async def get_ticket_messages(
        self,
        ticket_id: UUID,
        current_user_id: UUID,
        user_roles: List[str],
        page: int = 1,
        limit: int = 20
    ) -> Tuple[List[TicketMessage], int]:
        """Get messages for a specific ticket"""
        # Verify user can access this ticket
        ticket = await self.get_ticket_details(ticket_id, current_user_id, user_roles)
        
        # Base query
        query = select(TicketMessage).where(
            TicketMessage.ticket_id == ticket_id
        )
        
        # Count query
        count_query = select(func.count()).select_from(TicketMessage).where(
            TicketMessage.ticket_id == ticket_id
        )
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination and sorting (oldest first - chronological order)
        offset = (page - 1) * limit
        query = query.order_by(TicketMessage.created_at.asc()).offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        messages = result.scalars().all()
        
        return messages, total
    
    # ==================== Create Ticket Message (Authenticated) ====================
    
    async def create_ticket_message(
        self,
        ticket_id: UUID,
        message_text: str,
        is_internal_note: bool,
        current_user_id: UUID,
        user_roles: List[str]
    ) -> TicketMessage:
        """Create a new message in ticket (authenticated)"""
        # Verify user can access this ticket
        ticket = await self.get_ticket_details(ticket_id, current_user_id, user_roles)
        
        # Check if ticket is closed or canceled
        if ticket.is_closed:
            raise BadRequestException("Cannot add messages to a closed ticket")
        
        if ticket.status == TicketStatus.CANCELED:
            raise BadRequestException("Cannot add messages to a canceled ticket")
        
        # Validate user can add message
        if "Admin" not in user_roles:
            if ticket.assignee_id != current_user_id:
                raise BadRequestException("You can only add messages to tickets assigned to you")
        
        # Get user info
        result = await self.db.execute(
            select(User).where(User.id == current_user_id)
        )
        user = result.scalar_one_or_none()
        
        # Create message
        now = datetime.now(timezone.utc)
        message = TicketMessage(
            ticket_id=ticket_id,
            sender_type=SenderType.AGENT,
            sender_name=user.full_name if user else "Support Agent",
            sender_email=user.email if user else None,
            message_text=message_text,
            is_internal_note=is_internal_note,
            attachments=None,
            created_at=now
        )
        
        self.db.add(message)
        
        # Update ticket updated_at
        ticket.updated_at = now
        
        await self.db.commit()
        await self.db.refresh(message)
        
        logger.info(f"Message added to ticket {ticket_id} by user {current_user_id}")
        
        # Send email notification (if not internal note)
        if not is_internal_note:
            try:
                email_service.send_new_message_notification(
                    to_email=ticket.customer_email,
                    customer_name=ticket.customer_name,
                    ticket_id=str(ticket.id),
                    ticket_title=ticket.title,
                    sender_name=message.sender_name,
                    message_text=message_text
                )
            except Exception as e:
                logger.error(f"Failed to send message notification email: {str(e)}")
        
        return message
    
    # ==================== Create External Message (Public) ====================
    
    async def create_external_message(
        self,
        ticket_id: UUID,
        customer_email: str,
        customer_name: str,
        message_text: str
    ) -> TicketMessage:
        """Create message from external customer (no auth required)"""
        # Get ticket
        result = await self.db.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            raise NotFoundException("Ticket not found")
        
        # Verify email matches ticket owner
        if ticket.customer_email.lower() != customer_email.lower():
            raise BadRequestException("Email does not match ticket owner")
        
        # Check if ticket is closed or canceled
        if ticket.is_closed:
            raise BadRequestException("Cannot add messages to a closed ticket")
        
        if ticket.status == TicketStatus.CANCELED:
            raise BadRequestException("Cannot add messages to a canceled ticket")
        
        # Create message
        now = datetime.now(timezone.utc)
        message = TicketMessage(
            ticket_id=ticket_id,
            sender_type=SenderType.CUSTOMER,
            sender_name=customer_name,
            sender_email=customer_email,
            message_text=message_text,
            is_internal_note=False,
            attachments=None,
            created_at=now
        )
        
        self.db.add(message)
        
        # Update ticket updated_at
        ticket.updated_at = now
        
        # If ticket was resolved, reopen it
        if ticket.status == TicketStatus.RESOLVED:
            ticket.status = TicketStatus.OPEN
            ticket.is_closed = False
        
        await self.db.commit()
        await self.db.refresh(message)
        
        logger.info(f"External message added to ticket {ticket_id} by {customer_email}")
        
        # Send email notification to assignee (if exists)
        if ticket.assignee_id:
            try:
                result = await self.db.execute(
                    select(User).where(User.id == ticket.assignee_id)
                )
                assignee = result.scalar_one_or_none()
                
                if assignee:
                    email_service.send_new_message_notification(
                        to_email=assignee.email,
                        customer_name=assignee.full_name,
                        ticket_id=str(ticket.id),
                        ticket_title=ticket.title,
                        sender_name=customer_name,
                        message_text=message_text
                    )
            except Exception as e:
                logger.error(f"Failed to send notification to assignee: {str(e)}")
        
        return message
    
    # ==================== External Customer - Get My Tickets ====================
    
    async def get_external_customer_tickets(
        self,
        customer_email: str,
        page: int = 1,
        limit: int = 10
    ) -> Tuple[List[TicketResponse], int]:
        """Get tickets for external customer by email (no auth required)"""
        # Query tickets for this customer email
        query = select(Ticket).options(
            selectinload(Ticket.assignee)
        ).where(
            Ticket.customer_email == customer_email,
            Ticket.is_active == True
        )
        
        # Count query
        count_query = select(func.count()).select_from(Ticket).where(
            Ticket.customer_email == customer_email,
            Ticket.is_active == True
        )
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination and sorting (newest first)
        offset = (page - 1) * limit
        query = query.order_by(Ticket.created_at.desc()).offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        tickets = result.scalars().all()
        
        # Convert to response format
        ticket_responses = self._convert_to_responses(tickets)
        
        return ticket_responses, total
    
    # ==================== External Customer - Get Messages ====================
    
    async def get_external_ticket_messages(
        self,
        ticket_id: UUID,
        customer_email: str,
        page: int = 1,
        limit: int = 20
    ) -> Tuple[List[TicketMessage], int]:
        """Get messages for external customer (no auth required)"""
        # Get ticket
        result = await self.db.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            raise NotFoundException("Ticket not found")
        
        # Verify email matches
        if ticket.customer_email.lower() != customer_email.lower():
            raise BadRequestException("Email does not match ticket owner")
        
        # Base query - exclude internal notes
        query = select(TicketMessage).where(
            TicketMessage.ticket_id == ticket_id,
            TicketMessage.is_internal_note == False
        )
        
        # Count query
        count_query = select(func.count()).select_from(TicketMessage).where(
            TicketMessage.ticket_id == ticket_id,
            TicketMessage.is_internal_note == False
        )
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination and sorting (oldest first)
        offset = (page - 1) * limit
        query = query.order_by(TicketMessage.created_at.asc()).offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        messages = result.scalars().all()
        
        return messages, total
    
    # ==================== Admin - Delete Ticket ====================
    
    async def delete_ticket_admin(
        self,
        ticket_id: UUID,
        deleted_by_user_id: UUID
    ) -> None:
        """Delete ticket (Admin only - soft delete by setting is_active = False)"""
        # Get ticket
        result = await self.db.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            raise NotFoundException("Ticket not found")
        
        # Soft delete
        ticket.is_active = False
        ticket.updated_at = datetime.now(timezone.utc)
        
        # Create audit log
        await self._create_audit_log(
            user_id=deleted_by_user_id,
            action_type="DELETE",
            target_table="tickets",
            target_record_id=ticket.id,
            changed_values={
                "is_active": {"old": True, "new": False},
                "deleted_at": datetime.now(timezone.utc).isoformat()
            }
        )
        
        await self.db.commit()
        
        logger.info(f"Ticket {ticket.id} deleted by admin {deleted_by_user_id}")
    
    # ==================== Admin - Get All Tickets (Simplified) ====================
    
    async def get_all_tickets_admin_summary(
        self,
        page: int = 1,
        limit: int = 10,
        status: Optional[TicketStatus] = None,
        priority: Optional[TicketPriority] = None,
        ticket_type: Optional[TicketType] = None,
        is_closed: Optional[bool] = None,
        assignee_id: Optional[UUID] = None,
        sort_by: str = "created_at",
        search: Optional[str] = None
    ) -> Tuple[List[dict], int]:
        """Get all tickets (Admin only) with simplified response"""
        # Base query
        query = select(Ticket).options(
            selectinload(Ticket.assignee)
        ).where(Ticket.is_active == True)
        
        # Apply filters
        if status:
            query = query.where(Ticket.status == status)
        if priority:
            query = query.where(Ticket.priority == priority)
        if ticket_type:
            query = query.where(Ticket.ticket_type == ticket_type)
        if is_closed is not None:
            query = query.where(Ticket.is_closed == is_closed)
        if assignee_id is not None:
            query = query.where(Ticket.assignee_id == assignee_id)
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Ticket.title.ilike(search_term),
                    Ticket.description.ilike(search_term),
                    Ticket.customer_name.ilike(search_term),
                    Ticket.customer_email.ilike(search_term),
                    Ticket.external_customer_id.ilike(search_term)
                )
            )
        
        # Count query
        count_query = select(func.count()).select_from(Ticket).where(Ticket.is_active == True)
        
        if status:
            count_query = count_query.where(Ticket.status == status)
        if priority:
            count_query = count_query.where(Ticket.priority == priority)
        if ticket_type:
            count_query = count_query.where(Ticket.ticket_type == ticket_type)
        if is_closed is not None:
            count_query = count_query.where(Ticket.is_closed == is_closed)
        if assignee_id is not None:
            count_query = count_query.where(Ticket.assignee_id == assignee_id)
        if search:
            search_term = f"%{search}%"
            count_query = count_query.where(
                or_(
                    Ticket.title.ilike(search_term),
                    Ticket.description.ilike(search_term),
                    Ticket.customer_name.ilike(search_term),
                    Ticket.customer_email.ilike(search_term),
                    Ticket.external_customer_id.ilike(search_term)
                )
            )
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply sorting
        sort_options = {
            "created_at": Ticket.created_at.desc(),
            "updated_at": Ticket.updated_at.desc(),
            "priority": Ticket.priority.desc(),
            "status": Ticket.status.asc(),
            "title": Ticket.title.asc(),
            "customer_name": Ticket.customer_name.asc()
        }
        sort_column = sort_options.get(sort_by, Ticket.created_at.desc())
        
        # Apply pagination and sorting
        offset = (page - 1) * limit
        query = query.order_by(sort_column).offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        tickets = result.scalars().all()
        
        # Convert to simplified response - keep proper types (not strings)
        simplified_tickets = []
        for ticket in tickets:
            simplified_tickets.append({
                "id": ticket.id,
                "ticket_type": ticket.ticket_type,
                "title": ticket.title,
                "status": ticket.status,
                "priority": ticket.priority,
                "customer_name": ticket.customer_name,
                "assignee_id": ticket.assignee_id,
                "assignee_name": ticket.assignee.full_name if ticket.assignee else None,
                "created_at": ticket.created_at
            })
        
        return simplified_tickets, total
    
    # ==================== Admin - Get Statistics ====================
    
    async def get_ticket_statistics_admin(self) -> dict:
        """Get comprehensive ticket statistics for admin dashboard"""
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)
        
        # Total tickets
        total_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(Ticket.is_active == True)
        )
        total_tickets = total_result.scalar()
        
        # By Status
        status_counts = {}
        for ticket_status in TicketStatus:
            result = await self.db.execute(
                select(func.count()).select_from(Ticket).where(
                    Ticket.is_active == True,
                    Ticket.status == ticket_status
                )
            )
            status_counts[ticket_status.value] = result.scalar()
        
        # By Priority
        priority_counts = {}
        for ticket_priority in TicketPriority:
            result = await self.db.execute(
                select(func.count()).select_from(Ticket).where(
                    Ticket.is_active == True,
                    Ticket.priority == ticket_priority
                )
            )
            priority_counts[ticket_priority.value] = result.scalar()
        
        # By Type
        tech_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(
                Ticket.is_active == True,
                Ticket.ticket_type == TicketType.TECH
            )
        )
        tech_tickets = tech_result.scalar()
        
        support_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(
                Ticket.is_active == True,
                Ticket.ticket_type == TicketType.SUPPORT
            )
        )
        support_tickets = support_result.scalar()
        
        # By Assignment
        assigned_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(
                Ticket.is_active == True,
                Ticket.assignee_id != None
            )
        )
        assigned_tickets = assigned_result.scalar()
        
        unassigned_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(
                Ticket.is_active == True,
                Ticket.assignee_id == None
            )
        )
        unassigned_tickets = unassigned_result.scalar()
        
        # SLA - Overdue
        overdue_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(
                Ticket.is_active == True,
                Ticket.sla_due_date < now,
                Ticket.status.not_in([TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELED])
            )
        )
        overdue_tickets = overdue_result.scalar()
        
        # SLA - Due Soon (within 2 hours)
        due_soon_threshold = now + timedelta(hours=2)
        due_soon_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(
                Ticket.is_active == True,
                Ticket.sla_due_date <= due_soon_threshold,
                Ticket.sla_due_date > now,
                Ticket.status.not_in([TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELED])
            )
        )
        due_soon_tickets = due_soon_result.scalar()
        
        # AI Created
        ai_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(
                Ticket.is_active == True,
                Ticket.ai_auto_created == True
            )
        )
        ai_created_tickets = ai_result.scalar()
        manual_created_tickets = total_tickets - ai_created_tickets
        
        # Average Resolution Time
        avg_resolution_result = await self.db.execute(
            select(
                func.avg(
                    func.extract('epoch', Ticket.resolved_at - Ticket.created_at) / 3600
                )
            ).select_from(Ticket).where(
                Ticket.resolved_at != None
            )
        )
        avg_resolution_time = avg_resolution_result.scalar()
        
        # Average Response Time (time to assign)
        avg_response_result = await self.db.execute(
            select(
                func.avg(
                    func.extract('epoch', Ticket.assigned_at - Ticket.created_at) / 3600
                )
            ).select_from(Ticket).where(
                Ticket.assigned_at != None
            )
        )
        avg_response_time = avg_response_result.scalar()
        
        # Recent Activity
        today_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(
                Ticket.created_at >= today_start
            )
        )
        tickets_today = today_result.scalar()
        
        week_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(
                Ticket.created_at >= week_start
            )
        )
        tickets_this_week = week_result.scalar()
        
        month_result = await self.db.execute(
            select(func.count()).select_from(Ticket).where(
                Ticket.created_at >= month_start
            )
        )
        tickets_this_month = month_result.scalar()
        
        return {
            "total_tickets": total_tickets,
            "open_tickets": status_counts.get('open', 0),
            "in_progress_tickets": status_counts.get('in_progress', 0),
            "pending_tickets": status_counts.get('pending', 0),
            "escalated_tickets": status_counts.get('escalated', 0),
            "resolved_tickets": status_counts.get('resolved', 0),
            "closed_tickets": status_counts.get('closed', 0),
            "canceled_tickets": status_counts.get('canceled', 0),
            "urgent_tickets": priority_counts.get('urgent', 0),
            "high_priority_tickets": priority_counts.get('high', 0),
            "medium_priority_tickets": priority_counts.get('medium', 0),
            "low_priority_tickets": priority_counts.get('low', 0),
            "tech_tickets": tech_tickets,
            "support_tickets": support_tickets,
            "assigned_tickets": assigned_tickets,
            "unassigned_tickets": unassigned_tickets,
            "overdue_tickets": overdue_tickets,
            "due_soon_tickets": due_soon_tickets,
            "ai_created_tickets": ai_created_tickets,
            "manual_created_tickets": manual_created_tickets,
            "avg_resolution_time_hours": round(avg_resolution_time, 2) if avg_resolution_time else None,
            "avg_response_time_hours": round(avg_response_time, 2) if avg_response_time else None,
            "tickets_today": tickets_today,
            "tickets_this_week": tickets_this_week,
            "tickets_this_month": tickets_this_month
        }
    
    # ==================== Helper Methods ====================
    
    def _get_sla_hours(self, priority: TicketPriority) -> int:
        """Calculate SLA hours based on priority"""
        sla_map = {
            TicketPriority.URGENT: 1,
            TicketPriority.HIGH: 4,
            TicketPriority.MEDIUM: 12,
            TicketPriority.LOW: 24
        }
        return sla_map.get(priority, 12)
    
    def _validate_status_transition(self, current_status: TicketStatus, new_status: TicketStatus):
        """Validate if status transition is allowed"""
        allowed_transitions = {
            TicketStatus.OPEN: [TicketStatus.IN_PROGRESS, TicketStatus.CANCELED],
            TicketStatus.IN_PROGRESS: [TicketStatus.PENDING, TicketStatus.RESOLVED, TicketStatus.ESCALATED, TicketStatus.CANCELED],
            TicketStatus.PENDING: [TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CANCELED],
            TicketStatus.ESCALATED: [TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CANCELED],
            TicketStatus.RESOLVED: [TicketStatus.CLOSED, TicketStatus.OPEN],
            TicketStatus.CLOSED: [TicketStatus.OPEN],
            TicketStatus.CANCELED: []
        }
        
        if current_status == new_status:
            raise BadRequestException(f"Ticket is already in {new_status.value} status")
        
        if new_status not in allowed_transitions.get(current_status, []):
            raise BadRequestException(
                f"Cannot change status from {current_status.value} to {new_status.value}"
            )
    
    def _convert_to_responses(self, tickets: List[Ticket]) -> List[TicketResponse]:
        """Convert Ticket models to TicketResponse schemas"""
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
        """Create audit log entry"""
        audit_log = AuditLog(
            user_id=user_id,
            action_type=action_type,
            target_table=target_table,
            target_record_id=target_record_id,
            changed_values=changed_values,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(audit_log)