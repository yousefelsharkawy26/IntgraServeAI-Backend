from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, Cookie
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
    MessageResponse
)
from utils.exceptions import (
    AuthenticationException,
    ValidationException,
    InvalidTokenException
)
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Login successful - Access token in body, Refresh token in cookie",
            "content": {
                "application/json": {
                    "example": {
                        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                    }
                }
            }
        },
        401: {
            "description": "Invalid credentials"
        }
    },
    summary="User Login",
    description="Authenticate user. Returns access token in response body and sets refresh token in httpOnly cookie."
)
async def login(
    response: Response,
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Login endpoint
    
    - **email**: User's registered email address
    - **password**: User's password
    
    Returns access token in body and sets refresh token in secure httpOnly cookie.
    """
    try:
        auth_service = AuthService(db)
        access_token, refresh_token = await auth_service.login(credentials)
        
        # Set refresh token in httpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,  # لا يمكن الوصول له من JavaScript
            secure=not settings.DEBUG,  # HTTPS only في production
            samesite="lax",  # حماية من CSRF
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # 7 days
            path="/api/v1/auth"  # فقط لـ auth endpoints
        )
        
        # Return access token in body
        return {"token": access_token}
    
    except AuthenticationException as e:
        raise e
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "An error occurred during login"}
        )


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Forgot Password",
    description="Send password reset link to user's email address."
)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Forgot password endpoint"""
    try:
        auth_service = AuthService(db)
        result = await auth_service.forgot_password(request)
        return result
    
    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}", exc_info=True)
        # Always return success to prevent email enumeration
        return {
            "message": "Password reset Link have been sent to your email."
        }


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Invalid or expired token"
        }
    },
    summary="Reset Password",
    description="Reset user password using token from email."
)
async def reset_password(
    token: str = Query(..., description="Password reset token from email"),
    request: ResetPasswordRequest = ...,
    db: AsyncSession = Depends(get_db)
):
    """Reset password endpoint"""
    try:
        auth_service = AuthService(db)
        result = await auth_service.reset_password(token, request)
        return result
    
    except InvalidTokenException as e:
        raise e
    except ValidationException as e:
        raise e
    except Exception as e:
        logger.error(f"Reset password error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "An error occurred during password reset"}
        )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Token refreshed successfully"
        },
        401: {
            "description": "Invalid refresh token"
        }
    },
    summary="Refresh Access Token",
    description="Get a new access token using refresh token from cookie."
)
async def refresh_token(
    refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh token endpoint
    
    Reads refresh token from httpOnly cookie and returns new access token.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid"}
        )
    
    try:
        auth_service = AuthService(db)
        access_token = await auth_service.refresh_access_token(refresh_token)
        return {"token": access_token}
    
    except AuthenticationException as e:
        raise e
    except Exception as e:
        logger.error(f"Refresh token error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid"}
        )


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="User Logout",
    description="Logout user and clear refresh token cookie."
)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Logout endpoint
    
    Clears the refresh token cookie.
    """
    # Clear refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth"
    )
    
    return {"message": "Logged out successfully"}