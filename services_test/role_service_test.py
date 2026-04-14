import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from services.role_service import RoleService
from utils.schemas.role_schemas import RoleUpdate
from utils.schemas.user_schemas import UserResponse
from utils.exceptions import NotFoundException, ConflictException, BadRequestException

# ============================================================================
# Helper Class for SQLAlchemy Mocking
# ============================================================================

class MockResult:
    """
    كلاس مساعد لمحاكاة النتائج المعقدة الراجعة من SQLAlchemy
    يدعم: scalar_one_or_none(), scalars().all(), scalars().unique().all(), scalar()
    """
    def __init__(self, data):
        self.data = data

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self.data if isinstance(self.data, list) else [self.data]

    def scalar_one_or_none(self):
        return self.data[0] if isinstance(self.data, list) and self.data else self.data

    def scalar(self):
        # يستخدم عادة في إرجاع الأرقام مثل count()
        return self.data


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db_session():
    """محاكاة جلسة قاعدة البيانات"""
    session = AsyncMock()
    return session

@pytest.fixture
def role_service(mock_db_session):
    """تهيئة الخدمة مع الجلسة الوهمية"""
    return RoleService(db=mock_db_session)

@pytest.fixture
def mock_role():
    """رول وهمي للاختبارات"""
    role = MagicMock()
    role.id = uuid4()
    role.name = "admin"
    role.description = "Administrator role"
    return role

@pytest.fixture
def mock_user(mock_role):
    """مستخدم وهمي للاختبارات مرتبط برول"""
    user = MagicMock()
    user.id = uuid4()
    user.email = "user@example.com"
    user.email_confirmed = True
    user.full_name = "Test User"
    user.is_active = True
    user.last_login = datetime.now(timezone.utc)
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    user.roles = [mock_role]
    return user

# ============================================================================
# Tests: Read Operations (Get Roles)
# ============================================================================

@pytest.mark.asyncio
async def test_get_all_roles(role_service, mock_db_session, mock_role):
    """اختبار جلب جميع الرتب"""
    # محاكاة إرجاع قائمة تحتوي على رول واحد
    mock_db_session.execute.return_value = MockResult([mock_role])
    
    roles = await role_service.get_all_roles()
    
    assert len(roles) == 1
    assert roles[0].name == "admin"

@pytest.mark.asyncio
async def test_get_role_by_id(role_service, mock_db_session, mock_role):
    """اختبار جلب رتبة باستخدام الـ ID"""
    mock_db_session.execute.return_value = MockResult(mock_role)
    
    role = await role_service.get_role_by_id(mock_role.id)
    
    assert role is not None
    assert role.name == "admin"

@pytest.mark.asyncio
async def test_get_user_roles_success(role_service, mock_db_session, mock_user):
    """اختبار جلب رتب مستخدم معين بنجاح"""
    mock_db_session.execute.return_value = MockResult(mock_user)
    
    result = await role_service.get_user_roles(mock_user.id)
    
    assert "roles" in result
    assert len(result["roles"]) == 1
    assert result["roles"][0]["name"] == "admin"

@pytest.mark.asyncio
async def test_get_user_roles_not_found(role_service, mock_db_session):
    """اختبار جلب رتب لمستخدم غير موجود"""
    mock_db_session.execute.return_value = MockResult(None)
    
    with pytest.raises(NotFoundException):
        await role_service.get_user_roles(uuid4())

# ============================================================================
# Tests: Update Operations
# ============================================================================

