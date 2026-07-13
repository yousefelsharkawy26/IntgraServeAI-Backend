"""independent LLM configurations and database agent backups

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_configurations",
        sa.Column("tenant_key", sa.String(100), server_default="default", nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("location", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("api_key_reference", sa.String(255), nullable=True),
        sa.Column("temperature", sa.Float(), server_default="0.7", nullable=False),
        sa.Column("max_tokens", sa.Integer(), server_default="2048", nullable=False),
        sa.Column("system_prompt_template", sa.Text(), server_default="", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_key", "name", name="uq_llm_configurations_tenant_name"),
    )
    op.create_index("ix_llm_configurations_tenant_key", "llm_configurations", ["tenant_key"])
    op.create_index("ix_llm_configurations_provider", "llm_configurations", ["provider"])
    op.create_index("ix_llm_configurations_active", "llm_configurations", ["active"])
    op.create_index("ix_llm_configurations_id", "llm_configurations", ["id"], unique=True)

    op.execute(
        """
        INSERT INTO llm_configurations (
            id, tenant_key, name, provider, location, model_name,
            api_key, api_key_reference, temperature, max_tokens,
            system_prompt_template, active, config_json, created_at, updated_at
        )
        SELECT
            id,
            'default',
            provider || ' ' || model_name || ' ' || left(id::text, 8),
            provider,
            location,
            model_name,
            NULL,
            api_key_reference,
            temperature,
            max_tokens,
            system_prompt_template,
            active,
            config_json,
            created_at,
            updated_at
        FROM agent_llm_configs
        """
    )

    op.add_column("agent_configs", sa.Column("llm_config_id", sa.UUID(), nullable=True))
    op.execute(
        """
        UPDATE agent_configs AS agent
        SET llm_config_id = (
            SELECT llm.id
            FROM agent_llm_configs AS llm
            WHERE llm.agent_config_id = agent.id
            ORDER BY llm.active DESC, llm.updated_at DESC
            LIMIT 1
        )
        """
    )
    op.alter_column("agent_configs", "llm_config_id", nullable=False)
    op.create_index("ix_agent_configs_llm_config_id", "agent_configs", ["llm_config_id"])
    op.create_foreign_key(
        "fk_agent_configs_llm_config_id",
        "agent_configs",
        "llm_configurations",
        ["llm_config_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "agent_config_backups",
        sa.Column("agent_config_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("encrypted_llm_api_key", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_config_id"], ["agent_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_config_backups_agent_config_id", "agent_config_backups", ["agent_config_id"])
    op.create_index("ix_agent_config_backups_id", "agent_config_backups", ["id"], unique=True)

    op.drop_table("agent_llm_configs")


def downgrade() -> None:
    op.create_table(
        "agent_llm_configs",
        sa.Column("agent_config_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("location", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("temperature", sa.Float(), server_default="0.7", nullable=False),
        sa.Column("max_tokens", sa.Integer(), server_default="2048", nullable=False),
        sa.Column("api_key_reference", sa.String(255), nullable=True),
        sa.Column("system_prompt_template", sa.Text(), server_default="", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_config_id"], ["agent_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO agent_llm_configs (
            id, agent_config_id, provider, location, model_name,
            temperature, max_tokens, api_key_reference,
            system_prompt_template, active, config_json, created_at, updated_at
        )
        SELECT
            agent.id,
            agent.id,
            llm.provider,
            llm.location,
            llm.model_name,
            llm.temperature,
            llm.max_tokens,
            llm.api_key_reference,
            llm.system_prompt_template,
            TRUE,
            llm.config_json,
            llm.created_at,
            llm.updated_at
        FROM agent_configs AS agent
        JOIN llm_configurations AS llm ON llm.id = agent.llm_config_id
        """
    )
    op.drop_table("agent_config_backups")
    op.drop_constraint("fk_agent_configs_llm_config_id", "agent_configs", type_="foreignkey")
    op.drop_index("ix_agent_configs_llm_config_id", table_name="agent_configs")
    op.drop_column("agent_configs", "llm_config_id")
    op.drop_table("llm_configurations")
