# apis/v1/tickets.py
from fastapi import APIRouter, Depends, status, Query, UploadFile, File, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional, List
from pydantic import EmailStr
from starlette.datastructures import UploadFile as StarletteUploadFile

from core.database import get_db
from services.ticket_service import TicketService
from utils.schemas.ticket_schemas import (
    ExternalTicketCreate,
    ExternalTicketCreateResponse,
    TicketResponse,
    TicketDetailedResponse,
    TicketSimpleResponse,
    TicketSimpleListResponse,
    ExternalTicketSimpleResponse,
    ExternalTicketListResponse,
    TicketStatusUpdate,
    TicketReassign,
    TicketResolve,
    TicketCancel,
    TicketMessageResponse,
    TicketMessagesListResponse,
    TicketStatistics,
    TicketMessageAddedResponse,
    TicketAssignedResponse,
    TicketStatusUpdateResponse,
    TicketReassignResponse,
    TicketResolvedResponse,
    TicketCanceledResponse,
    TicketClosedResponse,
    TicketDeletedResponse
)
from utils.dependencies import get_current_active_user, require_admin
from models.user import User
from models.ticket import TicketStatus, TicketPriority, TicketType
from utils.exceptions import BadRequestException, ValidationException
import logging
from pathlib import Path
import time
import re

router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== Helper Functions ====================

def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


async def save_uploaded_files(files: List, ticket_id: UUID) -> List[dict]:
    """Save uploaded files and return attachment info"""
    attachments = []
    
    if not files:
        return attachments
    
    if len(files) > 5:
        raise BadRequestException("Maximum 5 files allowed per message")
    
    upload_dir = Path("uploads/tickets") / str(ticket_id) / "messages"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    allowed_extensions = {
        '.jpg', '.jpeg', '.png', '.gif',
        '.pdf', '.doc', '.docx',
        '.txt', '.csv', '.xlsx'
    }
    
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    for file in files:
        try:
            content = await file.read()
            file_size = len(content)
            
            if file_size == 0:
                continue
            
            if file_size > MAX_FILE_SIZE:
                raise BadRequestException(f"File '{file.filename}' exceeds 10 MB limit")
            
            ext = Path(file.filename).suffix.lower()
            if ext not in allowed_extensions:
                raise BadRequestException(f"File type '{ext}' not allowed")
            
            timestamp = int(time.time() * 1000)
            safe_filename = f"{timestamp}_{file.filename}"
            file_path = upload_dir / safe_filename
            
            with open(file_path, "wb") as f:
                f.write(content)
            
            attachments.append({
                "filename": file.filename,
                "file_path": str(file_path),
                "file_size": file_size,
                "content_type": file.content_type or "application/octet-stream"
            })
            
            logger.info(f"Saved: {file_path}")
            
        except BadRequestException:
            raise
        except Exception as e:
            logger.error(f"Failed to save {file.filename}: {e}")
            raise BadRequestException(f"Failed to save '{file.filename}'")
    
    return attachments


# ====================================================================================
# ========================= ADMIN ENDPOINTS (MUST BE FIRST!) =========================
# ====================================================================================

@router.get(
    "/admin/statistics",
    response_model=TicketStatistics,
    status_code=status.HTTP_200_OK,
    summary="Get Statistics (Admin)",
    description="Get ticket statistics. Admin only.",
    tags=["Admin"]
)
async def get_ticket_statistics_admin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get statistics (Admin)"""
    ticket_service = TicketService(db)
    stats = await ticket_service.get_ticket_statistics_admin()
    return TicketStatistics(**stats)


@router.get(
    "/admin/all",
    response_model=TicketSimpleListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get All Tickets (Admin)",
    description="Get all tickets. Admin only.",
    tags=["Admin"]
)
async def get_all_tickets_admin(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[TicketStatus] = Query(None),
    priority: Optional[TicketPriority] = Query(None),
    ticket_type: Optional[TicketType] = Query(None),
    is_closed: Optional[bool] = Query(None),
    assignee_id: Optional[UUID] = Query(None),
    sort_by: str = Query("created_at"),
    search: Optional[str] = Query(None, min_length=2),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get all tickets (Admin)"""
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
    
    return TicketSimpleListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=[TicketSimpleResponse(**t) for t in tickets]
    )


