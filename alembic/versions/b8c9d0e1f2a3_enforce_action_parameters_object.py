"""enforce non-null Action parameters objects

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-13 00:00:00.000000

Legacy parameterless actions were imported as SQL NULL because the old registry
omitted the optional field. Action Engine tools require a mapping, so repair
those rows before adding the database invariant.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE actions SET parameters = '{}'::jsonb WHERE parameters IS NULL")
    op.alter_column(
        "actions",
        "parameters",
        existing_type=postgresql.JSONB(),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def downgrade() -> None:
    op.alter_column(
        "actions",
        "parameters",
        existing_type=postgresql.JSONB(),
        nullable=True,
        server_default=None,
    )