@pytest.mark.asyncio
async def test_update_role_success(role_service, mock_db_session, mock_role):
    """اختبار تعديل بيانات الرتبة بنجاح (مع تسجيل Audit Log)"""
    
    # عند التحديث، الخدمة تقوم باستعلامين: 1. جلب الرول, 2. التحقق من أن الاسم الجديد غير مستخدم
    # سنستخدم side_effect لإرجاع نتائج مختلفة بالترتيب
    mock_db_session.execute.side_effect = [
        MockResult(mock_role),  # نتيجة get_role_by_id
        MockResult(None)        # نتيجة get_role_by_name (لم يجد رول آخر بنفس الاسم)
    ]
    
    update_data = RoleUpdate(name="super_admin", description="New description")
    user_id = uuid4()
    
    updated_role = await role_service.update_role(mock_role.id, update_data, user_id)
    
    assert updated_role.name == "super_admin"
    assert updated_role.description == "New description"
    mock_db_session.add.assert_called_once()  # التحقق من إنشاء AuditLog
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()

@pytest.mark.asyncio
async def test_update_role_conflict(role_service, mock_db_session, mock_role):
    """اختبار محاولة تغيير اسم الرتبة لاسم موجود بالفعل"""
    
    existing_role = MagicMock()
    existing_role.name = "manager"
    
    # 1. يجد الرول المراد تحديثه, 2. يجد رول آخر يحمل نفس الاسم الجديد
    mock_db_session.execute.side_effect = [
        MockResult(mock_role),
        MockResult(existing_role)
    ]
    
    update_data = RoleUpdate(name="manager")
    
    with pytest.raises(ConflictException) as exc:
        await role_service.update_role(mock_role.id, update_data, uuid4())
    assert "already exists" in str(exc.value)

@pytest.mark.asyncio
async def test_update_role_no_changes(role_service, mock_db_session, mock_role):
    """اختبار محاولة تحديث رتبة بدون تمرير بيانات جديدة"""
    
    mock_db_session.execute.return_value = MockResult(mock_role)
    
    # إرسال نفس البيانات الحالية
    update_data = RoleUpdate(name="admin", description="Administrator role")
    
    with pytest.raises(BadRequestException) as exc:
        await role_service.update_role(mock_role.id, update_data, uuid4())
    assert "No changes provided" in str(exc.value)

# ============================================================================
# Tests: Advanced Queries (Pagination & Statistics)
# ============================================================================

@pytest.mark.asyncio
async def test_get_users_by_role_success(role_service, mock_db_session, mock_role, mock_user):
    """اختبار جلب المستخدمين التابعين لرتبة معينة (مع الـ Pagination)"""
    
    # هذه الدالة تنفذ 3 استعلامات بالترتيب:
    # 1. التحقق من وجود الرول
    # 2. جلب عدد المستخدمين (Count)
    # 3. جلب قائمة المستخدمين
    mock_db_session.execute.side_effect = [
        MockResult(mock_role),  # get_role_by_id
        MockResult(5),          # count query returns 5
        MockResult([mock_user]) # users query returns list
    ]
    
    users, total = await role_service.get_users_by_role(mock_role.id, page=1, limit=10)
    
    assert total == 5
    assert len(users) == 1
    assert isinstance(users[0], UserResponse)
    assert users[0].email == "user@example.com"
    assert "admin" in users[0].roles

@pytest.mark.asyncio
async def test_get_role_statistics(role_service, mock_db_session, mock_role):
    """اختبار جلب إحصائيات الرتب (إجمالي مستخدمين، نشطين، غير نشطين)"""
    
    # الدالة تقوم بـ:
    # 1. استعلام لجلب كل الرتب (سنفترض وجود رول واحد)
    # 2. استعلام للـ Total Users لهذا الرول
    # 3. استعلام للـ Active Users لهذا الرول
    mock_db_session.execute.side_effect = [
        MockResult([mock_role]), # get all roles
        MockResult(10),          # total users = 10
        MockResult(8)            # active users = 8
    ]
    
    stats = await role_service.get_role_statistics()
    
    assert stats["total_roles"] == 1
    assert len(stats["roles"]) == 1
    
    role_stat = stats["roles"][0]
    assert role_stat["name"] == "admin"
    assert role_stat["user_count"] == 10
    assert role_stat["active_users"] == 8
    assert role_stat["inactive_users"] == 2  # 10 - 8 = 2