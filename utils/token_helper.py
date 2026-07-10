# utils/token_helper.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import hashlib
import jwt
from core.config import settings
from utils.exceptions import InvalidTokenException, UnauthorizedException
from uuid import UUID


class TokenHelper:
    """Helper class for JWT token operations"""
    
    @staticmethod
    def _hash_token(token: str) -> str:
        """Compute a stable SHA-256 hash of a raw token string."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
    
    @staticmethod
    async def blacklist_token(token: str, token_type: str, db) -> None:
        """Add a token to the blacklist.  *db* is an AsyncSession."""
        from models.auth import TokenBlacklist
        from sqlalchemy import select, delete
        
        payload = TokenHelper.verify_token(token, token_type)
        exp = payload.get("exp")
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else (
            datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )
        
        token_hash = TokenHelper._hash_token(token)
        
        # Cleanup expired entries (best-effort, fire-and-forget)
        try:
            await db.execute(
                delete(TokenBlacklist).where(TokenBlacklist.expires_at < datetime.now(timezone.utc))
            )
        except Exception:
            pass
        
        entry = TokenBlacklist(
            token_hash=token_hash,
            token_type=token_type,
            expires_at=expires_at,
        )
        db.add(entry)
        await db.commit()
    
    @staticmethod
    async def is_token_blacklisted(token: str, db) -> bool:
        """Return True if the token has been revoked.  *db* is an AsyncSession."""
        from models.auth import TokenBlacklist
        from sqlalchemy import select
        
        token_hash = TokenHelper._hash_token(token)
        result = await db.execute(
            select(TokenBlacklist).where(
                TokenBlacklist.token_hash == token_hash,
                TokenBlacklist.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none() is not None
    
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
    def get_user_id_from_token(token: str) -> str:
        """Extract user_id from access token"""
        payload = TokenHelper.verify_token(token, "access")
        user_id = payload.get("user_id")
        
        if not user_id:
            raise UnauthorizedException("Invalid token: user_id not found")
        
        return user_id