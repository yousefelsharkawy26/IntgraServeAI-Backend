from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime

from models.user import User, Role
from models.audit import AuditLog
from utils.schemas.user_schemas import (
    UserCreate,
    UserUpdateBasicInfo,
    UserUpdatePassword,
    UserUpdateRoles
)
from utils.security import get_password_hash
from utils.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException,
    ValidationException
)
import logging

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_user(self, user_data: UserCreate, created_by_user_id: UUID) -> User:
        """Create a new user"""
        # Check if email already exists
        result = await self.db.execute(
            select(User).where(User.email == user_data.email)
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            raise ConflictException(f"Email '{user_data.email}' already exists")
        
        # Get roles
        roles = []
        for role_id in user_data.roles_id:
            result = await self.db.execute(
                select(Role).where(Role.id == role_id)
            )
            role = result.scalar_one_or_none()
            if not role:
                raise NotFoundException(f"Role with ID '{role_id}' not found")
            roles.append(role)
        
        # Create user
        user = User(
            email=user_data.email,
            password_hash=get_password_hash(user_data.password),
            full_name=user_data.full_name,
            is_active=True,
            email_confirmed=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Assign roles
        user.roles = roles
        
        self.db.add(user)
        await self.db.flush()
        
        # Create audit log
        await self._create_audit_log(
            user_id=created_by_user_id,
            action_type="CREATE",
            target_table="users",
            target_record_id=user.id,
            changed_values={
                "email": user_data.email,
                "full_name": user_data.full_name,
                "roles": [str(r.id) for r in roles]
            }
        )
        
        await self.db.commit()
        
        # ✅ Reload with relationships
        await self.db.refresh(user)
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user.id)
        )
        user = result.scalar_one()
        
        logger.info(f"User created: {user.email} by user {created_by_user_id}")
        
        return user
    
    async def update_basic_info(
        self,
        user_id: UUID,
        update_data: UserUpdateBasicInfo,
        updated_by_user_id: UUID
    ) -> User:
        """Update user basic information"""
        # Get user
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        
        changed_values = {}
        
        # Update email if provided
        if update_data.email and update_data.email != user.email:
            # Check if new email exists
            result = await self.db.execute(
                select(User).where(User.email == update_data.email)
            )
            existing = result.scalar_one_or_none()
            if existing:
                raise ConflictException(f"Email '{update_data.email}' already exists")
            
            changed_values["email"] = {"old": user.email, "new": update_data.email}
            user.email = update_data.email
            user.email_confirmed = False
        
        # Update full name if provided
        if update_data.full_name and update_data.full_name != user.full_name:
            changed_values["full_name"] = {"old": user.full_name, "new": update_data.full_name}
            user.full_name = update_data.full_name
        
        if not changed_values:
            return user
        
        user.updated_at = datetime.utcnow()
        
        # Create audit log
        await self._create_audit_log(
            user_id=updated_by_user_id,
            action_type="UPDATE",
            target_table="users",
            target_record_id=user.id,
            changed_values=changed_values
        )
        
        await self.db.commit()
        
        # ✅ Reload with relationships
        await self.db.refresh(user)
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user.id)
        )
        user = result.scalar_one()
        
        logger.info(f"User updated: {user.email} by user {updated_by_user_id}")
        
        return user
    
    async def update_password(
        self,
        user_id: UUID,
        update_data: UserUpdatePassword,
        updated_by_user_id: UUID
    ) -> None:
        """Update user password"""
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        
        user.password_hash = get_password_hash(update_data.new_password)
        user.updated_at = datetime.utcnow()
        
        # Create audit log
        await self._create_audit_log(
            user_id=updated_by_user_id,
            action_type="UPDATE",
            target_table="users",
            target_record_id=user.id,
            changed_values={"password": "updated"}
        )
        
        await self.db.commit()
        
        logger.info(f"Password updated for user: {user.email}")
    
    async def update_roles(
        self,
        user_id: UUID,
        update_data: UserUpdateRoles,
        updated_by_user_id: UUID
    ) -> User:
        """Update user roles"""
        # ✅ Get user with roles loaded
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise NotFoundException("User not found")
        
        # Get old roles
        old_role_ids = [str(r.id) for r in user.roles]
        
        # Get new roles
        new_roles = []
        for role_id in update_data.roles_id:
            result = await self.db.execute(
                select(Role).where(Role.id == role_id)
            )
            role = result.scalar_one_or_none()
            if not role:
                raise NotFoundException(f"Role with ID '{role_id}' not found")
            new_roles.append(role)
        
        # Update roles
        user.roles = new_roles
        user.updated_at = datetime.utcnow()
        
        # Create audit log
        await self._create_audit_log(
            user_id=updated_by_user_id,
            action_type="UPDATE",
            target_table="users",
            target_record_id=user.id,
            changed_values={
                "roles": {
                    "old": old_role_ids,
                    "new": [str(r.id) for r in new_roles]
                }
            }
        )
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info(f"Roles updated for user: {user.email}")
        
        return user
    
    async def deactivate_user(self, user_id: UUID, deactivated_by_user_id: UUID) -> None:
        """Deactivate user"""
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        
        if not user.is_active:
            raise BadRequestException("User is already deactivated")
        
        user.is_active = False
        user.updated_at = datetime.utcnow()
        
        await self._create_audit_log(
            user_id=deactivated_by_user_id,
            action_type="UPDATE",
            target_table="users",
            target_record_id=user.id,
            changed_values={"is_active": {"old": True, "new": False}}
        )
        
        await self.db.commit()
        
        logger.info(f"User deactivated: {user.email}")
    
    async def activate_user(self, user_id: UUID, activated_by_user_id: UUID) -> None:
        """Activate user"""
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        
        if user.is_active:
            raise BadRequestException("User is already active")
        
        user.is_active = True
        user.updated_at = datetime.utcnow()
        
        await self._create_audit_log(
            user_id=activated_by_user_id,
            action_type="UPDATE",
            target_table="users",
            target_record_id=user.id,
            changed_values={"is_active": {"old": False, "new": True}}
        )
        
        await self.db.commit()
        
        logger.info(f"User activated: {user.email}")
    
    async def list_users(
        self,
        page: int = 1,
        limit: int = 10,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        email_confirmed: Optional[bool] = None
    ) -> Tuple[List[User], int]:
        """List users with filters"""
        # Build query with eager loading
        query = select(User).options(selectinload(User.roles))  # ✅
        
        # Apply filters
        if role:
            query = query.join(User.roles).where(Role.name == role)
        
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        
        if email_confirmed is not None:
            query = query.where(User.email_confirmed == email_confirmed)
        
        # Get total count
        count_query = select(func.count()).select_from(User)
        
        if role:
            count_query = count_query.join(User.roles).where(Role.name == role)
        if is_active is not None:
            count_query = count_query.where(User.is_active == is_active)
        if email_confirmed is not None:
            count_query = count_query.where(User.email_confirmed == email_confirmed)
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(User.created_at.desc())
        
        # Execute query
        result = await self.db.execute(query)
        users = result.scalars().unique().all()  # ✅ unique() for joined queries
        
        return users, total
    
    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID with roles loaded"""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))  # ✅
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_logs(
        self,
        user_id: UUID,
        page: int = 1,
        limit: int = 10
    ) -> Tuple[List[AuditLog], int]:
        """Get audit logs for a user"""
        # Check if user exists
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        
        # Build query
        query = select(AuditLog).where(
            or_(
                AuditLog.user_id == user_id,
                AuditLog.target_record_id == user_id
            )
        )
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(AuditLog.created_at.desc())
        
        # Execute query
        result = await self.db.execute(query)
        logs = result.scalars().all()
        
        return logs, total
    
    async def _create_audit_log(
        self,
        user_id: UUID,
        action_type: str,
        target_table: str,
        target_record_id: UUID,
        changed_values: dict
    ) -> None:
        """Create audit log entry"""
        audit_log = AuditLog(
            user_id=user_id,
            action_type=action_type,
            target_table=target_table,
            target_record_id=target_record_id,
            changed_values=changed_values,
            created_at=datetime.utcnow()
        )
        self.db.add(audit_log)