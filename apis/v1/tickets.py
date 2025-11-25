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
import shutil
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


async def parse_form_with_files(request: Request) -> dict:
    """
    Parse multipart form data with proper file handling
    
    Returns dict with:
    - customer_email: str
    - customer_name: str
    - message_text: str (can be empty)
    - is_internal_note: bool
    - files: List[UploadFile]
    """
    form = await request.form()
    
    # Extract text fields
    customer_email = form.get("customer_email", "")
    customer_name = form.get("customer_name", "")
    message_text = form.get("message_text", "")
    is_internal_note_str = form.get("is_internal_note", "false")
    
    # Convert is_internal_note to bool
    is_internal_note = is_internal_note_str.lower() in ("true", "1", "yes")
    
    # Extract files - handle multiple files with same key
    files = []
    for key in form.keys():
        if key == "files":
            # Get all values for "files" key
            for item in form.getlist("files"):
                if isinstance(item, StarletteUploadFile):
                    # Check if file has actual content
                    if item.filename and item.filename.strip():
                        files.append(item)
    
    return {
        "customer_email": str(customer_email).strip() if customer_email else "",
        "customer_name": str(customer_name).strip() if customer_name else "",
        "message_text": str(message_text).strip() if message_text else "",
        "is_internal_note": is_internal_note,
        "files": files
    }


async def save_uploaded_files(files: List, ticket_id: UUID) -> List[dict]:
    """
    Validate and save uploaded files
    
    Returns list of attachment dictionaries
    """
    attachments = []
    
    if not files:
        return attachments
    
    if len(files) > 5:
        raise BadRequestException("Maximum 5 files allowed per message")
    
    # Create upload directory
    upload_dir = Path("uploads/tickets") / str(ticket_id) / "messages"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Allowed extensions
    allowed_extensions = {
        '.jpg', '.jpeg', '.png', '.gif',
        '.pdf',
        '.doc', '.docx',
        '.txt',
        '.csv', '.xlsx'
    }
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    
    for file in files:
        try:
            # Read file content
            content = await file.read()
            file_size = len(content)
            
            # Reset file position for potential re-read
            await file.seek(0)
            
            # Skip empty files
            if file_size == 0:
                continue
            
            # Validate file size
            if file_size > MAX_FILE_SIZE:
                raise BadRequestException(
                    f"File '{file.filename}' exceeds 10 MB limit (size: {file_size / 1024 / 1024:.2f} MB)"
                )
            
            # Validate file extension
            file_extension = Path(file.filename).suffix.lower()
            if file_extension not in allowed_extensions:
                raise BadRequestException(
                    f"File type '{file_extension}' not allowed. "
                    f"Allowed: {', '.join(sorted(allowed_extensions))}"
                )
            
            # Generate unique filename
            timestamp = int(time.time() * 1000)
            safe_filename = f"{timestamp}_{file.filename}"
            file_path = upload_dir / safe_filename
            
            # Save file
            with open(file_path, "wb") as f:
                f.write(content)
            
            attachments.append({
                "filename": file.filename,
                "file_path": str(file_path),
                "file_size": file_size,
                "content_type": file.content_type or "application/octet-stream"
            })
            
            logger.info(f"File saved: {file_path} ({file_size} bytes)")
            
        except BadRequestException:
            raise
        except Exception as e:
            logger.error(f"Failed to save file {file.filename}: {str(e)}")
            raise BadRequestException(f"Failed to save file '{file.filename}'")
    
    return attachments


# ==================== Public Endpoints (No Auth) ====================

