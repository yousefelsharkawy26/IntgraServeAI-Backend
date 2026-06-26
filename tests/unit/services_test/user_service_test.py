import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from services.user_service import UserService
from models.user import User, Role
from utils.schemas.user_schemas import (
    UserCreate, UserUpdateBasicInfo, UserUpdateRoles, 
    MyProfileUpdate, MyPasswordChange
)
from utils.exceptions import NotFoundException, ConflictException, AuthenticationException

# ============================================================================
# Helper Class
# ============================================================================

class MockResult:
    def __init__(self, data): self.data = data
    def scalars(self): return self
    def unique(self): return self
    def all(self): return self.data if isinstance(self.data, list) else [self.data]
    def scalar_one_or_none(self): return self.data[0] if isinstance(self.data, list) and self.data else self.data
    def scalar_one(self): return self.data[0] if isinstance(self.data, list) and self.data else self.data
    def scalar(self): return self.data

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session

@pytest.fixture
def user_service(mock_db_session):
    return UserService(db=mock_db_session)

@pytest.fixture
def mock_role():
    # إزالة spec=Role لتجنب تعارضات SQLAlchemy الداخلية أثناء الـ Mocking
    role = MagicMock()
    role.id = uuid4()
    role.name = "Support"
    return role

@pytest.fixture
def mock_user(mock_role):
    # إزالة spec=User
    user = MagicMock()
    user.id = uuid4()
    user.email = "original@test.com"
    user.full_name = "Original Name"
    user.password_hash = "hashed_old_password"
    user.is_active = True
    user.roles = [mock_role]
    return user

# ============================================================================
# Tests: User Creation
# ============================================================================

@pytest.mark.asyncio
@patch("services.user_service.get_password_hash")
async def test_create_user_success(mock_hash, user_service, mock_db_session, mock_role, mock_user):
    mock_hash.return_value = "hashed_pwd"
    
    mock_db_session.execute.side_effect = [
        MockResult(None),      
        MockResult(mock_role), 
        MockResult(mock_user)  
    ]
    
    # استخدام بيانات مطابقة لشروط Pydantic (8 أحرف + دور واحد)
    user_data = UserCreate(
        email="new@test.com", 
        password="strong_password_123", 
        full_name="New User", 
        roles_id=[mock_role.id]
    )
    
    user = await user_service.create_user(user_data, uuid4())
    assert user is not None
    mock_db_session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_create_user_conflict(user_service, mock_db_session, mock_user):
    mock_db_session.execute.return_value = MockResult(mock_user)
    
    # نستخدم model_construct لتخطي تحقق Pydantic واختبار منطق الـ Service
    user_data = UserCreate.model_construct(
        email="exists@test.com"
    )
    
    with pytest.raises(ConflictException):
        await user_service.create_user(user_data, uuid4())

# ============================================================================
# Tests: Password Management
# ============================================================================

@pytest.mark.asyncio
@patch("services.user_service.verify_password")
@patch("services.user_service.get_password_hash")
async def test_change_my_password_success(mock_hash, mock_verify, user_service, mock_db_session, mock_user):
    mock_db_session.execute.return_value = MockResult(mock_user)
    mock_verify.return_value = True
    mock_hash.return_value = "new_hash"
    
    # كلمات مرور طويلة لإرضاء Pydantic
    pwd_data = MyPasswordChange(
        current_password="old_password_123", 
        new_password="new_password_123"
    )
    await user_service.change_my_password(mock_user.id, pwd_data)
    assert mock_user.password_hash == "new_hash"

@pytest.mark.asyncio
@patch("services.user_service.verify_password")
async def test_change_my_password_incorrect(mock_verify, user_service, mock_db_session, mock_user):
    mock_db_session.execute.return_value = MockResult(mock_user)
    mock_verify.return_value = False 
    
    pwd_data = MyPasswordChange.model_construct(
        current_password="wrong", 
        new_password="short"
    )
    
    with pytest.raises(AuthenticationException):
        await user_service.change_my_password(mock_user.id, pwd_data)

# ============================================================================
# Tests: Bulk Operations
# ============================================================================

@pytest.mark.asyncio
async def test_bulk_deactivate_users(user_service, mock_db_session):
    """اختبار تعطيل مجموعة من المستخدمين باستخدام كائنات منفصلة لكل مستخدم"""
    user1 = MagicMock(); user1.is_active = True; user1.email = "u1@t.com"
    user2 = MagicMock(); user2.is_active = True; user2.email = "u2@t.com"
    
    # إرجاع user1 ثم user2 عند البحث بكل ID
    mock_db_session.execute.side_effect = [MockResult(user1), MockResult(user2)]
    
    ids = [uuid4(), uuid4()]
    result = await user_service.bulk_deactivate_users(ids, uuid4())
    
    assert result["successful"] == 2
    assert user1.is_active is False
    assert user2.is_active is False

# ============================================================================
# Statistics & List (تستمر كما هي لأنها كانت ناجحة)
# ============================================================================

@pytest.mark.asyncio
async def test_get_user_statistics(user_service, mock_db_session, mock_role):
    mock_db_session.execute.side_effect = [
        MockResult(100), MockResult(80), MockResult(90), 
        MockResult([mock_role]), MockResult(40), MockResult(10), MockResult(5)
    ]
    stats = await user_service.get_user_statistics()
    assert stats["total_users"] == 100

@pytest.mark.asyncio
async def test_list_users_with_search(user_service, mock_db_session, mock_user):
    mock_db_session.execute.side_effect = [MockResult(1), MockResult([mock_user])]
    users, total = await user_service.list_users(uuid4(), search="test")
    assert total == 1