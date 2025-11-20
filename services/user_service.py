# services/user_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta, timezone  # ✅ Add timezone

from models.user import User, Role
from models.audit import AuditLog
from utils.schemas.user_schemas import (
    UserCreate,
    UserUpdateBasicInfo,
    UserUpdatePassword,
    UserUpdateRoles,
    UserResponse,
    AuditLogResponse,
    MyProfileUpdate,
    MyPasswordChange,
    UserActivity
)
from utils.security import get_password_hash, verify_password
from utils.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException,
    ValidationException,
    AuthenticationException
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
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
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        
        changed_values = {}
        
        if update_data.email and update_data.email != user.email:
            result = await self.db.execute(
                select(User).where(User.email == update_data.email)
            )
            existing = result.scalar_one_or_none()
            if existing:
                raise ConflictException(f"Email '{update_data.email}' already exists")
            
            changed_values["email"] = {"old": user.email, "new": update_data.email}
            user.email = update_data.email
            user.email_confirmed = False
        
        if update_data.full_name and update_data.full_name != user.full_name:
            changed_values["full_name"] = {"old": user.full_name, "new": update_data.full_name}
            user.full_name = update_data.full_name
        
        if not changed_values:
            return user
        
        user.updated_at = datetime.now(timezone.utc)
        
        await self._create_audit_log(
            user_id=updated_by_user_id,
            action_type="UPDATE",
            target_table="users",
            target_record_id=user.id,
            changed_values=changed_values
        )
        
        await self.db.commit()
        
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
        user.updated_at = datetime.now(timezone.utc)
        
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
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise NotFoundException("User not found")
        
        old_role_ids = [str(r.id) for r in user.roles]
        
        new_roles = []
        for role_id in update_data.roles_id:
            result = await self.db.execute(
                select(Role).where(Role.id == role_id)
            )
            role = result.scalar_one_or_none()
            if not role:
                raise NotFoundException(f"Role with ID '{role_id}' not found")
            new_roles.append(role)
        
        user.roles = new_roles
        user.updated_at = datetime.now(timezone.utc)
        
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
        user.updated_at = datetime.now(timezone.utc)
        
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
        user.updated_at = datetime.now(timezone.utc)
        
        await self._create_audit_log(
            user_id=activated_by_user_id,
            action_type="UPDATE",
            target_table="users",
            target_record_id=user.id,
            changed_values={"is_active": {"old": False, "new": True}}
        )
        
        await self.db.commit()
        
        logger.info(f"User activated: {user.email}")
    
    # ✅ Update own profile
    async def update_my_profile(
        self,
        user_id: UUID,
        update_data: MyProfileUpdate
    ) -> User:
        """Update current user's own profile"""
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        
        changed_values = {}
        
        if update_data.email and update_data.email != user.email:
            result = await self.db.execute(
                select(User).where(User.email == update_data.email)
            )
            existing = result.scalar_one_or_none()
            if existing:
                raise ConflictException(f"Email '{update_data.email}' already exists")
            
            changed_values["email"] = {"old": user.email, "new": update_data.email}
            user.email = update_data.email
            user.email_confirmed = False
        
        if update_data.full_name and update_data.full_name != user.full_name:
            changed_values["full_name"] = {"old": user.full_name, "new": update_data.full_name}
            user.full_name = update_data.full_name
        
        if not changed_values:
            raise BadRequestException("No changes provided")
        
        user.updated_at = datetime.now(timezone.utc)
        
        await self._create_audit_log(
            user_id=user_id,
            action_type="UPDATE",
            target_table="users",
            target_record_id=user.id,
            changed_values=changed_values
        )
        
        await self.db.commit()
        
        await self.db.refresh(user)
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user.id)
        )
        user = result.scalar_one()
        
        logger.info(f"User updated own profile: {user.email}")
        
        return user
    
    # ✅ Change own password
    async def change_my_password(
        self,
        user_id: UUID,
        password_data: MyPasswordChange
    ) -> None:
        """Change current user's password"""
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        
        # Verify current password
        if not verify_password(password_data.current_password, user.password_hash):
            raise AuthenticationException("Current password is incorrect")
        
        # Update password
        user.password_hash = get_password_hash(password_data.new_password)
        user.updated_at = datetime.now(timezone.utc)
        
        await self._create_audit_log(
            user_id=user_id,
            action_type="UPDATE",
            target_table="users",
            target_record_id=user.id,
            changed_values={"password": "changed by user"}
        )
        
        await self.db.commit()
        
        logger.info(f"User changed own password: {user.email}")
    
    # ✅ Bulk deactivate users
    async def bulk_deactivate_users(
        self,
        user_ids: List[UUID],
        deactivated_by_user_id: UUID
    ) -> dict:
        """Deactivate multiple users"""
        total_requested = len(user_ids)
        successful = 0
        failed = 0
        errors = []
        
        for user_id in user_ids:
            try:
                user = await self.get_user_by_id(user_id)
                
                if not user:
                    errors.append({
                        "user_id": str(user_id),
                        "error": "User not found"
                    })
                    failed += 1
                    continue
                
                if not user.is_active:
                    errors.append({
                        "user_id": str(user_id),
                        "error": "User is already deactivated"
                    })
                    failed += 1
                    continue
                
                user.is_active = False
                user.updated_at = datetime.now(timezone.utc)
                
                await self._create_audit_log(
                    user_id=deactivated_by_user_id,
                    action_type="BULK_DEACTIVATE",
                    target_table="users",
                    target_record_id=user.id,
                    changed_values={"is_active": {"old": True, "new": False}}
                )
                
                successful += 1
                logger.info(f"User deactivated in bulk: {user.email}")
                
            except Exception as e:
                errors.append({
                    "user_id": str(user_id),
                    "error": str(e)
                })
                failed += 1
        
        await self.db.commit()
        
        return {
            "message": "Bulk deactivation completed",
            "total_requested": total_requested,
            "successful": successful,
            "failed": failed,
            "errors": errors if errors else None
        }
    
    # ✅ Bulk activate users
    async def bulk_activate_users(
        self,
        user_ids: List[UUID],
        activated_by_user_id: UUID
    ) -> dict:
        """Activate multiple users"""
        total_requested = len(user_ids)
        successful = 0
        failed = 0
        errors = []
        
        for user_id in user_ids:
            try:
                user = await self.get_user_by_id(user_id)
                
                if not user:
                    errors.append({
                        "user_id": str(user_id),
                        "error": "User not found"
                    })
                    failed += 1
                    continue
                
                if user.is_active:
                    errors.append({
                        "user_id": str(user_id),
                        "error": "User is already active"
                    })
                    failed += 1
                    continue
                
                user.is_active = True
                user.updated_at = datetime.now(timezone.utc)
                
                await self._create_audit_log(
                    user_id=activated_by_user_id,
                    action_type="BULK_ACTIVATE",
                    target_table="users",
                    target_record_id=user.id,
                    changed_values={"is_active": {"old": False, "new": True}}
                )
                
                successful += 1
                logger.info(f"User activated in bulk: {user.email}")
                
            except Exception as e:
                errors.append({
                    "user_id": str(user_id),
                    "error": str(e)
                })
                failed += 1
        
        await self.db.commit()
        
        return {
            "message": "Bulk activation completed",
            "total_requested": total_requested,
            "successful": successful,
            "failed": failed,
            "errors": errors if errors else None
        }
    
    # ✅ Get user statistics
    async def get_user_statistics(self) -> dict:
        """Get user statistics"""
        # Total users
        total_result = await self.db.execute(select(func.count(User.id)))
        total_users = total_result.scalar()
        
        # Active users
        active_result = await self.db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        active_users = active_result.scalar()
        
        # Inactive users
        inactive_users = total_users - active_users
        
        # Confirmed emails
        confirmed_result = await self.db.execute(
            select(func.count(User.id)).where(User.email_confirmed == True)
        )
        confirmed_emails = confirmed_result.scalar()
        
        # Unconfirmed emails
        unconfirmed_emails = total_users - confirmed_emails
        
        # Users by role
        users_by_role = {}
        roles_result = await self.db.execute(select(Role))
        roles = roles_result.scalars().all()
        
        for role in roles:
            count_result = await self.db.execute(
                select(func.count(User.id))
                .join(User.roles)
                .where(Role.id == role.id)
            )
            users_by_role[role.name] = count_result.scalar()
        
        # Recent registrations (last 7 days)
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_reg_result = await self.db.execute(
            select(func.count(User.id)).where(User.created_at >= seven_days_ago)
        )
        recent_registrations = recent_reg_result.scalar()
        
        # Recent logins (last 24 hours)
        one_day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_login_result = await self.db.execute(
            select(func.count(User.id)).where(User.last_login >= one_day_ago)
        )
        recent_logins = recent_login_result.scalar()
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": inactive_users,
            "confirmed_emails": confirmed_emails,
            "unconfirmed_emails": unconfirmed_emails,
            "users_by_role": users_by_role,
            "recent_registrations": recent_registrations,
            "recent_logins": recent_logins
        }
    
    # ✅ Get user activity
    async def get_user_activity(
        self,
        page: int = 1,
        limit: int = 10,
        sort_by: str = "last_login"  # last_login or created_at
    ) -> Tuple[List[UserActivity], int]:
        """Get user activity (last login information)"""
        # Build query
        query = select(User)
        
        # Get total count
        count_result = await self.db.execute(select(func.count(User.id)))
        total = count_result.scalar()
        
        # Apply sorting
        if sort_by == "last_login":
            query = query.order_by(User.last_login.desc().nulls_last())
        else:
            query = query.order_by(User.created_at.desc())
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        users = result.scalars().all()
        
        # Convert to UserActivity
        user_activities = []
        now = datetime.now(timezone.utc)
        
        for user in users:
            days_since_login = None
            if user.last_login:
                days_since_login = (now - user.last_login).days
            
            activity = UserActivity(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                last_login=user.last_login,
                is_active=user.is_active,
                days_since_login=days_since_login
            )
            user_activities.append(activity)
        
        return user_activities, total
    
    async def list_users(
        self,
        current_user_id: UUID,
        page: int = 1,
        limit: int = 10,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        email_confirmed: Optional[bool] = None,
        search: Optional[str] = None  # ✅ Added search parameter
    ) -> Tuple[List[UserResponse], int]:
        """List users with filters (excluding current user)"""
        # Build query with eager loading
        query = select(User).options(selectinload(User.roles))
        
        # Exclude current user
        query = query.where(User.id != current_user_id)
        
        # ✅ Apply search filter
        if search:
            query = query.where(
                or_(
                    User.email.ilike(f"%{search}%"),
                    User.full_name.ilike(f"%{search}%")
                )
            )
        
        # Apply filters
        if role:
            query = query.join(User.roles).where(Role.name == role)
        
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        
        if email_confirmed is not None:
            query = query.where(User.email_confirmed == email_confirmed)
        
        # Get total count
        count_query = select(func.count()).select_from(User).where(User.id != current_user_id)
        
        if search:
            count_query = count_query.where(
                or_(
                    User.email.ilike(f"%{search}%"),
                    User.full_name.ilike(f"%{search}%")
                )
            )
        
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
        users = result.scalars().unique().all()
        
        # Convert to UserResponse with role names only
        user_responses = []
        for user in users:
            user_dict = {
                "id": user.id,
                "email": user.email,
                "email_confirmed": user.email_confirmed,
                "full_name": user.full_name,
                "roles": [role.name for role in user.roles],
                "is_active": user.is_active,
                "last_login": user.last_login,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }
            user_responses.append(UserResponse(**user_dict))
        
        return user_responses, total
    
    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID with roles loaded"""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_with_roles(self, user_id: UUID) -> UserResponse:
        """Get user by ID with roles (for API response)"""
        user = await self.get_user_by_id(user_id)
        
        if not user:
            raise NotFoundException("User not found")
        
        user_dict = {
            "id": user.id,
            "email": user.email,
            "email_confirmed": user.email_confirmed,
            "full_name": user.full_name,
            "roles": [role.name for role in user.roles],
            "is_active": user.is_active,
            "last_login": user.last_login,
            "created_at": user.created_at,
            "updated_at": user.updated_at
        }
        
        return UserResponse(**user_dict)
    
    async def get_user_logs(
        self,
        user_id: UUID,
        page: int = 1,
        limit: int = 10
    ) -> Tuple[List[AuditLogResponse], int]:
        """Get audit logs for actions performed BY a user"""
        # Check if user exists
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        
        # Build query
        query = select(AuditLog).options(
            selectinload(AuditLog.user)
        ).where(
            AuditLog.user_id == user_id
        )
        
        # Get total count
        count_query = select(func.count()).select_from(AuditLog).where(
            AuditLog.user_id == user_id
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(AuditLog.created_at.desc())
        
        # Execute query
        result = await self.db.execute(query)
        logs = result.scalars().all()
        
        # Convert to AuditLogResponse
        log_responses = []
        for log in logs:
            log_dict = {
                "id": log.id,
                "user_id": log.user_id,
                "user_name": log.user.full_name if log.user else None,
                "action_type": log.action_type,
                "target_table": log.target_table,
                "target_record_id": log.target_record_id,
                "changed_values": log.changed_values,
                "created_at": log.created_at
            }
            log_responses.append(AuditLogResponse(**log_dict))
        
        return log_responses, total
    
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
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(audit_log)