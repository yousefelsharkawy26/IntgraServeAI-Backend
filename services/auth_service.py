from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Dict, Tuple
from datetime import datetime
from models.user import User
from utils.schemas.auth_schemas import (
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest
)
from utils.security import verify_password, get_password_hash, validate_password_strength
from utils.token_helper import TokenHelper
from utils.email_service import email_service
from utils.exceptions import (
    AuthenticationException,
    NotFoundException,
    BadRequestException,
    ValidationException,
    InvalidTokenException
)
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


class AuthService:
    """Service for authentication operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def login(self, credentials: LoginRequest) -> Tuple[str, str]:
        """
        Authenticate user and return tokens
        
        Args:
            credentials: Login credentials (email and password)
            
        Returns:
            Tuple of (access_token, refresh_token)
            
        Raises:
            AuthenticationException: If credentials are invalid
        """
        # Get user by email
        result = await self.db.execute(
            select(User).where(User.email == credentials.email)
        )
        user = result.scalar_one_or_none()
        
        # Check if user exists
        if not user:
            logger.warning(f"Login attempt with non-existent email: {credentials.email}")
            raise AuthenticationException("Invalid email or password")
        
        # Check if user is active
        if not user.is_active:
            logger.warning(f"Login attempt for inactive user: {credentials.email}")
            raise AuthenticationException("Account is inactive. Please contact support.")
        
        # Verify password
        if not verify_password(credentials.password, user.password_hash):
            logger.warning(f"Failed login attempt for user: {credentials.email}")
            raise AuthenticationException("Invalid email or password")
        
        # Update last login
        user.last_login = datetime.utcnow()
        await self.db.commit()
        
        # Create token data
        token_data = {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name
        }
        
        # Create access and refresh tokens
        access_token = TokenHelper.create_access_token(token_data)
        refresh_token = TokenHelper.create_refresh_token(token_data)
        
        logger.info(f"User logged in successfully: {user.email}")
        
        # Return both tokens (refresh will be set in cookie by the endpoint)
        return access_token, refresh_token
    
    async def forgot_password(self, request: ForgotPasswordRequest) -> Dict[str, str]:
        """Send password reset email"""
        # Get user by email
        result = await self.db.execute(
            select(User).where(User.email == request.email)
        )
        user = result.scalar_one_or_none()
        
        # Always return success message (prevent email enumeration)
        success_message = {
            "message": "Password reset Link have been sent to your email."
        }
        
        if not user:
            logger.warning(f"Password reset requested for non-existent email: {request.email}")
            return success_message
        
        if not user.is_active:
            logger.warning(f"Password reset requested for inactive user: {request.email}")
            return success_message
        
        # Create reset token
        reset_token = TokenHelper.create_reset_password_token(
            user_id=str(user.id),
            email=user.email
        )
        
        # Send reset email
        email_sent = email_service.send_password_reset_email(
            to_email=user.email,
            reset_token=reset_token,
            user_name=user.full_name
        )
        
        if email_sent:
            logger.info(f"Password reset email sent to: {user.email}")
        else:
            logger.error(f"Failed to send password reset email to: {user.email}")
        
        return success_message
    
    async def reset_password(
        self,
        token: str,
        request: ResetPasswordRequest
    ) -> Dict[str, str]:
        """Reset user password using reset token"""
        # Verify reset token
        try:
            payload = TokenHelper.verify_reset_password_token(token)
            user_id = payload.get("user_id")
            email = payload.get("email")
            
            if not user_id or not email:
                raise InvalidTokenException("Invalid Link.")
        
        except InvalidTokenException as e:
            logger.warning(f"Invalid reset token used")
            raise e
        
        # Validate password strength
        is_valid, error_message = validate_password_strength(request.new_password)
        if not is_valid:
            raise ValidationException({
                "new_password": error_message
            })
        
        # Get user
        result = await self.db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User not found for password reset: {user_id}")
            raise InvalidTokenException("Invalid Link.")
        
        # Verify email matches
        if user.email != email:
            logger.warning(f"Email mismatch in reset token for user: {user_id}")
            raise InvalidTokenException("Invalid Link.")
        
        # Update password
        user.password_hash = get_password_hash(request.new_password)
        await self.db.commit()
        
        logger.info(f"Password reset successfully for user: {user.email}")
        
        # Send confirmation email
        email_service.send_password_reset_confirmation_email(
            to_email=user.email,
            user_name=user.full_name
        )
        
        return {
            "message": "Password has been reset successfully."
        }
    
    async def refresh_access_token(self, refresh_token: str) -> str:
        """
        Refresh access token using refresh token from cookie
        
        Args:
            refresh_token: Refresh token from cookie
            
        Returns:
            New access token
            
        Raises:
            UnauthorizedException: If refresh token is invalid
        """
        # Verify refresh token
        payload = TokenHelper.verify_token(refresh_token, token_type="refresh")
        
        user_id = payload.get("user_id")
        if not user_id:
            raise AuthenticationException("Invalid refresh token")
        
        # Get user
        result = await self.db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise AuthenticationException("User not found or inactive")
        
        # Create new access token
        token_data = {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name
        }
        
        access_token = TokenHelper.create_access_token(token_data)
        
        logger.info(f"Access token refreshed for user: {user.email}")
        
        return access_token
    
    async def logout(self, user_id: str) -> Dict[str, str]:
        """Logout user (for audit log purposes)"""
        result = await self.db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()
        
        if user:
            logger.info(f"User logged out: {user.email}")
        
        return {
            "message": "Logged out successfully"
        }