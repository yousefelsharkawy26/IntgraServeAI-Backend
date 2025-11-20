# services/role_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime

from models.user import Role, User
from models.audit import AuditLog
from utils.schemas.role_schemas import RoleUpdate
from utils.schemas.user_schemas import UserResponse
from utils.exceptions import NotFoundException, ConflictException, BadRequestException
import logging
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


class RoleService:
    """Service for role management"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_all_roles(self) -> List[Role]:
        """Get all roles"""
        result = await self.db.execute(
            select(Role).order_by(Role.name)
        )
        return result.scalars().all()
    
    async def get_role_by_id(self, role_id: UUID) -> Optional[Role]:
        """Get role by ID"""
        result = await self.db.execute(
            select(Role).where(Role.id == role_id)
        )
        return result.scalar_one_or_none()
    
    async def get_role_by_name(self, name: str) -> Optional[Role]:
        """Get role by name"""
        result = await self.db.execute(
            select(Role).where(Role.name == name)
        )
        return result.scalar_one_or_none()
    
    async def get_user_roles(self, user_id: UUID) -> dict:
        """Get roles for a specific user"""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise NotFoundException("User not found")
        
        return {
            "roles": [
                {
                    "id": role.id,
                    "name": role.name
                }
                for role in user.roles
            ]
        }
    
    async def update_role(
        self,
        role_id: UUID,
        update_data: RoleUpdate,
        updated_by_user_id: UUID
    ) -> Role:
        """Update role information"""
        role = await self.get_role_by_id(role_id)
        if not role:
            raise NotFoundException("Role not found")
        
        changed_values = {}
        
        if update_data.name and update_data.name != role.name:
            existing_role = await self.get_role_by_name(update_data.name)
            if existing_role:
                raise ConflictException(f"Role with name '{update_data.name}' already exists")
            
            changed_values["name"] = {"old": role.name, "new": update_data.name}
            role.name = update_data.name
        
        if update_data.description is not None and update_data.description != role.description:
            changed_values["description"] = {"old": role.description, "new": update_data.description}
            role.description = update_data.description
        
        if not changed_values:
            raise BadRequestException("No changes provided")
        
        await self._create_audit_log(
            user_id=updated_by_user_id,
            action_type="UPDATE",
            target_table="roles",
            target_record_id=role.id,
            changed_values=changed_values
        )
        
        await self.db.commit()
        await self.db.refresh(role)
        
        logger.info(f"Role updated: {role.name} by user {updated_by_user_id}")
        
        return role
    
    # ✅ Get users by role
    async def get_users_by_role(
        self,
        role_id: UUID,
        page: int = 1,
        limit: int = 10
    ) -> Tuple[List[UserResponse], int]:
        """Get all users with specific role"""
        # Check if role exists
        role = await self.get_role_by_id(role_id)
        if not role:
            raise NotFoundException("Role not found")
        
        # Build query
        query = select(User).options(selectinload(User.roles)).join(User.roles).where(
            Role.id == role_id
        )
        
        # Get total count
        count_query = select(func.count(User.id)).join(User.roles).where(Role.id == role_id)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(User.created_at.desc())
        
        # Execute query
        result = await self.db.execute(query)
        users = result.scalars().unique().all()
        
        # Convert to UserResponse
        user_responses = []
        for user in users:
            user_dict = {
                "id": user.id,
                "email": user.email,
                "email_confirmed": user.email_confirmed,
                "full_name": user.full_name,
                "roles": [r.name for r in user.roles],
                "is_active": user.is_active,
                "last_login": user.last_login,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }
            user_responses.append(UserResponse(**user_dict))
        
        return user_responses, total
    
    # ✅ Get role statistics
    async def get_role_statistics(self) -> dict:
        """Get role statistics"""
        # Get all roles
        roles_result = await self.db.execute(select(Role))
        roles = roles_result.scalars().all()
        
        total_roles = len(roles)
        role_stats = []
        
        for role in roles:
            # Total users with this role
            total_users_result = await self.db.execute(
                select(func.count(User.id))
                .join(User.roles)
                .where(Role.id == role.id)
            )
            total_users = total_users_result.scalar()
            
            # Active users with this role
            active_users_result = await self.db.execute(
                select(func.count(User.id))
                .join(User.roles)
                .where(Role.id == role.id, User.is_active == True)
            )
            active_users = active_users_result.scalar()
            
            role_stats.append({
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "user_count": total_users,
                "active_users": active_users,
                "inactive_users": total_users - active_users
            })
        
        return {
            "total_roles": total_roles,
            "roles": role_stats
        }
    
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