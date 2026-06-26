import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from services.ticket_service import TicketService
from models.ticket import Ticket, TicketStatus, TicketPriority, TicketType
from utils.exceptions import NotFoundException, BadRequestException, ConflictException

class MockResult:
    def __init__(self, data): self.data = data
    def scalars(self): return self
    def all(self): return self.data if isinstance(self.data, list) else [self.data]
    def scalar_one_or_none(self): return self.data[0] if isinstance(self.data, list) and self.data else self.data
    def scalar(self): return self.data

@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    session.add = MagicMock() 
    session.refresh = AsyncMock()
    return session

@pytest.fixture
def ticket_service(mock_db_session):
    return TicketService(db=mock_db_session)

@pytest.fixture
def mock_ticket():
    ticket = MagicMock(spec=Ticket)
    ticket.id = uuid4()
    ticket.title = "Test Ticket"
    ticket.status = TicketStatus.OPEN
    ticket.priority = TicketPriority.MEDIUM
    ticket.ticket_type = TicketType.SUPPORT
    ticket.customer_email = "customer@example.com"
    ticket.customer_name = "John Doe"
    ticket.assignee_id = None
    ticket.is_active = True
    ticket.is_closed = False
    return ticket

@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid4()
    user.full_name = "Agent Name"
    user.email = "agent@system.com"
    return user

@pytest.mark.asyncio
async def test_create_external_ticket(ticket_service, mock_db_session):
    ticket_data = MagicMock()
    ticket_data.title = "Help me"
    ticket_data.priority = TicketPriority.URGENT
    ticket_data.description = "..."
    ticket_data.external_customer_id = "123"
    ticket_data.customer_email = "c@e.com"
    ticket_data.customer_name = "Cust"
    
    ticket = await ticket_service.create_external_ticket(ticket_data)
    assert ticket.ticket_type == TicketType.SUPPORT
    mock_db_session.add.assert_called_once()

@pytest.mark.asyncio
async def test_get_my_tickets_role_filtering(ticket_service, mock_db_session, mock_ticket):
    mock_db_session.execute.side_effect = [MockResult(1), MockResult([mock_ticket])]
    tickets, total = await ticket_service.get_my_tickets(uuid4(), ["Support User"], page=1, limit=10)
    assert total == 1
    assert len(tickets) == 1

@pytest.mark.asyncio
@patch("services.ticket_service.email_service")
async def test_assign_to_me_success(mock_email, ticket_service, mock_db_session, mock_ticket, mock_user):
    mock_db_session.execute.side_effect = [MockResult(mock_ticket), MockResult(mock_user)]
    result = await ticket_service.assign_to_me(mock_ticket.id, mock_user.id, ["Admin"])
    assert mock_ticket.assignee_id == mock_user.id
    assert mock_ticket.status == TicketStatus.IN_PROGRESS

@pytest.mark.asyncio
async def test_assign_to_me_already_assigned(ticket_service, mock_db_session, mock_ticket, mock_user):
    mock_ticket.assignee_id = uuid4() 
    # نحتاج نتيجتين للاستعلامين المتتاليين داخل الدالة
    mock_db_session.execute.side_effect = [MockResult(mock_ticket), MockResult(mock_user)]
    with pytest.raises(ConflictException):
        await ticket_service.assign_to_me(mock_ticket.id, uuid4(), ["Admin"])

@pytest.mark.asyncio
async def test_update_status_invalid_transition(ticket_service, mock_db_session, mock_ticket):
    mock_ticket.status = TicketStatus.OPEN
    mock_db_session.execute.return_value = MockResult(mock_ticket)
    with pytest.raises(BadRequestException):
        await ticket_service.update_ticket_status(mock_ticket.id, TicketStatus.CLOSED, "notes", uuid4(), ["Admin"])

@pytest.mark.asyncio
async def test_toggle_reassign_ticket(ticket_service, mock_db_session, mock_ticket):
    mock_ticket.ticket_type = TicketType.SUPPORT
    mock_ticket.assignee_id = uuid4()
    mock_db_session.execute.return_value = MockResult(mock_ticket)
    result = await ticket_service.toggle_reassign_ticket(mock_ticket.id, "Need tech", uuid4(), ["Admin"])
    assert mock_ticket.ticket_type == TicketType.TECH
    assert mock_ticket.assignee_id is None

@pytest.mark.asyncio
async def test_get_ticket_statistics_admin(ticket_service, mock_db_session):
    mock_db_session.execute.side_effect = [MockResult(100)] + [MockResult(5)] * 23
    stats = await ticket_service.get_ticket_statistics_admin()
    assert stats["total_tickets"] == 100