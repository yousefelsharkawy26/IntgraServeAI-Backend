# apis/v1/tickets.py
from fastapi import APIRouter, Depends, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional, List
from pydantic import EmailStr

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
    TicketMessageCreate,
    TicketMessageResponse,
    TicketMessagesListResponse,
    FileUploadResponse,
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
            "model": ExternalTicketCreateResponse
        },
        422: {
            "description": "Validation Error"
        }
    },
    summary="Create Ticket from External System",
    description="""
    Creates a support ticket from an external system. No authentication required.
    
    **SLA Response Times**:
    - URGENT: 1 hour
    - HIGH: 4 hours
    - MEDIUM: 12 hours
    - LOW: 24 hours
    """
)
async def create_external_ticket(
    ticket_data: ExternalTicketCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create ticket from external system (e.g., CRM, website form)"""
    ticket_service = TicketService(db)
    ticket = await ticket_service.create_external_ticket(ticket_data)
    
    return ExternalTicketCreateResponse(
        message="Ticket created successfully. We will reply as soon as possible.",
        ticket_id=ticket.id
    )


@router.post(
    "/external/{ticket_id}/messages",
    response_model=TicketMessageAddedResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "Message added successfully",
            "model": TicketMessageAddedResponse
        },
        400: {
            "description": "Bad Request - Email mismatch, closed ticket, etc."
        },
        404: {
            "description": "Ticket not found"
        },
        422: {
            "description": "Validation Error"
        }
    },
    summary="Add Message from External Customer",
    description="""
    Add a message to ticket from external customer with optional file attachments.
    No authentication required.
    
    **File Upload Rules**:
    - Max 5 files per message
    - Max 10 MB per file
    - Allowed: jpg, jpeg, png, gif, pdf, doc, docx, txt, csv, xlsx
    """
)
async def create_external_message_with_files(
    ticket_id: UUID,
    customer_email: EmailStr = Form(..., description="Customer email"),
    customer_name: str = Form(..., min_length=2, max_length=255, description="Customer name"),
    message_text: str = Form(..., min_length=1, max_length=5000, description="Message text"),
    files: List[UploadFile] = File(None, description="Attachments (optional, max 5 files, 10 MB each)"),
    db: AsyncSession = Depends(get_db)
):
    """Add message with optional files from external customer"""
    import shutil
    from pathlib import Path
    import time
    
    ticket_service = TicketService(db)
    
    # Validate and save files
    attachments = []
    
    if files and files[0].filename:
        if len(files) > 5:
            raise BadRequestException("Maximum 5 files allowed per message")
        
        upload_dir = Path("uploads/tickets") / str(ticket_id) / "messages"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx', '.txt', '.csv', '.xlsx'}
        MAX_FILE_SIZE = 10 * 1024 * 1024
        
        for file in files:
            if not file.filename:
                continue
                
            file.file.seek(0, 2)
            file_size = file.file.tell()
            file.file.seek(0)
            
            if file_size > MAX_FILE_SIZE:
                raise BadRequestException(f"File '{file.filename}' exceeds 10 MB limit")
            
            file_extension = Path(file.filename).suffix.lower()
            
            if file_extension not in allowed_extensions:
                raise BadRequestException(f"File type {file_extension} not allowed")
            
            timestamp = int(time.time() * 1000)
            safe_filename = f"{timestamp}_{file.filename}"
            file_path = upload_dir / safe_filename
            
            with file_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            attachments.append({
                "filename": file.filename,
                "file_path": str(file_path),
                "file_size": file_size,
                "content_type": file.content_type or "application/octet-stream"
            })
            
            logger.info(f"File uploaded: {file_path}")
    
    result = await ticket_service.create_external_message(
        ticket_id=ticket_id,
        customer_email=customer_email,
        customer_name=customer_name,
        message_text=message_text.strip(),
        attachments=attachments if attachments else None
    )
    
    return TicketMessageAddedResponse(
        message=result["message"],
        message_id=result["message_id"]
    )


@router.get(
    "/external/my-tickets",
    response_model=ExternalTicketListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Tickets retrieved successfully",
            "model": ExternalTicketListResponse
        },
        422: {
            "description": "Validation Error"
        }
    },
    summary="Get My Tickets (External Customer)",
    description="Get simplified tickets list for external customer by email. No authentication required."
)
async def get_external_customer_tickets(
    customer_email: EmailStr = Query(..., description="Customer email address"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
):
    """Get tickets for external customer (no auth) - Simplified response"""
    ticket_service = TicketService(db)
    
    tickets, total = await ticket_service.get_external_customer_tickets(
        customer_email=customer_email,
        page=page,
        limit=limit
    )
    
    ticket_responses = [ExternalTicketSimpleResponse(**t) for t in tickets]
    
    return ExternalTicketListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=ticket_responses
    )


@router.get(
    "/external/{ticket_id}/messages",
    response_model=TicketMessagesListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Messages retrieved successfully",
            "model": TicketMessagesListResponse
        },
        400: {
            "description": "Bad Request - Email mismatch"
        },
        404: {
            "description": "Ticket not found"
        },
        422: {
            "description": "Validation Error"
        }
    },
    summary="Get Ticket Messages (External Customer)",
    description="Get messages for external customer. No authentication required. Internal notes are excluded."
)
async def get_external_ticket_messages(
    ticket_id: UUID,
    customer_email: EmailStr = Query(..., description="Customer email"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
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
    response_model=TicketSimpleListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Tickets retrieved successfully",
            "model": TicketSimpleListResponse
        },
        401: {
            "description": "Unauthorized"
        },
        422: {
            "description": "Validation Error"
        }
    },
    summary="Get My Tickets",
    description="Retrieves tickets assigned to current user with automatic role-based filtering. Returns simplified response."
)
async def get_my_tickets(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[TicketStatus] = Query(None, description="Filter by status"),
    priority: Optional[TicketPriority] = Query(None, description="Filter by priority"),
    sort_by: str = Query("created_at", description="Sort by: created_at, updated_at, priority, status, title"),
    search: Optional[str] = Query(None, min_length=2, description="Search in title, customer name/email"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get my tickets with automatic role-based filtering"""
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
    
    ticket_responses = [TicketSimpleResponse(**t) for t in tickets]
    
    return TicketSimpleListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=ticket_responses
    )


