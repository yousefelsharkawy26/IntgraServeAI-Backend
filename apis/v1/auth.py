# apis/v1/auth.py
from fastapi import APIRouter, Depends, status, Response, Cookie, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from core.database import get_db
from core.config import settings
from services.auth_service import AuthService
from utils.schemas.auth_schemas import (
    LoginRequest,
    TokenResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    MessageResponse,
    ErrorResponse,
    ValidationErrorResponse
)
from utils.exceptions import (
    AuthenticationException,
    ValidationException,
    InvalidTokenException,
    UnauthorizedException
)
from utils.rate_limiter import rate_limit_by_ip, rate_limit_by_ip_and_field
from utils.token_helper import TokenHelper
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Login successful", "model": TokenResponse},
        401: {"description": "Invalid credentials", "model": ErrorResponse},
        422: {"description": "Validation errors", "model": ValidationErrorResponse}
    },
    summary="User Login",
    description="Authenticate user. Returns access token in response body and sets refresh token in httpOnly cookie."
)
async def login(
    response: Response,
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_by_ip_and_field("email")),
):
    """Login endpoint"""
    try:
        auth_service = AuthService(db)
        access_token, refresh_token = await auth_service.login(credentials)
        
        # Set refresh token in httpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="none" if not settings.DEBUG else "lax",
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            path="/api/v1/auth"
        )
        
        return {"token": access_token}
    
    except (AuthenticationException, ValidationException) as e:
        raise e
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        raise AuthenticationException("An error occurred during login")


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Password reset link sent", "model": ForgotPasswordResponse},
        422: {"description": "Validation errors", "model": ValidationErrorResponse}
    },
    summary="Forgot Password",
    description="Send password reset link to user's email address."
)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_by_ip_and_field("email")),
):
    """Forgot password endpoint"""
    try:
        auth_service = AuthService(db)
        result = await auth_service.forgot_password(request)
        return result
    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}", exc_info=True)
        # Always return success to prevent email enumeration
        return {"message": "Password reset Link have been sent to your email."}


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Password reset successful", "model": ResetPasswordResponse},
        400: {"description": "Invalid or expired token", "model": ErrorResponse},
        422: {"description": "Validation errors", "model": ValidationErrorResponse}
    },
    summary="Reset Password",
    description="Reset user password using token from email."
)
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_by_ip()),
):
    """Reset password endpoint"""
    try:
        auth_service = AuthService(db)
        result = await auth_service.reset_password(request.token, request)
        return result
    except (InvalidTokenException, ValidationException) as e:
        raise e
    except Exception as e:
        logger.error(f"Reset password error: {str(e)}", exc_info=True)
        raise InvalidTokenException("An error occurred during password reset")


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Token refreshed successfully", "model": TokenResponse},
        401: {"description": "Invalid or expired refresh token", "model": ErrorResponse}
    },
    summary="Refresh Access Token",
    description="Get a new access token using refresh token from cookie."
)
async def refresh_token(
    refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_by_ip()),
):
    """Refresh token endpoint"""
    
    if not refresh_token:
        raise UnauthorizedException("Refresh token not found")
    
    # Check blacklist before accepting the refresh token
    if await TokenHelper.is_token_blacklisted(refresh_token, db):
        raise UnauthorizedException("Refresh token has been revoked")
    
    try:
        auth_service = AuthService(db)
        access_token = await auth_service.refresh_access_token(refresh_token)
        return {"token": access_token}
    
    except (AuthenticationException, UnauthorizedException) as e:
        raise e
    except Exception as e:
        logger.error(f"Refresh token error: {str(e)}", exc_info=True)
        raise UnauthorizedException("Invalid refresh token")


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Logout successful", "model": MessageResponse}
    },
    summary="User Logout",
    description="Logout user and clear refresh token cookie."
)
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
):
    """Logout endpoint — blacklists the refresh token so it cannot be reused."""
    if refresh_token:
        try:
            await TokenHelper.blacklist_token(refresh_token, "refresh", db)
        except Exception:
            # Still clear the cookie even if blacklisting fails
            logger.warning("Failed to blacklist refresh token during logout", exc_info=True)
    
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth"
    )
    return {"message": "Logged out successfully"}