# apis/v1/tickets.py
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from core.database import get_db
from services.ticket_service import TicketService
from utils.schemas.ticket_schemas import (
    ExternalTicketCreate,
    ExternalTicketCreateResponse,
    TicketResponse,
    TicketListResponse
)
from utils.schemas.auth_schemas import MessageResponse
from utils.dependencies import get_current_active_user
from models.user import User

router = APIRouter()


# ==================== Public Endpoint (No Auth) ====================

@router.post(
    "/external/create",
    response_model=ExternalTicketCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Ticket created successfully"},
        422: {"description": "Validation errors"}
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
    
    This endpoint is designed for integration with external systems.
    The external system sends customer support requests, and we create tickets.
    
    **Request Body**:
    - **external_customer_id**: Customer ID in external system (optional)
    - **customer_email**: Customer email address (required)
    - **customer_name**: Customer full name (required)
    - **title**: Ticket title/subject (required, min 5 chars)
    - **description**: Detailed issue description (required, min 10 chars)
    - **priority**: LOW | MEDIUM | HIGH | URGENT (optional, default: MEDIUM)
    - **category**: TECHNICAL | BILLING | GENERAL | COMPLAINT | FEATURE_REQUEST (optional)
    
    **Response**:
    - **message**: Success message
    - **ticket_id**: UUID of created ticket
    - **status**: Current ticket status (OPEN)
    - **estimated_response_time**: Based on priority (e.g., "4 hours")
    
    **SLA Response Times**:
    - URGENT: 1 hour
    - HIGH: 4 hours
    - MEDIUM: 12 hours
    - LOW: 24 hours
    """
    ticket_service = TicketService(db)
    ticket, estimated_time = await ticket_service.create_external_ticket(ticket_data)
    
    return ExternalTicketCreateResponse(
        message="Ticket created successfully",
        ticket_id=ticket.id,
        status=ticket.status,
        estimated_response_time=estimated_time
    )


# ==================== Authenticated Endpoints ====================

@router.get(
    "/my-tickets",
    response_model=TicketListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get My Tickets",
    description="Retrieves tickets assigned to the current user."
)
async def get_my_tickets(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get tickets assigned to me
    
    **Authenticated users only**
    
    Returns a paginated list of tickets assigned to the current user.
    
    **Role-Based Filtering**:
    - **Tech User**: sees only TECH tickets assigned to them
    - **Support User**: sees only SUPPORT tickets assigned to them
    - **Admin**: sees all tickets assigned to them (both TECH and SUPPORT)
    
    **Query Parameters**:
    - **page**: Page number (default: 1)
    - **limit**: Items per page (default: 10, max: 100)
    
    **Sorting**:
    - Results are sorted by creation date (newest first)
    
    **Example**:
    ```
    GET /api/v1/tickets/my-tickets?page=1&limit=10
    ```
    """
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    tickets, total = await ticket_service.get_my_tickets(
        current_user_id=current_user.id,
        user_roles=user_roles,
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
    "/unassigned",
    response_model=TicketListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Unassigned Tickets",
    description="Retrieves tickets that are not assigned to anyone."
)
async def get_unassigned_tickets(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get unassigned tickets
    
    **Authenticated users only**
    
    Returns a paginated list of tickets that are not assigned to anyone.
    Users can pick tickets from this list using the "assign-to-me" endpoint.
    
    **Role-Based Filtering**:
    - **Tech User**: sees only unassigned TECH tickets
    - **Support User**: sees only unassigned SUPPORT tickets
    - **Admin**: sees all unassigned tickets (both TECH and SUPPORT)
    
    **Filters Applied Automatically**:
    - `assignee_id` is NULL (not assigned)
    - `status` is OPEN
    - `is_active` is True
    
    **Query Parameters**:
    - **page**: Page number (default: 1)
    - **limit**: Items per page (default: 10, max: 100)
    
    **Sorting**:
    - Results are sorted by:
      1. Priority (URGENT → HIGH → MEDIUM → LOW)
      2. Creation date (oldest first - FIFO)
    
    **Example**:
    ```
    GET /api/v1/tickets/unassigned?page=1&limit=20
    ```
    """
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    tickets, total = await ticket_service.get_unassigned_tickets(
        user_roles=user_roles,
        page=page,
        limit=limit
    )
    
    return TicketListResponse(
        page=page,
        limit=limit,
        total=total,
        tickets=tickets
    )


@router.patch(
    "/{ticket_id}/assign-to-me",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Ticket assigned successfully"},
        404: {"description": "Ticket not found"},
        400: {"description": "Bad request - Cannot assign this ticket"},
        409: {"description": "Conflict - Ticket already assigned"}
    },
    summary="Assign Ticket to Me",
    description="Self-assign an unassigned ticket to the current user."
)
async def assign_ticket_to_me(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Self-assign an unassigned ticket
    
    **Authenticated users only**
    
    Assigns the specified ticket to the current user and changes its status to IN_PROGRESS.
    
    **Path Parameters**:
    - **ticket_id**: UUID of the ticket to assign
    
    **Validations**:
    1. ✅ Ticket must exist and be active
    2. ✅ Ticket must be unassigned (`assignee_id` is NULL)
    3. ✅ Ticket status must be OPEN
    4. ✅ Ticket type must match user role:
       - Tech User can only assign TECH tickets
       - Support User can only assign SUPPORT tickets
       - Admin can assign any ticket
    
    **Race Condition Protection**:
    This endpoint uses database row locking to prevent two users from
    assigning the same ticket simultaneously. If two users try to assign
    the same ticket at the same time, only the first one succeeds.
    The second user receives a 409 Conflict error.
    
    **What Happens on Success**:
    - `assignee_id` is set to current user's ID
    - `assigned_at` is set to current timestamp
    - `status` changes from OPEN to IN_PROGRESS
    - Audit log entry is created
    
    **Example**:
    ```
    PATCH /api/v1/tickets/123e4567-e89b-12d3-a456-426614174000/assign-to-me
    ```
    
    **Error Examples**:
    - **404**: Ticket not found
    - **400**: Cannot assign ticket with status: RESOLVED
    - **400**: Tech Users can only assign TECH tickets
    - **409**: Ticket already assigned to John Doe
    """
    ticket_service = TicketService(db)
    user_roles = [role.name for role in current_user.roles]
    
    await ticket_service.assign_to_me(
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        user_roles=user_roles
    )
    
    return MessageResponse(message="Ticket assigned to you successfully")