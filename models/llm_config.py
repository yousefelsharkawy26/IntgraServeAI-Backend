from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import relationship

from models.base import BaseModel, JSONVariant
from utils.encrypted_type import EncryptedText


class LLMConfiguration(BaseModel):
    """Reusable LLM provider/model settings consumed by ModelFactory."""

    __tablename__ = "llm_configurations"
    __table_args__ = (
        UniqueConstraint("tenant_key", "name", name="uq_llm_configurations_tenant_name"),
    )

    tenant_key = Column(String(100), nullable=False, default="default", server_default="default", index=True)
    name = Column(String(150), nullable=False)
    provider = Column(String(100), nullable=False, index=True)
    location = Column(String(50), nullable=False)
    model_name = Column(String(255), nullable=False)
    api_key = Column(EncryptedText, nullable=True)
    api_key_reference = Column(String(255), nullable=True)
    temperature = Column(Float, nullable=False, default=0.7, server_default="0.7")
    max_tokens = Column(Integer, nullable=False, default=2048, server_default="2048")
    system_prompt_template = Column(Text, nullable=False, default="", server_default="")
    active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    config_json = Column(JSONVariant, nullable=False, default=dict, server_default=text("'{}'"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    agents = relationship("AgentConfig", back_populates="llm_config")
