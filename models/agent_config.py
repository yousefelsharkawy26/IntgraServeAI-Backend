from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid as UUID

from models.base import BaseModel, JSONVariant


class AgentConfig(BaseModel):
    """Core, frequently queried agent configuration."""

    __tablename__ = "agent_configs"
    __table_args__ = (
        UniqueConstraint("tenant_key", "name", name="uq_agent_configs_tenant_name"),
        Index(
            "uq_agent_configs_active_tenant",
            "tenant_key",
            unique=True,
            postgresql_where=text("active"),
            sqlite_where=text("active = 1"),
        ),
    )

    tenant_key = Column(String(100), nullable=False, default="default", server_default="default", index=True)
    name = Column(String(100), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    tone = Column(String(500), nullable=False)
    version = Column(String(50), nullable=False)
    active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    llm_configs = relationship("AgentLLMConfig", back_populates="agent_config", cascade="all, delete-orphan")
    action_defaults = relationship("AgentActionDefault", back_populates="agent_config", cascade="all, delete-orphan")
    prompts = relationship("AgentPrompt", back_populates="agent_config", cascade="all, delete-orphan")


class AgentLLMConfig(BaseModel):
    """Provider configuration; multiple provider rows may belong to one agent."""

    __tablename__ = "agent_llm_configs"
    __table_args__ = (
        UniqueConstraint(
            "agent_config_id", "provider", "location", "model_name",
            name="uq_agent_llm_provider_model",
        ),
        Index(
            "uq_agent_llm_active",
            "agent_config_id",
            unique=True,
            postgresql_where=text("active"),
            sqlite_where=text("active = 1"),
        ),
    )

    agent_config_id = Column(UUID(as_uuid=True), ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(100), nullable=False, index=True)
    location = Column(String(50), nullable=False)
    model_name = Column(String(255), nullable=False)
    temperature = Column(Float, nullable=False, default=0.7, server_default="0.7")
    max_tokens = Column(Integer, nullable=False, default=2048, server_default="2048")
    api_key_reference = Column(String(255), nullable=True)
    system_prompt_template = Column(Text, nullable=False, default="", server_default="")
    active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    config_json = Column(JSONVariant, nullable=False, default=dict, server_default=text("'{}'"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    agent_config = relationship("AgentConfig", back_populates="llm_configs")


class AgentActionDefault(BaseModel):
    """Flexible defaults for one action type."""

    __tablename__ = "agent_action_defaults"
    __table_args__ = (
        UniqueConstraint("agent_config_id", "action_type", name="uq_agent_action_default_type"),
    )

    agent_config_id = Column(UUID(as_uuid=True), ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(100), nullable=False, index=True)
    config_json = Column(JSONVariant, nullable=False, default=dict, server_default=text("'{}'"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    agent_config = relationship("AgentConfig", back_populates="action_defaults")


class AgentPrompt(BaseModel):
    """Versioned prompt content for an agent."""

    __tablename__ = "agent_prompts"
    __table_args__ = (
        UniqueConstraint("agent_config_id", "name", "version", name="uq_agent_prompt_version"),
        Index(
            "uq_agent_prompt_active",
            "agent_config_id",
            unique=True,
            postgresql_where=text("active"),
            sqlite_where=text("active = 1"),
        ),
    )

    agent_config_id = Column(UUID(as_uuid=True), ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, default="system", server_default="system")
    content = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    active = Column(Boolean, nullable=False, default=False, server_default="false", index=True)

    agent_config = relationship("AgentConfig", back_populates="prompts")
