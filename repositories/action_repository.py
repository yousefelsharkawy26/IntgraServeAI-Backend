import re
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.action import Action


class ActionNameConflict(Exception):
    """Raised when a database-level create would violate name uniqueness."""


class ActionRepository:
    """SQLAlchemy persistence boundary for Action Registry entries."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, action_id: str) -> Optional[Action]:
        return await self.session.get(Action, action_id)

    async def get_by_name(self, name: str) -> Optional[Action]:
        result = await self.session.execute(select(Action).where(Action.name == name))
        return result.scalar_one_or_none()

    async def list(
        self,
        action_type: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> list[Action]:
        statement = select(Action)
        if action_type:
            statement = statement.where(Action.type == action_type)
        if active is not None:
            statement = statement.where(Action.active.is_(active))
        if search:
            pattern = f"%{search}%"
            statement = statement.where(
                or_(Action.name.ilike(pattern), Action.description.ilike(pattern))
            )
        result = await self.session.execute(statement.order_by(Action.id))
        return list(result.scalars().all())

    async def create(self, action: Action) -> Action:
        # Serialize ID allocation on PostgreSQL. This avoids duplicate ACT IDs
        # when multiple workers create actions concurrently.
        if self.session.bind and self.session.bind.dialect.name == "postgresql":
            await self.session.execute(
                select(func.pg_advisory_xact_lock(0x414354494F4E))
            )

        # Recheck under the allocation lock so concurrent API workers return the
        # established duplicate-name error instead of leaking an IntegrityError.
        if await self.get_by_name(action.name) is not None:
            raise ActionNameConflict(action.name)
        if not action.id:
            action.id = await self.next_id(action.type)

        self.session.add(action)
        await self.session.flush()
        return action

    async def update(self, action: Action, values: dict[str, Any]) -> Action:
        for field, value in values.items():
            setattr(action, field, value)
        await self.session.flush()
        await self.session.refresh(action)
        return action

    async def delete(self, action: Action) -> None:
        await self.session.delete(action)
        await self.session.flush()

    async def next_id(self, action_type: str) -> str:
        prefix = "INT" if action_type == "internal" else "ACT"
        result = await self.session.execute(
            select(Action.id).where(Action.id.like(f"{prefix}-%"))
        )
        pattern = re.compile(rf"^{prefix}-(\d+)$")
        highest = max(
            (int(match.group(1)) for value in result.scalars() if (match := pattern.match(value))),
            default=0,
        )
        return f"{prefix}-{highest + 1:03d}"

    async def upsert(self, action_id: str, values: dict[str, Any]) -> Action:
        action = await self.get_by_id(action_id)
        if action is None:
            action = Action(id=action_id, **values)
            self.session.add(action)
        else:
            for field, value in values.items():
                setattr(action, field, value)
        await self.session.flush()
        return action
