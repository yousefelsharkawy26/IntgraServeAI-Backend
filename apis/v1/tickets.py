# apis/v1/tickets.py
from fastapi import APIRouter, Depends, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
from pydantic import EmailStr

from core.database import get_db
from services.ticket_service import TicketService
from utils.schemas.ticket_schemas import (
    ExternalTicketCreate,
    ExternalTicketCreateResponse,
    TicketResponse,
    TicketDetailedResponse,
    TicketListResponse,
    TicketStatusUpdate,
    TicketReassign,
    TicketResolve,
    TicketCancel,
    TicketMessageCreate,
    TicketMessageResponse,
    TicketMessagesListResponse,
    ExternalMessageCreate,
    FileUploadResponse,
    TicketSummaryResponse,
    TicketSummaryListResponse,
    TicketStatistics
)
from utils.schemas.auth_schemas import MessageResponse
from utils.dependencies import get_current_active_user, require_admin
from models.user import User
from models.ticket import TicketStatus, TicketPriority, TicketType
from utils.exceptions import BadRequestException
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== Public Endpoints (No Auth) ====================

@router.post(
    "/external/create",
    response_model=ExternalTicketCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "Ticket created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Ticket created successfully. We will reply as soon as possible.",
                        "ticket_id": "123e4567-e89b-12d3-a456-426614174000"
                    }
                }
            }
        },
        422: {
            "description": "Validation errors",
            "content": {
                "application/json": {
                    "example": {
                        "errors": {
                            "customer_email": "Invalid email format",
                            "priority": "Field required"
                        }
                    }
                }
            }
        }
    },
    summary="Create Ticket from External System",
    description="Creates a support ticket from an external system. No authentication required."
)
async def create_external_ticket(
    ticket_data: ExternalTicketCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create ticket from external system (e.g., CRM, website form)
    
    **Public endpoint - No authentication required**
    
    **SLA Response Times**:
    - URGENT: 1 hour
    - HIGH: 4 hours
    - MEDIUM: 12 hours
    - LOW: 24 hours
    
    **Returns**: Success message and ticket_id
    """
    ticket_service = TicketService(db)
    ticket = await ticket_service.create_external_ticket(ticket_data)
    
    return ExternalTicketCreateResponse(
        message="Ticket created successfully. We will reply as soon as possible.",
        ticket_id=ticket.id
    )


@router.post(
    "/external/{ticket_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "Message added successfully"
        },
        404: {
            "description": "Ticket not found"
        },
        400: {
            "description": "Cannot add message"
        }
    },
    summary="Add Message from External Customer",
    description="Add a message to ticket from external customer. No authentication required."
)
async def create_external_message(
    ticket_id: UUID,
    message_data: ExternalMessageCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Add message from external customer (no auth)
    
    **Public endpoint - No authentication required**
    """
    ticket_service = TicketService(db)
    
    await ticket_service.create_external_message(
        ticket_id=ticket_id,
        customer_email=message_data.customer_email,
        customer_name=message_data.customer_name,
        message_text=message_data.message_text
    )
    
    return MessageResponse(message="Message added successfully")


@router.get(
    "/external/my-tickets",
    response_model=TicketListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get My Tickets (External Customer)",
    description="Get tickets for external customer by email. No authentication required."
)
async def get_external_customer_tickets(
    customer_email: EmailStr = Query(..., description="Customer email address"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
):
    """Get tickets for external customer (no auth)"""
    ticket_service = TicketService(db)
    
    tickets, total = await ticket_service.get_external_customer_tickets(
        customer_email=customer_email,
        page=page,
        limit=limit
    )
    
    return TicketListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=tickets
    )


@router.get(
    "/external/{ticket_id}/messages-view",
    response_model=TicketMessagesListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ticket Messages (External Customer)",
    description="Get messages for external customer. No authentication required."
)
async def get_external_ticket_messages(
    ticket_id: UUID,
    customer_email: EmailStr = Query(..., description="Customer email (must match ticket owner)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
):
    """Get ticket messages for external customer (no auth)"""
    ticket_service = TicketService(db)
    
    messages, total = await ticket_service.get_external_ticket_messages(
        ticket_id=ticket_id,
        customer_email=customer_email,
        page=page,
        limit=limit
    )
    
    # Convert to response
    message_responses = []
    for msg in messages:
        msg_dict = {
            "id": msg.id,
            "ticket_id": msg.ticket_id,
            "sender_type": msg.sender_type,
            "sender_name": msg.sender_name,
            "sender_email": msg.sender_email,
            "message_text": msg.message_text,
            "is_internal_note": msg.is_internal_note,
            "attachments": msg.attachments,
            "created_at": msg.created_at
        }
        message_responses.append(TicketMessageResponse(**msg_dict))
    
    return TicketMessagesListResponse(
        page=page,
        limit=limit,
        total=total,
        messages=message_responses
    )


# ==================== Authenticated Endpoints ====================

@router.get(
    "/my-tickets",
    response_model=TicketListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get My Tickets",
    description="Retrieves tickets assigned to the current user with filters and sorting."
)
async def get_my_tickets(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    status: Optional[TicketStatus] = Query(None, description="Filter by status"),
    priority: Optional[TicketPriority] = Query(None, description="Filter by priority"),
    ticket_type: Optional[TicketType] = Query(None, description="Filter by ticket type"),
    sort_by: str = Query("created_at", description="Sort by: created_at, updated_at, priority, status, title"),
    search: Optional[str] = Query(None, min_length=2, description="Search in title, description, customer name/email"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get my tickets with filters and sorting"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    tickets, total = await ticket_service.get_my_tickets(
        current_user_id=current_user.id,
        user_roles=user_roles,
        page=page,
        limit=limit,
        status=status,
        priority=priority,
        ticket_type=ticket_type,
        sort_by=sort_by,
        search=search
    )
    
    return TicketListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=tickets
    )


@router.get(
    "/unassigned",
    response_model=TicketListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Unassigned Tickets",
    description="Retrieves unassigned tickets with filters and sorting."
)
async def get_unassigned_tickets(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    priority: Optional[TicketPriority] = Query(None, description="Filter by priority"),
    ticket_type: Optional[TicketType] = Query(None, description="Filter by ticket type"),
    sort_by: str = Query("priority", description="Sort by: priority, created_at, title"),
    search: Optional[str] = Query(None, min_length=2, description="Search in title, description, customer name"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get unassigned tickets with filters and sorting"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    tickets, total = await ticket_service.get_unassigned_tickets(
        user_roles=user_roles,
        page=page,
        limit=limit,
        priority=priority,
        ticket_type=ticket_type,
        sort_by=sort_by,
        search=search
    )
    
    return TicketListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=tickets
    )


@router.get(
    "/admin/all",
    response_model=TicketListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Tickets retrieved successfully"},
        401: {"description": "Unauthorized - Admin only"}
    },
    summary="Get All Tickets (Admin)",
    description="Retrieves all tickets with filters. Admin only."
)
async def get_all_tickets_admin(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    status: Optional[TicketStatus] = Query(None, description="Filter by status"),
    priority: Optional[TicketPriority] = Query(None, description="Filter by priority"),
    ticket_type: Optional[TicketType] = Query(None, description="Filter by ticket type"),
    is_closed: Optional[bool] = Query(None, description="Filter by closed status"),
    assignee_id: Optional[UUID] = Query(None, description="Filter by assignee user ID"),
    sort_by: str = Query("created_at", description="Sort by: created_at, updated_at, priority, status, title, customer_name"),
    search: Optional[str] = Query(None, min_length=2, description="Search in title, description, customer details"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get all tickets (Admin only) with filters"""
    ticket_service = TicketService(db)
    
    tickets, total = await ticket_service.get_all_tickets_admin(
        page=page,
        limit=limit,
        status=status,
        priority=priority,
        ticket_type=ticket_type,
        is_closed=is_closed,
        assignee_id=assignee_id,
        sort_by=sort_by,
        search=search
    )
    
    return TicketListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=tickets
    )


@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Ticket details retrieved successfully"},
        404: {"description": "Ticket not found"},
        400: {"description": "Cannot access this ticket type"}
    },
    summary="Get Ticket Details",
    description="Retrieves detailed information about a specific ticket."
)
async def get_ticket_details(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get ticket details by ID"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    ticket = await ticket_service.get_ticket_details(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    # Convert to response
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
    
    return TicketResponse(**ticket_dict)


@router.get(
    "/admin/{ticket_id}",
    response_model=TicketDetailedResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ticket Details (Admin - Full Details)",
    description="Retrieves complete ticket information with ALL fields. Admin only."
)
async def get_ticket_details_admin(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get ticket details with ALL fields (Admin only)"""
    ticket_service = TicketService(db)
    
    ticket = await ticket_service.get_ticket_details_admin(ticket_id)
    
    # Convert to detailed response with ALL fields
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
        "previous_assignee_id": ticket.previous_assignee_id,
        "is_closed": ticket.is_closed,
        "is_active": ticket.is_active,
        "closed_at": ticket.closed_at,
        "resolution_notes": ticket.resolution_notes,
        "cancellation_reason": ticket.cancellation_reason,
        "escalation_reason": ticket.escalation_reason,
        "resolved_at": ticket.resolved_at,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at
    }
    
    return TicketDetailedResponse(**ticket_dict)


@router.patch(
    "/{ticket_id}/assign-to-me",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Ticket assigned successfully"},
        404: {"description": "Ticket not found"},
        400: {"description": "Cannot assign this ticket"},
        409: {"description": "Ticket already assigned"}
    },
    summary="Assign Ticket to Me",
    description="Self-assign an unassigned ticket to the current user."
)
async def assign_ticket_to_me(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Self-assign an unassigned ticket"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    await ticket_service.assign_to_me(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return MessageResponse(message="Ticket assigned to you successfully")


@router.patch(
    "/{ticket_id}/status",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Status updated successfully"},
        404: {"description": "Ticket not found"},
        400: {"description": "Invalid status transition"}
    },
    summary="Update Ticket Status",
    description="Update the status of a ticket."
)
async def update_ticket_status(
    ticket_id: UUID,
    status_update: TicketStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update ticket status"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    await ticket_service.update_ticket_status(
        ticket_id=ticket_id,
        new_status=status_update.status,
        notes=status_update.notes,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return MessageResponse(message="Ticket status updated successfully")


@router.patch(
    "/{ticket_id}/reassign",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Ticket reassigned successfully"},
        404: {"description": "Ticket or role not found"},
        400: {"description": "Cannot reassign this ticket"}
    },
    summary="Reassign Ticket to Role",
    description="Reassign a ticket to a specific role (escalate)."
)
async def reassign_ticket(
    ticket_id: UUID,
    reassign_data: TicketReassign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Reassign ticket to a role"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    await ticket_service.reassign_ticket_by_role(
        ticket_id=ticket_id,
        target_role=reassign_data.role,
        reason=reassign_data.reason,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return MessageResponse(message="Ticket reassigned successfully")


@router.patch(
    "/{ticket_id}/resolve",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Ticket resolved successfully"},
        404: {"description": "Ticket not found"},
        400: {"description": "Cannot resolve this ticket"}
    },
    summary="Resolve Ticket",
    description="Mark a ticket as resolved with resolution notes."
)
async def resolve_ticket(
    ticket_id: UUID,
    resolve_data: TicketResolve,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Resolve a ticket"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    await ticket_service.resolve_ticket(
        ticket_id=ticket_id,
        resolution_notes=resolve_data.resolution_notes,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return MessageResponse(message="Ticket resolved successfully")


@router.patch(
    "/{ticket_id}/cancel",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Ticket canceled successfully"},
        404: {"description": "Ticket not found"},
        400: {"description": "Cannot cancel this ticket"}
    },
    summary="Cancel Ticket",
    description="Cancel a ticket (duplicate, invalid, etc.)."
)
async def cancel_ticket(
    ticket_id: UUID,
    cancel_data: TicketCancel,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Cancel a ticket"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    await ticket_service.cancel_ticket(
        ticket_id=ticket_id,
        cancellation_reason=cancel_data.cancellation_reason,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return MessageResponse(message="Ticket canceled successfully")


@router.patch(
    "/{ticket_id}/close",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Ticket closed successfully"},
        404: {"description": "Ticket not found"},
        400: {"description": "Only resolved tickets can be closed"}
    },
    summary="Close Ticket",
    description="Close a resolved ticket (final state)."
)
async def close_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Close a ticket (only if resolved)"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    await ticket_service.close_ticket(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return MessageResponse(message="Ticket closed successfully")


# ==================== Ticket Messages ====================

@router.get(
    "/{ticket_id}/messages",
    response_model=TicketMessagesListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ticket Messages",
    description="Retrieves all messages/chat for a specific ticket."
)
async def get_ticket_messages(
    ticket_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get ticket messages (chat history)"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    messages, total = await ticket_service.get_ticket_messages(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles,
        page=page,
        limit=limit
    )
    
    # Convert to response
    message_responses = []
    for msg in messages:
        msg_dict = {
            "id": msg.id,
            "ticket_id": msg.ticket_id,
            "sender_type": msg.sender_type,
            "sender_name": msg.sender_name,
            "sender_email": msg.sender_email,
            "message_text": msg.message_text,
            "is_internal_note": msg.is_internal_note,
            "attachments": msg.attachments,
            "created_at": msg.created_at
        }
        message_responses.append(TicketMessageResponse(**msg_dict))
    
    return TicketMessagesListResponse(
        page=page,
        limit=limit,
        total=total,
        messages=message_responses
    )


@router.post(
    "/{ticket_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Message added successfully"},
        404: {"description": "Ticket not found"},
        400: {"description": "Cannot add message"}
    },
    summary="Add Message to Ticket",
    description="Add a new message/note to a ticket (authenticated users)."
)
async def create_ticket_message(
    ticket_id: UUID,
    message_data: TicketMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Add a message to ticket (authenticated)"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    await ticket_service.create_ticket_message(
        ticket_id=ticket_id,
        message_text=message_data.message_text,
        is_internal_note=message_data.is_internal_note,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return MessageResponse(message="Message added successfully")


# ==================== Admin Endpoints ====================

@router.delete(
    "/admin/{ticket_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete Ticket (Admin)",
    description="Delete a ticket (soft delete). Admin only."
)
async def delete_ticket_admin(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete ticket (Admin only - soft delete)"""
    ticket_service = TicketService(db)
    
    await ticket_service.delete_ticket_admin(
        ticket_id=ticket_id,
        deleted_by_user_id=current_user.id
    )
    
    return MessageResponse(message="Ticket deleted successfully")


@router.get(
    "/admin/all-summary",
    response_model=TicketSummaryListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Ticket summaries retrieved successfully"},
        401: {"description": "Unauthorized - Admin only"}
    },
    summary="Get All Tickets Summary (Admin)",
    description="Get simplified list of all tickets. Admin only."
)
async def get_all_tickets_summary_admin(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    status: Optional[TicketStatus] = Query(None, description="Filter by status"),
    priority: Optional[TicketPriority] = Query(None, description="Filter by priority"),
    ticket_type: Optional[TicketType] = Query(None, description="Filter by ticket type"),
    is_closed: Optional[bool] = Query(None, description="Filter by closed status"),
    assignee_id: Optional[UUID] = Query(None, description="Filter by assignee user ID"),
    sort_by: str = Query("created_at", description="Sort by: created_at, updated_at, priority, status, title, customer_name"),
    search: Optional[str] = Query(None, min_length=2, description="Search in all fields"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get all tickets (simplified) - Admin only"""
    ticket_service = TicketService(db)
    
    tickets, total = await ticket_service.get_all_tickets_admin_summary(
        page=page,
        limit=limit,
        status=status,
        priority=priority,
        ticket_type=ticket_type,
        is_closed=is_closed,
        assignee_id=assignee_id,
        sort_by=sort_by,
        search=search
    )
    
    # Convert dict to TicketSummaryResponse
    ticket_responses = [TicketSummaryResponse(**t) for t in tickets]
    
    return TicketSummaryListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=ticket_responses
    )


@router.get(
    "/admin/statistics",
    response_model=TicketStatistics,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Statistics retrieved successfully"},
        401: {"description": "Unauthorized - Admin only"}
    },
    summary="Get Ticket Statistics (Admin)",
    description="Get comprehensive ticket statistics. Admin only."
)
async def get_ticket_statistics_admin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get ticket statistics (Admin only)"""
    ticket_service = TicketService(db)
    
    stats = await ticket_service.get_ticket_statistics_admin()
    
    return TicketStatistics(**stats)


# ==================== File Upload Endpoint ====================

@router.post(
    "/{ticket_id}/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload File to Ticket",
    description="Upload attachment (image, document) to ticket."
)
async def upload_ticket_file(
    ticket_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Upload file to ticket"""
    import os
    import shutil
    from pathlib import Path
    
    # Validate file size (10 MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        raise BadRequestException("File size exceeds 10 MB limit")
    
    # Validate file type
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx', '.txt', '.csv', '.xlsx'}
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise BadRequestException(f"File type {file_extension} not allowed")
    
    # Verify ticket exists and user can access it
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    ticket = await ticket_service.get_ticket_details(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    # Create upload directory
    upload_dir = Path("uploads/tickets") / str(ticket_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    import time
    timestamp = int(time.time())
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = upload_dir / safe_filename
    
    # Save file
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    logger.info(f"File uploaded: {file_path} for ticket {ticket_id}")
    
    return FileUploadResponse(
        filename=file.filename,
        file_path=str(file_path),
        file_size=file_size,
        content_type=file.content_type or "application/octet-stream"
    )