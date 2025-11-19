from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from uuid import UUID

from models.user import Role
from utils.exceptions import NotFoundException


class RoleService:
    """Service for role management"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_all_roles(self) -> List[Role]:
        """
        Get all roles
        
        Returns:
            List of Role objects
        """
        result = await self.db.execute(
            select(Role).order_by(Role.name)
        )
        return result.scalars().all()
    
    async def get_role_by_id(self, role_id: UUID) -> Optional[Role]:
        """
        Get role by ID
        
        Args:
            role_id: Role UUID
            
        Returns:
            Role object or None
        """
        result = await self.db.execute(
            select(Role).where(Role.id == role_id)
        )
        return result.scalar_one_or_none()
    
    async def get_role_by_name(self, name: str) -> Optional[Role]:
        """
        Get role by name
        
        Args:
            name: Role name
            
        Returns:
            Role object or None
        """
        result = await self.db.execute(
            select(Role).where(Role.name == name)
        )
        return result.scalar_one_or_none()