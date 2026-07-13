"""create PostgreSQL-backed Action Registry

Revision ID: a7b8c9d0e1f2
Revises: d4e5f6a7b8c9
Create Date: 2026-07-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "actions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("requires_human_input", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("execution_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("response_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_actions_name"),
    )
    op.create_index("ix_actions_name", "actions", ["name"], unique=False)
    op.create_index("ix_actions_type", "actions", ["type"], unique=False)
    op.create_index("ix_actions_active", "actions", ["active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_actions_active", table_name="actions")
    op.drop_index("ix_actions_type", table_name="actions")
    op.drop_index("ix_actions_name", table_name="actions")
    op.drop_table("actions")
