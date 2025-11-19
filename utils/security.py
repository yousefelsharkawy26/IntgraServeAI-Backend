from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import secrets
import hashlib

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def generate_reset_token() -> str:
    """Generate a secure random token for password reset"""
    # Generate 32 bytes (256 bits) of random data
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a token using SHA-256"""
    return hashlib.sha256(token.encode()).hexdigest()


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password strength
    Returns: (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if len(password) > 128:
        return False, "Password must not exceed 128 characters"
    
    # Add more rules if needed
    # has_uppercase = any(c.isupper() for c in password)
    # has_lowercase = any(c.islower() for c in password)
    # has_digit = any(c.isdigit() for c in password)
    
    return True, None