@router.get(
    "/unassigned",
    response_model=TicketSimpleListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Unassigned tickets retrieved successfully",
            "model": TicketSimpleListResponse
        },
        401: {
            "description": "Unauthorized"
        },
        422: {
            "description": "Validation Error"
        }
    },
    summary="Get Unassigned Tickets",
    description="Retrieves unassigned tickets with automatic role-based filtering. Returns simplified response."
)
async def get_unassigned_tickets(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    priority: Optional[TicketPriority] = Query(None, description="Filter by priority"),
    sort_by: str = Query("priority", description="Sort by: priority, created_at, title"),
    search: Optional[str] = Query(None, min_length=2, description="Search in title, customer name"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get unassigned tickets with automatic role-based filtering"""
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
    
    ticket_responses = [TicketSimpleResponse(**t) for t in tickets]
    
    return TicketSimpleListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=ticket_responses
    )


@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Ticket details retrieved successfully",
            "model": TicketResponse
        },
        401: {
            "description": "Unauthorized"
        },
        403: {
            "description": "Forbidden - No permission to view this ticket type"
        },
        404: {
            "description": "Ticket not found"
        }
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


@router.patch(
    "/{ticket_id}/assign-to-me",
    response_model=TicketAssignedResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Ticket assigned successfully",
            "model": TicketAssignedResponse
        },
        400: {
            "description": "Bad Request - Invalid status or no permission"
        },
        401: {
            "description": "Unauthorized"
        },
        404: {
            "description": "Ticket not found"
        },
        409: {
            "description": "Conflict - Ticket already assigned"
        }
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
    
    result = await ticket_service.assign_to_me(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketAssignedResponse(
        message=result["message"],
        ticket_id=result["ticket_id"],
        assignee_name=result["assignee_name"]
    )


@router.patch(
    "/{ticket_id}/status",
    response_model=TicketStatusUpdateResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Status updated successfully",
            "model": TicketStatusUpdateResponse
        },
        400: {
            "description": "Bad Request - Invalid status transition"
        },
        401: {
            "description": "Unauthorized"
        },
        404: {
            "description": "Ticket not found"
        },
        422: {
            "description": "Validation Error"
        }
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
    
    result = await ticket_service.update_ticket_status(
        ticket_id=ticket_id,
        new_status=status_update.status,
        notes=status_update.notes,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketStatusUpdateResponse(
        message=result["message"],
        ticket_id=result["ticket_id"],
        old_status=result["old_status"],
        new_status=result["new_status"]
    )


@router.patch(
    "/{ticket_id}/reassign",
    response_model=TicketReassignResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Ticket reassigned successfully",
            "model": TicketReassignResponse
        },
        400: {
            "description": "Bad Request - Closed, canceled, or resolved ticket"
        },
        401: {
            "description": "Unauthorized"
        },
        404: {
            "description": "Ticket not found"
        },
        422: {
            "description": "Validation Error"
        }
    },
    summary="Toggle Reassign Ticket",
    description="""
    Toggle reassign ticket between Tech and Support teams. The ticket will be UNASSIGNED.
    
    - If current type is **SUPPORT** → changes to **TECH** (unassigned)
    - If current type is **TECH** → changes to **SUPPORT** (unassigned)
    
    The ticket will appear in the unassigned queue for the target team.
    """
)
async def reassign_ticket(
    ticket_id: UUID,
    reassign_data: TicketReassign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Toggle reassign ticket between Tech and Support (unassigned)"""
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    result = await ticket_service.toggle_reassign_ticket(
        ticket_id=ticket_id,
        reason=reassign_data.reason,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketReassignResponse(
        message=result["message"],
        ticket_id=result["ticket_id"],
        new_ticket_type=result["new_ticket_type"]
    )


@router.patch(
    "/{ticket_id}/resolve",
    response_model=TicketResolvedResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Ticket resolved successfully",
            "model": TicketResolvedResponse
        },
        400: {
            "description": "Bad Request - Closed, canceled, or already resolved"
        },
        401: {
            "description": "Unauthorized"
        },
        404: {
            "description": "Ticket not found"
        },
        422: {
            "description": "Validation Error"
        }
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
    
    result = await ticket_service.resolve_ticket(
        ticket_id=ticket_id,
        resolution_notes=resolve_data.resolution_notes,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketResolvedResponse(
        message=result["message"],
        ticket_id=result["ticket_id"],
        resolved_at=result["resolved_at"]
    )


@router.patch(
    "/{ticket_id}/cancel",
    response_model=TicketCanceledResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Ticket canceled successfully",
            "model": TicketCanceledResponse
        },
        400: {
            "description": "Bad Request - Closed or already canceled"
        },
        401: {
            "description": "Unauthorized"
        },
        404: {
            "description": "Ticket not found"
        },
        422: {
            "description": "Validation Error"
        }
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
    
    result = await ticket_service.cancel_ticket(
        ticket_id=ticket_id,
        cancellation_reason=cancel_data.cancellation_reason,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketCanceledResponse(
        message=result["message"],
        ticket_id=result["ticket_id"]
    )


@router.patch(
    "/{ticket_id}/close",
    response_model=TicketClosedResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Ticket closed successfully",
            "model": TicketClosedResponse
        },
        400: {
            "description": "Bad Request - Not resolved or already closed"
        },
        401: {
            "description": "Unauthorized"
        },
        404: {
            "description": "Ticket not found"
        }
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
    
    result = await ticket_service.close_ticket(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketClosedResponse(
        message=result["message"],
        ticket_id=result["ticket_id"],
        closed_at=result["closed_at"]
    )


# ==================== Ticket Messages ====================

@router.get(
    "/{ticket_id}/messages",
    response_model=TicketMessagesListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Messages retrieved successfully",
            "model": TicketMessagesListResponse
        },
        401: {
            "description": "Unauthorized"
        },
        403: {
            "description": "Forbidden - No permission to view this ticket"
        },
        404: {
            "description": "Ticket not found"
        },
        422: {
            "description": "Validation Error"
        }
    },
    summary="Get Ticket Messages",
    description="Retrieves all messages/chat for a specific ticket."
)
async def get_ticket_messages(
    ticket_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
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
    response_model=TicketMessageAddedResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "Message added successfully",
            "model": TicketMessageAddedResponse
        },
        400: {
            "description": "Bad Request - Closed or canceled ticket"
        },
        401: {
            "description": "Unauthorized"
        },
        403: {
            "description": "Forbidden - Not assigned to you"
        },
        404: {
            "description": "Ticket not found"
        },
        422: {
            "description": "Validation Error"
        }
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
    
    result = await ticket_service.create_ticket_message(
        ticket_id=ticket_id,
        message_text=message_data.message_text,
        is_internal_note=message_data.is_internal_note,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return TicketMessageAddedResponse(
        message=result["message"],
        message_id=result["message_id"]
    )


@router.post(
    "/{ticket_id}/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "File uploaded successfully",
            "model": FileUploadResponse
        },
        400: {
            "description": "Bad Request - File too large or invalid type"
        },
        401: {
            "description": "Unauthorized"
        },
        403: {
            "description": "Forbidden - No permission"
        },
        404: {
            "description": "Ticket not found"
        }
    },
    summary="Upload File to Ticket",
    description="""
    Upload attachment (image, document) to ticket.
    
    **Rules**:
    - Max file size: 10 MB
    - Allowed types: jpg, jpeg, png, gif, pdf, doc, docx, txt, csv, xlsx
    """
)
async def upload_ticket_file(
    ticket_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Upload file to ticket"""
    import shutil
    from pathlib import Path
    import time
    
    MAX_FILE_SIZE = 10 * 1024 * 1024
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        raise BadRequestException("File size exceeds 10 MB limit")
    
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx', '.txt', '.csv', '.xlsx'}
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise BadRequestException(f"File type {file_extension} not allowed")
    
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    # Verify access
    await ticket_service.get_ticket_details(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    upload_dir = Path("uploads/tickets") / str(ticket_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = upload_dir / safe_filename
    
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    logger.info(f"File uploaded: {file_path}")
    
    return FileUploadResponse(
        filename=file.filename,
        file_path=str(file_path),
        file_size=file_size,
        content_type=file.content_type or "application/octet-stream"
    )


# ==================== Admin Endpoints ====================

@router.get(
    "/admin/all",
    response_model=TicketSimpleListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Tickets retrieved successfully",
            "model": TicketSimpleListResponse
        },
        401: {
            "description": "Unauthorized"
        },
        403: {
            "description": "Forbidden - Admin only"
        },
        422: {
            "description": "Validation Error"
        }
    },
    summary="Get All Tickets (Admin)",
    description="Retrieves all tickets with filters. Admin only. Returns simplified response."
)
async def get_all_tickets_admin(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[TicketStatus] = Query(None, description="Filter by status"),
    priority: Optional[TicketPriority] = Query(None, description="Filter by priority"),
    ticket_type: Optional[TicketType] = Query(None, description="Filter by type"),
    is_closed: Optional[bool] = Query(None, description="Filter by closed status"),
    assignee_id: Optional[UUID] = Query(None, description="Filter by assignee"),
    sort_by: str = Query("created_at", description="Sort by: created_at, updated_at, priority, status, title, customer_name"),
    search: Optional[str] = Query(None, min_length=2, description="Search in title, customer info"),
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
    
    ticket_responses = [TicketSimpleResponse(**t) for t in tickets]
    
    return TicketSimpleListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=ticket_responses
    )


@router.get(
    "/admin/{ticket_id}",
    response_model=TicketDetailedResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Ticket details retrieved successfully",
            "model": TicketDetailedResponse
        },
        401: {
            "description": "Unauthorized"
        },
        403: {
            "description": "Forbidden - Admin only"
        },
        404: {
            "description": "Ticket not found"
        }
    },
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


@router.delete(
    "/admin/{ticket_id}",
    response_model=TicketDeletedResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Ticket deleted successfully",
            "model": TicketDeletedResponse
        },
        401: {
            "description": "Unauthorized"
        },
        403: {
            "description": "Forbidden - Admin only"
        },
        404: {
            "description": "Ticket not found"
        }
    },
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
    
    result = await ticket_service.delete_ticket_admin(
        ticket_id=ticket_id,
        deleted_by_user_id=current_user.id
    )
    
    return TicketDeletedResponse(
        message=result["message"],
        ticket_id=result["ticket_id"]
    )


@router.get(
    "/admin/statistics",
    response_model=TicketStatistics,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Statistics retrieved successfully",
            "model": TicketStatistics
        },
        401: {
            "description": "Unauthorized"
        },
        403: {
            "description": "Forbidden - Admin only"
        }
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