@router.post(
    "/external/create",
    response_model=ExternalTicketCreateResponse,
    status_code=status.HTTP_201_CREATED,
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
    """Create ticket from external system"""
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
    summary="Add Message from External Customer",
    description="""
    Add a message to ticket from external customer. No authentication required.
    
    **Content-Type**: multipart/form-data
    
    **Required Fields**:
    - customer_email: Customer email address
    - customer_name: Customer name (min 2 characters)
    
    **Optional Fields**:
    - message_text: Message text (optional if files provided)
    - files: File attachments (optional if message provided)
    
    **Rules**:
    - Must provide message OR files OR both
    - Max 5 files per message
    - Max 10 MB per file
    - Allowed: jpg, jpeg, png, gif, pdf, doc, docx, txt, csv, xlsx
    
    **Examples**:
    
    1. Message only:
    ```
    customer_email: customer@example.com
    customer_name: John Doe
    message_text: I need help with my order
    ```
    
    2. Files only:
    ```
    customer_email: customer@example.com
    customer_name: John Doe
    files: [file1.pdf]
    ```
    
    3. Message + Files:
    ```
    customer_email: customer@example.com
    customer_name: John Doe
    message_text: See attached screenshots
    files: [screenshot1.png, screenshot2.png]
    ```
    """
)
async def create_external_message(
    ticket_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Add message from external customer with optional files"""
    
    # Parse form data
    form_data = await parse_form_with_files(request)
    
    customer_email = form_data["customer_email"]
    customer_name = form_data["customer_name"]
    message_text = form_data["message_text"]
    files = form_data["files"]
    
    # Validate required fields
    if not customer_email:
        raise ValidationException({"customer_email": "Customer email is required"})
    
    if not validate_email(customer_email):
        raise ValidationException({"customer_email": "Invalid email format"})
    
    if not customer_name:
        raise ValidationException({"customer_name": "Customer name is required"})
    
    if len(customer_name) < 2:
        raise ValidationException({"customer_name": "Customer name must be at least 2 characters"})
    
    # Check content
    has_message = bool(message_text)
    has_files = len(files) > 0
    
    if not has_message and not has_files:
        raise BadRequestException(
            "Must provide either a message, files, or both"
        )
    
    # Process files
    attachments = await save_uploaded_files(files, ticket_id)
    
    # Final message
    final_message = message_text if has_message else "[File(s) attached]"
    
    # Create message
    ticket_service = TicketService(db)
    result = await ticket_service.create_external_message(
        ticket_id=ticket_id,
        customer_email=customer_email,
        customer_name=customer_name,
        message_text=final_message,
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
    summary="Get My Tickets (External Customer)",
    description="Get tickets for external customer by email. No authentication required."
)
async def get_external_customer_tickets(
    customer_email: EmailStr = Query(..., description="Customer email address"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get tickets for external customer"""
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
    summary="Get Ticket Messages (External Customer)",
    description="Get messages for external customer. Internal notes excluded."
)
async def get_external_ticket_messages(
    ticket_id: UUID,
    customer_email: EmailStr = Query(..., description="Customer email"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get ticket messages for external customer"""
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
    summary="Get My Tickets",
    description="Get tickets assigned to current user with role-based filtering."
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
    summary="Get Unassigned Tickets",
    description="Get unassigned tickets with role-based filtering."
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
    summary="Get Ticket Details",
    description="Get ticket details (only tickets assigned to you)."
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
    summary="Assign Ticket to Me",
    description="Self-assign an unassigned ticket."
)
async def assign_ticket_to_me(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Self-assign ticket"""
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
    summary="Update Ticket Status",
    description="Update ticket status."
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
    summary="Toggle Reassign Ticket",
    description="Toggle between Tech and Support teams (ticket becomes unassigned)."
)
async def reassign_ticket(
    ticket_id: UUID,
    reassign_data: TicketReassign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Toggle reassign ticket"""
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
    summary="Resolve Ticket",
    description="Mark ticket as resolved."
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
    
    return TicketResolvedResponse(
        message=result["message"],
        ticket_id=result["ticket_id"],
        resolved_at=result["resolved_at"]
    )


@router.patch(
    "/{ticket_id}/cancel",
    response_model=TicketCanceledResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel Ticket",
    description="Cancel a ticket."
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
    
    return TicketCanceledResponse(
        message=result["message"],
        ticket_id=result["ticket_id"]
    )


@router.patch(
    "/{ticket_id}/close",
    response_model=TicketClosedResponse,
    status_code=status.HTTP_200_OK,
    summary="Close Ticket",
    description="Close a resolved ticket."
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
    
    return TicketClosedResponse(
        message=result["message"],
        ticket_id=result["ticket_id"],
        closed_at=result["closed_at"]
    )


# ==================== Ticket Messages (Authenticated) ====================

@router.get(
    "/{ticket_id}/messages",
    response_model=TicketMessagesListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ticket Messages",
    description="Get messages for a ticket (only your tickets)."
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
    summary="Add Message to Ticket",
    description="""
    Add message to ticket with optional files (authenticated).
    
    **Content-Type**: multipart/form-data
    
    **Fields**:
    - message_text: Message text (optional if files provided)
    - is_internal_note: true/false (default: false)
    - files: File attachments (optional if message provided)
    
    **Rules**:
    - Must provide message OR files OR both
    - Max 5 files, 10 MB each
    """
)
async def create_ticket_message(
    ticket_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Add message to ticket"""
    
    # Parse form data
    form_data = await parse_form_with_files(request)
    
    message_text = form_data["message_text"]
    is_internal_note = form_data["is_internal_note"]
    files = form_data["files"]
    
    # Check content
    has_message = bool(message_text)
    has_files = len(files) > 0
    
    if not has_message and not has_files:
        raise BadRequestException(
            "Must provide either a message, files, or both"
        )
    
    # Process files
    attachments = await save_uploaded_files(files, ticket_id)
    
    # Final message
    final_message = message_text if has_message else "[File(s) attached]"
    
    # Create message
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
    
    return TicketMessageAddedResponse(
        message=result["message"],
        message_id=result["message_id"]
    )


# ==================== Admin Endpoints ====================

@router.get(
    "/admin/all",
    response_model=TicketSimpleListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get All Tickets (Admin)",
    description="Get all tickets with filters. Admin only."
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
    summary="Get Ticket Details (Admin)",
    description="Get complete ticket details. Admin only."
)
async def get_ticket_details_admin(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get ticket details (Admin)"""
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
    summary="Delete Ticket (Admin)",
    description="Soft delete ticket. Admin only."
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
    
    return TicketDeletedResponse(
        message=result["message"],
        ticket_id=result["ticket_id"]
    )


@router.get(
    "/admin/statistics",
    response_model=TicketStatistics,
    status_code=status.HTTP_200_OK,
    summary="Get Ticket Statistics (Admin)",
    description="Get ticket statistics. Admin only."
)
async def get_ticket_statistics_admin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get ticket statistics"""
    ticket_service = TicketService(db)
    stats = await ticket_service.get_ticket_statistics_admin()
    return TicketStatistics(**stats)