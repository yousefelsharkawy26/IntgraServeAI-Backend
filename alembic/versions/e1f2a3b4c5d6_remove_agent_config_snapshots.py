"""remove obsolete agent configuration snapshots

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-13 00:00:00.000000

The snapshot table only supported the legacy file-backup API. Prompt history is
preserved independently in agent_prompts.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("agent_config_snapshots")
    op.drop_column("agent_configs", "restored_from")


def downgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column("restored_from", sa.String(length=255), nullable=True),
    )
    op.create_table(
        "agent_config_snapshots",
        sa.Column("agent_config_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_config_id"],
            ["agent_configs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename"),
    )
    op.create_index(
        "ix_agent_config_snapshots_agent_config_id",
        "agent_config_snapshots",
        ["agent_config_id"],
    )
    op.create_index(
        "ix_agent_config_snapshots_filename",
        "agent_config_snapshots",
        ["filename"],
        unique=True,
    )
