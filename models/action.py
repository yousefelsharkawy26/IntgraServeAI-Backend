from sqlalchemy import Boolean, Column, DateTime, String, Text, func, text

from core.database import Base
from models.base import JSONVariant


class Action(Base):
    """Persisted Action Registry entry.

    The public action identifier (for example ``ACT-001``) remains the primary
    key so API and Action Engine consumers keep seeing the same IDs.
    """

    __tablename__ = "actions"

    id = Column(String(32), primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False)
    type = Column(String(50), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    requires_confirmation = Column(Boolean, nullable=False, default=False, server_default="false")
    requires_human_input = Column(Boolean, nullable=False, default=False, server_default="false")
    execution_config = Column(JSONVariant, nullable=True)
    parameters = Column(
        JSONVariant,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    response_config = Column(JSONVariant, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def to_dict(self, *, include_id: bool = True, include_engine_fields: bool = False) -> dict:
        data = {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "active": self.active,
            "requires_confirmation": self.requires_confirmation,
            "execution_config": self.execution_config,
            "parameters": self.parameters,
            "response_config": self.response_config,
        }
        if self.requires_human_input or include_engine_fields:
            data["requires_human_input"] = self.requires_human_input
        if include_id:
            data["id"] = self.id
        return data
