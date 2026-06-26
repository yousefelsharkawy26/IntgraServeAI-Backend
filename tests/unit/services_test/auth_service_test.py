import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from services.auth_service import AuthService
from utils.schemas.auth_schemas import LoginRequest, ForgotPasswordRequest, ResetPasswordRequest
from utils.exceptions import (
    AuthenticationException,
    InvalidTokenException,
    ValidationException
)

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db_session():
    """محاكاة جلسة قاعدة البيانات (AsyncSession)"""
    return AsyncMock()

@pytest.fixture
def auth_service(mock_db_session):
    """حقن جلسة قاعدة البيانات الوهمية داخل الخدمة"""
    return AuthService(db=mock_db_session)

@pytest.fixture
def mock_user():
    """مستخدم وهمي للاختبارات"""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.password_hash = "hashed_password"
    user.is_active = True
    user.full_name = "Test User"
    return user

def mock_db_result(return_value):
    """
    دالة مساعدة لمحاكاة النتيجة الراجعة من SQLAlchemy 
    db.execute(...) -> returns Synchronous Result -> scalar_one_or_none()
    """
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = return_value
    return mock_result

# ============================================================================
# Tests: Login
# ============================================================================

@pytest.mark.asyncio
@patch("services.auth_service.verify_password")
@patch("services.auth_service.TokenHelper")
async def test_login_success(mock_token_helper, mock_verify_password, auth_service, mock_db_session, mock_user):
    """اختبار تسجيل الدخول بنجاح"""
    
    mock_db_session.execute.return_value = mock_db_result(mock_user)
    mock_verify_password.return_value = True
    mock_token_helper.create_access_token.return_value = "access_token_123"
    mock_token_helper.create_refresh_token.return_value = "refresh_token_123"
    
    request = LoginRequest(email="test@example.com", password="password123")
    access, refresh = await auth_service.login(request)
    
    assert access == "access_token_123"
    assert refresh == "refresh_token_123"
    mock_db_session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_not_found(auth_service, mock_db_session):
    """اختبار محاولة تسجيل دخول بإيميل غير موجود"""
    
    mock_db_session.execute.return_value = mock_db_result(None)
    request = LoginRequest(email="wrong@example.com", password="password123")
    
    with pytest.raises(AuthenticationException) as exc:
        await auth_service.login(request)
    assert "Invalid email or password" in str(exc.value)

@pytest.mark.asyncio
async def test_login_inactive_user(auth_service, mock_db_session, mock_user):
    """اختبار محاولة تسجيل دخول لمستخدم غير مفعل"""
    
    mock_user.is_active = False
    mock_db_session.execute.return_value = mock_db_result(mock_user)
    request = LoginRequest(email="test@example.com", password="password123")
    
    with pytest.raises(AuthenticationException) as exc:
        await auth_service.login(request)
    assert "Account is inactive" in str(exc.value)

@pytest.mark.asyncio
@patch("services.auth_service.verify_password")
async def test_login_wrong_password(mock_verify_password, auth_service, mock_db_session, mock_user):
    """اختبار محاولة تسجيل دخول بكلمة مرور خاطئة"""
    
    mock_db_session.execute.return_value = mock_db_result(mock_user)
    mock_verify_password.return_value = False
    
    request = LoginRequest(email="test@example.com", password="wrong_password")
    
    with pytest.raises(AuthenticationException):
        await auth_service.login(request)

# ============================================================================
# Tests: Forgot Password
# ============================================================================

@pytest.mark.asyncio
@patch("services.auth_service.email_service")
@patch("services.auth_service.TokenHelper")
async def test_forgot_password_success(mock_token_helper, mock_email_service, auth_service, mock_db_session, mock_user):
    """اختبار طلب استعادة كلمة المرور بنجاح"""
    
    mock_db_session.execute.return_value = mock_db_result(mock_user)
    mock_token_helper.create_reset_password_token.return_value = "reset_token_123"
    mock_email_service.send_password_reset_email.return_value = True
    
    request = ForgotPasswordRequest(email="test@example.com")
    result = await auth_service.forgot_password(request)
    
    assert result["message"] == "Password reset Link have been sent to your email."
    mock_email_service.send_password_reset_email.assert_called_once()

@pytest.mark.asyncio
@patch("services.auth_service.email_service")
async def test_forgot_password_user_not_found(mock_email_service, auth_service, mock_db_session):
    """اختبار طلب استعادة كلمة مرور لإيميل غير موجود"""
    
    mock_db_session.execute.return_value = mock_db_result(None)
    request = ForgotPasswordRequest(email="nonexistent@example.com")
    result = await auth_service.forgot_password(request)
    
    assert result["message"] == "Password reset Link have been sent to your email."
    mock_email_service.send_password_reset_email.assert_not_called()

# ============================================================================
# Tests: Reset Password
# ============================================================================

@pytest.mark.asyncio
@patch("services.auth_service.email_service")
@patch("services.auth_service.validate_password_strength")
@patch("services.auth_service.get_password_hash")
@patch("services.auth_service.TokenHelper")
async def test_reset_password_success(
    mock_token_helper, mock_get_password_hash, mock_validate_pwd, mock_email_service, 
    auth_service, mock_db_session, mock_user
):
    """اختبار إعادة تعيين كلمة المرور بنجاح"""
    
    mock_token_helper.verify_reset_password_token.return_value = {
        "user_id": str(mock_user.id),
        "email": mock_user.email
    }
    mock_validate_pwd.return_value = (True, "")
    mock_get_password_hash.return_value = "new_hashed_password"
    mock_db_session.execute.return_value = mock_db_result(mock_user)
    
    request = ResetPasswordRequest(new_password="StrongPassword123!")
    result = await auth_service.reset_password("valid_token", request)
    
    assert result["message"] == "Password has been reset successfully."
    mock_db_session.commit.assert_called_once()
    mock_email_service.send_password_reset_confirmation_email.assert_called_once()

@pytest.mark.asyncio
@patch("services.auth_service.validate_password_strength")
@patch("services.auth_service.TokenHelper")
async def test_reset_password_weak_password(mock_token_helper, mock_validate_pwd, auth_service, mock_user):
    """اختبار إدخال كلمة مرور ضعيفة عند التحديث"""
    
    mock_token_helper.verify_reset_password_token.return_value = {
        "user_id": str(mock_user.id),
        "email": mock_user.email
    }
    mock_validate_pwd.return_value = (False, "Password too weak")
    
    # نستخدم model_construct لتجاوز Pydantic واختبار منطق الخدمة
    request = ResetPasswordRequest.model_construct(new_password="123")
    
    with pytest.raises(ValidationException):
        await auth_service.reset_password("valid_token", request)

# ============================================================================
# Tests: Refresh Token & Logout
# ============================================================================

@pytest.mark.asyncio
@patch("services.auth_service.TokenHelper")
async def test_refresh_access_token_success(mock_token_helper, auth_service, mock_db_session, mock_user):
    """اختبار تجديد التوكن بنجاح"""
    
    mock_token_helper.verify_token.return_value = {"user_id": str(mock_user.id)}
    mock_db_session.execute.return_value = mock_db_result(mock_user)
    mock_token_helper.create_access_token.return_value = "new_access_token"
    
    new_token = await auth_service.refresh_access_token("valid_refresh_token")
    assert new_token == "new_access_token"

@pytest.mark.asyncio
async def test_logout_success(auth_service, mock_db_session, mock_user):
    """اختبار تسجيل الخروج"""
    
    mock_db_session.execute.return_value = mock_db_result(mock_user)
    result = await auth_service.logout(str(mock_user.id))
    
    assert result["message"] == "Logged out successfully"