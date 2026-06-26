# utils/token_helper.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from core.config import settings
from utils.exceptions import InvalidTokenException, UnauthorizedException
from uuid import UUID


class TokenHelper:
    """Helper class for JWT token operations"""
    
    @staticmethod
    def create_access_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a new access token"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access"
        })
        
        # Convert UUID to string if present
        if "user_id" in to_encode and isinstance(to_encode["user_id"], UUID):
            to_encode["user_id"] = str(to_encode["user_id"])
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )
        
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a new refresh token"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            )
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "refresh"
        })
        
        # Convert UUID to string if present
        if "user_id" in to_encode and isinstance(to_encode["user_id"], UUID):
            to_encode["user_id"] = str(to_encode["user_id"])
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )
        
        return encoded_jwt
    
    @staticmethod
    def create_reset_password_token(user_id: str, email: str) -> str:
        """Create a password reset token"""
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.RESET_TOKEN_EXPIRE_MINUTES
        )
        
        to_encode = {
            "user_id": str(user_id),
            "email": email,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "reset_password"
        }
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )
        
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> Dict[str, Any]:
        """
        Verify and decode a JWT token
        
        Args:
            token: JWT token string
            token_type: Expected token type ("access", "refresh", "reset_password")
            
        Returns:
            Decoded token payload
            
        Raises:
            InvalidTokenException: If token is invalid or expired
        """
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            
            # Verify token type
            if payload.get("type") != token_type:
                raise InvalidTokenException("Invalid token type")
            
            return payload
            
        except jwt.ExpiredSignatureError:
            if token_type == "reset_password":
                raise InvalidTokenException("Invalid Link.")
            raise UnauthorizedException("Token has expired")
            
        except jwt.InvalidTokenError as e:
            if token_type == "reset_password":
                raise InvalidTokenException("Invalid Link.")
            raise UnauthorizedException(f"Invalid token: {str(e)}")
    
    @staticmethod
    def verify_reset_password_token(token: str) -> Dict[str, Any]:
        """Verify password reset token"""
        return TokenHelper.verify_token(token, token_type="reset_password")
    
    @staticmethod
    def decode_token_without_verification(token: str) -> Dict[str, Any]:
        """Decode token without verification (for debugging)"""
        try:
            return jwt.decode(
                token,
                options={"verify_signature": False},
                algorithms=[settings.ALGORITHM]
            )
        except Exception:
            return {}
    
    @staticmethod
    def get_user_id_from_token(token: str) -> str:
        """Extract user_id from access token"""
        payload = TokenHelper.verify_token(token, "access")
        user_id = payload.get("user_id")
        
        if not user_id:
            raise UnauthorizedException("Invalid token: user_id not found")
        
        return user_id