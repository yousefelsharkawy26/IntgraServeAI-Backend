# utils/dependencies.py
"""
Authentication and Authorization Dependencies
"""
from fastapi import Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from core.database import get_db
from models.user import User, Role
from utils.token_helper import TokenHelper
from utils.exceptions import UnauthorizedException

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token
    
    Args:
        credentials: Bearer token from Authorization header
        db: Database session
        
    Returns:
        User object with loaded roles
        
    Raises:
        UnauthorizedException: If token is invalid or user not found
    """
    try:
        # Verify access token
        payload = TokenHelper.verify_token(credentials.credentials, token_type="access")
        user_id = payload.get("user_id")
        
        if not user_id:
            raise UnauthorizedException("Invalid token")
        
        # Get user from database with roles (eager loading)
        result = await db.execute(
            select(User)
            .options(selectinload(User.roles))  # ✅ Eager load roles
            .where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise UnauthorizedException("User not found")
        
        if not user.is_active:
            raise UnauthorizedException("User account is deactivated")
        
        return user
        
    except UnauthorizedException:
        raise
    except Exception as e:
        raise UnauthorizedException(f"Authentication failed: {str(e)}")


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user
    
    Args:
        current_user: Current user from get_current_user
        
    Returns:
        User object
        
    Raises:
        UnauthorizedException: If user is not active
    """
    if not current_user.is_active:
        raise UnauthorizedException("User account is deactivated")
    
    return current_user


class RoleChecker:
    """
    Dependency to check if user has required role(s)
    """
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles
    
    async def __call__(
        self,
        current_user: User = Depends(get_current_active_user)
    ) -> User:
        """
        Check if user has any of the allowed roles
        
        Args:
            current_user: Current authenticated user (with loaded roles)
            
        Returns:
            User object if authorized
            
        Raises:
            UnauthorizedException: If user doesn't have required role
        """
        # ✅ Roles already loaded by get_current_user
        # Get user role names
        user_role_names = [role.name for role in current_user.roles]
        
        # Check if user has any of the allowed roles
        if not any(role in self.allowed_roles for role in user_role_names):
            raise UnauthorizedException(
                f"Access denied. Required roles: {', '.join(self.allowed_roles)}"
            )
        
        return current_user


# Pre-defined role checkers
require_admin = RoleChecker(["Admin"])
require_admin_or_tech = RoleChecker(["Admin", "Tech User"])
require_any_role = RoleChecker(["Admin", "Tech User", "Support User"])