@router.get(
    "/admin/{ticket_id}",
    response_model=TicketDetailedResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ticket (Admin)",
    description="Get full ticket details. Admin only.",
    tags=["Admin"]
)
async def get_ticket_details_admin(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get ticket details (Admin)"""
    ticket_service = TicketService(db)
    ticket = await ticket_service.get_ticket_details_admin(ticket_id)
    
    return TicketDetailedResponse(
        id=ticket.id,
        ticket_type=ticket.ticket_type,
        title=ticket.title,
        description=ticket.description,
        customer_email=ticket.customer_email,
        customer_name=ticket.customer_name,
        external_customer_id=ticket.external_customer_id,
        status=ticket.status,
        priority=ticket.priority,
        ai_auto_created=ticket.ai_auto_created,
        ai_confidence=float(ticket.ai_confidence) if ticket.ai_confidence else None,
        sla_due_date=ticket.sla_due_date,
        assignee_id=ticket.assignee_id,
        assignee_name=ticket.assignee.full_name if ticket.assignee else None,
        assigned_at=ticket.assigned_at,
        previous_assignee_id=ticket.previous_assignee_id,
        is_closed=ticket.is_closed,
        is_active=ticket.is_active,
        closed_at=ticket.closed_at,
        resolution_notes=ticket.resolution_notes,
        cancellation_reason=ticket.cancellation_reason,
        escalation_reason=ticket.escalation_reason,
        resolved_at=ticket.resolved_at,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at
    )


@router.delete(
    "/admin/{ticket_id}",
    response_model=TicketDeletedResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete Ticket (Admin)",
    description="Soft delete ticket. Admin only.",
    tags=["Admin"]
)
async def delete_ticket_admin(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete ticket (Admin)"""
    ticket_service = TicketService(db)
    
    result = await ticket_service.delete_ticket_admin(
        ticket_id=ticket_id,
        deleted_by_user_id=current_user.id
    )
    
    return TicketDeletedResponse(**result)


# ====================================================================================
# ========================= EXTERNAL ENDPOINTS (PUBLIC) ==============================
# ====================================================================================

@router.post(
    "/external/create",
    response_model=ExternalTicketCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Ticket (External)",
    description="Create ticket from external system. No auth required.",
    tags=["External"]
)
async def create_external_ticket(
    ticket_data: ExternalTicketCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create external ticket"""
    ticket_service = TicketService(db)
    ticket = await ticket_service.create_external_ticket(ticket_data)
    
    return ExternalTicketCreateResponse(
        message="Ticket created successfully",
        ticket_id=ticket.id
    )


@router.get(
    "/external/my-tickets",
    response_model=ExternalTicketListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get My Tickets (External)",
    description="Get tickets by customer email. No auth required.",
    tags=["External"]
)
async def get_external_customer_tickets(
    customer_email: EmailStr = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get external customer tickets"""
    ticket_service = TicketService(db)
    
    tickets, total = await ticket_service.get_external_customer_tickets(
        customer_email=customer_email,
        page=page,
        limit=limit
    )
    
    return ExternalTicketListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=[ExternalTicketSimpleResponse(**t) for t in tickets]
    )


@router.post(
    "/external/{ticket_id}/messages",
    response_model=TicketMessageAddedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Message (External)",
    description="""
Add message from external customer. No auth required.

**Options:** Message only ✅ | Files only ✅ | Both ✅

**File Rules:** Max 5 files, 10 MB each
""",
    tags=["External"]
)
async def create_external_message(
    ticket_id: UUID,
    request: Request,
    customer_email: str = Form(..., description="Customer email"),
    customer_name: str = Form(..., min_length=2, description="Customer name"),
    message_text: str = Form(default="", description="Message (optional if files)"),
    db: AsyncSession = Depends(get_db)
):
    """Add message from external customer"""
    
    if not validate_email(customer_email):
        raise ValidationException({"customer_email": "Invalid email format"})
    
    if len(customer_name.strip()) < 2:
        raise ValidationException({"customer_name": "Name must be at least 2 characters"})
    
    # Get files from form
    form = await request.form()
    files = []
    for key, value in form.multi_items():
        if key == "files" and isinstance(value, StarletteUploadFile):
            if value.filename:
                files.append(value)
    
    has_message = bool(message_text and message_text.strip())
    has_files = len(files) > 0
    
    if not has_message and not has_files:
        raise BadRequestException("Must provide message or files or both")
    
    attachments = await save_uploaded_files(files, ticket_id)
    final_message = message_text.strip() if has_message else "[File(s) attached]"
    
    ticket_service = TicketService(db)
    result = await ticket_service.create_external_message(
        ticket_id=ticket_id,
        customer_email=customer_email.strip(),
        customer_name=customer_name.strip(),
        message_text=final_message,
        attachments=attachments if attachments else None
    )
    
    return TicketMessageAddedResponse(
        message=result["message"],
        message_id=result["message_id"]
    )


@router.get(
    "/external/{ticket_id}/messages",
    response_model=TicketMessagesListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Messages (External)",
    description="Get ticket messages. Internal notes excluded.",
    tags=["External"]
)
async def get_external_ticket_messages(
    ticket_id: UUID,
    customer_email: EmailStr = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get external ticket messages"""
    ticket_service = TicketService(db)
    
    messages, total = await ticket_service.get_external_ticket_messages(
        ticket_id=ticket_id,
        customer_email=customer_email,
        page=page,
        limit=limit
    )
    
    message_responses = [
        TicketMessageResponse(
            id=msg.id,
            ticket_id=msg.ticket_id,
            sender_type=msg.sender_type,
            sender_name=msg.sender_name,
            sender_email=msg.sender_email,
            message_text=msg.message_text,
            is_internal_note=msg.is_internal_note,
            attachments=msg.attachments,
            created_at=msg.created_at
        )
        for msg in messages
    ]
    
    return TicketMessagesListResponse(
        page=page,
        limit=limit,
        total=total,
        messages=message_responses
    )


# ====================================================================================
# ========================= AUTHENTICATED ENDPOINTS ==================================
# ====================================================================================

@router.get(
    "/my-tickets",
    response_model=TicketSimpleListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get My Tickets",
    description="Get tickets assigned to current user.",
    tags=["Tickets"]
)
async def get_my_tickets(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[TicketStatus] = Query(None),
    priority: Optional[TicketPriority] = Query(None),
    sort_by: str = Query("created_at"),
    search: Optional[str] = Query(None, min_length=2),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get my tickets"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    tickets, total = await ticket_service.get_my_tickets(
        current_user_id=current_user.id,
        user_roles=user_roles,
        page=page,
        limit=limit,
        status=status,
        priority=priority,
        sort_by=sort_by,
        search=search
    )
    
    return TicketSimpleListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=[TicketSimpleResponse(**t) for t in tickets]
    )


@router.get(
    "/unassigned",
    response_model=TicketSimpleListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Unassigned Tickets",
    description="Get unassigned tickets for your role.",
    tags=["Tickets"]
)
async def get_unassigned_tickets(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    priority: Optional[TicketPriority] = Query(None),
    sort_by: str = Query("priority"),
    search: Optional[str] = Query(None, min_length=2),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get unassigned tickets"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    tickets, total = await ticket_service.get_unassigned_tickets(
        user_roles=user_roles,
        page=page,
        limit=limit,
        priority=priority,
        sort_by=sort_by,
        search=search
    )
    
    return TicketSimpleListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=[TicketSimpleResponse(**t) for t in tickets]
    )


# ====================================================================================
# ========================= TICKET ACTIONS (with {ticket_id}) ========================
# ====================================================================================

@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ticket Details",
    description="Get ticket details (your tickets only).",
    tags=["Tickets"]
)
async def get_ticket_details(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get ticket details"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    ticket = await ticket_service.get_ticket_details(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketResponse(
        id=ticket.id,
        ticket_type=ticket.ticket_type,
        title=ticket.title,
        description=ticket.description,
        customer_email=ticket.customer_email,
        customer_name=ticket.customer_name,
        external_customer_id=ticket.external_customer_id,
        status=ticket.status,
        priority=ticket.priority,
        ai_auto_created=ticket.ai_auto_created,
        ai_confidence=float(ticket.ai_confidence) if ticket.ai_confidence else None,
        sla_due_date=ticket.sla_due_date,
        assignee_id=ticket.assignee_id,
        assignee_name=ticket.assignee.full_name if ticket.assignee else None,
        assigned_at=ticket.assigned_at,
        is_closed=ticket.is_closed,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at
    )


@router.patch(
    "/{ticket_id}/assign-to-me",
    response_model=TicketAssignedResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign to Me",
    description="Self-assign an unassigned ticket.",
    tags=["Tickets"]
)
async def assign_ticket_to_me(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Assign ticket to me"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    result = await ticket_service.assign_to_me(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketAssignedResponse(**result)


@router.patch(
    "/{ticket_id}/status",
    response_model=TicketStatusUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Status",
    description="Update ticket status.",
    tags=["Tickets"]
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
    
    result = await ticket_service.update_ticket_status(
        ticket_id=ticket_id,
        new_status=status_update.status,
        notes=status_update.notes,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketStatusUpdateResponse(**result)


@router.patch(
    "/{ticket_id}/reassign",
    response_model=TicketReassignResponse,
    status_code=status.HTTP_200_OK,
    summary="Reassign Ticket",
    description="Toggle between Tech/Support (ticket becomes unassigned).",
    tags=["Tickets"]
)
async def reassign_ticket(
    ticket_id: UUID,
    reassign_data: TicketReassign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Reassign ticket"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    result = await ticket_service.toggle_reassign_ticket(
        ticket_id=ticket_id,
        reason=reassign_data.reason,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketReassignResponse(**result)


@router.patch(
    "/{ticket_id}/resolve",
    response_model=TicketResolvedResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve Ticket",
    description="Mark ticket as resolved.",
    tags=["Tickets"]
)
async def resolve_ticket(
    ticket_id: UUID,
    resolve_data: TicketResolve,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Resolve ticket"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    result = await ticket_service.resolve_ticket(
        ticket_id=ticket_id,
        resolution_notes=resolve_data.resolution_notes,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketResolvedResponse(**result)


@router.patch(
    "/{ticket_id}/cancel",
    response_model=TicketCanceledResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel Ticket",
    description="Cancel a ticket.",
    tags=["Tickets"]
)
async def cancel_ticket(
    ticket_id: UUID,
    cancel_data: TicketCancel,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Cancel ticket"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    result = await ticket_service.cancel_ticket(
        ticket_id=ticket_id,
        cancellation_reason=cancel_data.cancellation_reason,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketCanceledResponse(**result)


@router.patch(
    "/{ticket_id}/close",
    response_model=TicketClosedResponse,
    status_code=status.HTTP_200_OK,
    summary="Close Ticket",
    description="Close a resolved ticket.",
    tags=["Tickets"]
)
async def close_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Close ticket"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    result = await ticket_service.close_ticket(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketClosedResponse(**result)


# ====================================================================================
# ========================= TICKET MESSAGES ==========================================
# ====================================================================================

@router.get(
    "/{ticket_id}/messages",
    response_model=TicketMessagesListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ticket Messages",
    description="Get messages for your ticket.",
    tags=["Messages"]
)
async def get_ticket_messages(
    ticket_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get ticket messages"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    messages, total = await ticket_service.get_ticket_messages(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles,
        page=page,
        limit=limit
    )
    
    message_responses = [
        TicketMessageResponse(
            id=msg.id,
            ticket_id=msg.ticket_id,
            sender_type=msg.sender_type,
            sender_name=msg.sender_name,
            sender_email=msg.sender_email,
            message_text=msg.message_text,
            is_internal_note=msg.is_internal_note,
            attachments=msg.attachments,
            created_at=msg.created_at
        )
        for msg in messages
    ]
    
    return TicketMessagesListResponse(
        page=page,
        limit=limit,
        total=total,
        messages=message_responses
    )


@router.post(
    "/{ticket_id}/messages",
    response_model=TicketMessageAddedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Message",
    description="""
Add message to ticket with optional files.

**Options:** Message only ✅ | Files only ✅ | Both ✅

**File Rules:** Max 5 files, 10 MB each
""",
    tags=["Messages"]
)
async def create_ticket_message(
    ticket_id: UUID,
    request: Request,
    message_text: str = Form(default="", description="Message text"),
    is_internal_note: bool = Form(default=False, description="Internal note"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Add message to ticket"""
    
    # Get files from form
    form = await request.form()
    files = []
    for key, value in form.multi_items():
        if key == "files" and isinstance(value, StarletteUploadFile):
            if value.filename:
                files.append(value)
    
    has_message = bool(message_text and message_text.strip())
    has_files = len(files) > 0
    
    if not has_message and not has_files:
        raise BadRequestException("Must provide message or files or both")
    
    attachments = await save_uploaded_files(files, ticket_id)
    final_message = message_text.strip() if has_message else "[File(s) attached]"
    
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    result = await ticket_service.create_ticket_message_with_attachments(
        ticket_id=ticket_id,
        message_text=final_message,
        is_internal_note=is_internal_note,
        attachments=attachments if attachments else None,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketMessageAddedResponse(**result)