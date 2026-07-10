# utils/dependencies.py
"""
Authentication and Authorization Dependencies
"""
from fastapi import Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID

from core.database import get_db
from models.chat import ChatConversation
from models.user import User
from utils.token_helper import TokenHelper
from utils.exceptions import UnauthorizedException


security_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
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
        # Check blacklist before verifying
        if await TokenHelper.is_token_blacklisted(credentials.credentials, db):
            raise UnauthorizedException("Token has been revoked")
        
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
    

class CustomerSession:
    """Represents an authenticated customer session (non-JWT)."""
    def __init__(self, session_id: str, customer_email: str, conversation_id: Optional[UUID] = None):
        self.session_id = session_id
        self.customer_email = customer_email
        self.conversation_id = conversation_id


async def verify_customer_session(
    session_id: str = Query(..., description="Customer session ID"),
    customer_email: str = Query(..., description="Customer email address"),
    db: AsyncSession = Depends(get_db),
) -> CustomerSession:
    """
    Verify that a session_id + customer_email pair is valid.
    Looks up the conversation to ensure the session exists and belongs to the customer.
    """
    if not session_id or not customer_email:
        raise UnauthorizedException("Session ID and customer email are required")

    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.session_id == session_id,
            ChatConversation.customer_email == customer_email
        )
    )
    conv = result.scalar_one_or_none()

    if not conv:
        raise UnauthorizedException("Invalid session or email")

    return CustomerSession(
        session_id=session_id,
        customer_email=customer_email,
        conversation_id=conv.id
    )


async def verify_customer_session_for_conversation(
    conversation_id: UUID,
    session_id: str = Query(..., description="Customer session ID"),
    customer_email: str = Query(..., description="Customer email address"),
    db: AsyncSession = Depends(get_db),
) -> CustomerSession:
    """
    Verify that the customer owns the specific conversation.
    Used for endpoints that operate on a specific conversation resource.
    """
    if not session_id or not customer_email:
        raise UnauthorizedException("Session ID and customer email are required")

    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.session_id == session_id,
            ChatConversation.customer_email == customer_email
        )
    )
    conv = result.scalar_one_or_none()

    if not conv:
        raise UnauthorizedException("Invalid session, email, or conversation access denied")

    return CustomerSession(
        session_id=session_id,
        customer_email=customer_email,
        conversation_id=conv.id
    )

async def get_current_active_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Try JWT auth from Authorization: Bearer <token> header.
    Returns None if no token provided or invalid.

    FIX: Uses selectinload(User.roles) to eagerly load roles so that
    synchronous access to user.roles later does not trigger lazy loading.
    """
    if not credentials:
        return None

    token = credentials.credentials
    if not token:
        return None

    try:
        # Check blacklist before verifying
        if await TokenHelper.is_token_blacklisted(token, db):
            return None

        payload = TokenHelper.verify_token(token)
        user_id = payload.get("user_id")
        if not user_id:
            return None

        # FIX: Eagerly load roles to avoid MissingGreenlet
        result = await db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return user
    except Exception:
        pass
    return None



async def verify_customer_session_optional(
    session_id: Optional[str] = Query(None, description="Customer session ID"),
    customer_email: Optional[str] = Query(None, description="Customer email address"),
    db: AsyncSession = Depends(get_db),
) -> Optional[CustomerSession]:
    """Try to authenticate via session, return None if no session provided or invalid."""
    if not session_id or not customer_email:
        return None
    try:
        result = await db.execute(
            select(ChatConversation).where(
                ChatConversation.session_id == session_id,
                ChatConversation.customer_email == customer_email
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            return CustomerSession(
                session_id=session_id,
                customer_email=customer_email,
                conversation_id=conv.id
            )
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Unified Chat Access Control
# ---------------------------------------------------------------------------

class ChatAccess:
    """
    Unified access context for chat endpoints.

    Supports dual authentication:
      - Staff users via JWT (admin, agent roles)
      - Customers via session_id + customer_email
    """
    def __init__(
        self,
        user: Optional[User] = None,
        customer_session: Optional[CustomerSession] = None
    ):
        self.user = user
        self.customer_session = customer_session
        self.is_staff = user is not None
        self.is_admin = user is not None and any(r.name == "Admin" for r in user.roles)
        self.is_agent = user is not None and any(r.name in ("Support User", "Tech User") for r in user.roles)

    def can_access_conversation(self, conv: ChatConversation) -> bool:
        """Check if the accessor can view a specific conversation."""
        if self.is_admin or self.is_agent:
            return True
        if self.customer_session:
            return (
                conv.session_id == self.customer_session.session_id and
                conv.customer_email == self.customer_session.customer_email
            )
        return False

    def can_modify_conversation(self, conv: ChatConversation) -> bool:
        """Check if the accessor can modify (PATCH/POST messages to) a conversation."""
        if self.is_admin:
            return True
        if self.is_agent:
            # Only the assigned agent can modify a specific conversation
            if self.user and conv.assigned_agent_id is not None:
                return str(conv.assigned_agent_id) == str(self.user.id)
            return False
        if self.customer_session:
            return (
                conv.session_id == self.customer_session.session_id and
                conv.customer_email == self.customer_session.customer_email and
                conv.is_active  # Can't modify ended conversations
            )
        return False

    def can_delete_conversation(self) -> bool:
        """Only admins can delete conversations."""
        return self.is_admin


async def get_chat_access(
    user: Optional[User] = Depends(get_current_active_user_optional),
    customer_session: Optional[CustomerSession] = Depends(verify_customer_session_optional),
) -> ChatAccess:
    """
    Dual authentication dependency for chat endpoints.

    Accepts EITHER:
      - JWT bearer token via Authorization header (for staff users)
      - session_id + customer_email query params (for customers)

    Raises 401 if neither authentication method succeeds.
    """
    if user is None and customer_session is None:
        raise UnauthorizedException(
            "Authentication required. Provide either a valid JWT token via Authorization header "
            "or session_id + customer_email query params."
        )

    return ChatAccess(user=user, customer_session=customer_session)


# Pre-defined role checkers
require_admin = RoleChecker(["Admin"])
require_admin_or_tech = RoleChecker(["Admin", "Tech User"])
require_any_role = RoleChecker(["Admin", "Tech User", "Support User"])