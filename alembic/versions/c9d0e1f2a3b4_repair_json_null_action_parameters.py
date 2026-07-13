"""repair JSON null Action parameters

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-13 00:00:00.000000

SQLAlchemy JSON/JSONB serializes Python None as the JSON literal ``null`` by
default. A SQL ``IS NULL`` repair does not match that value, and PostgreSQL
``NOT NULL`` does not reject it. Repair both representations and enforce that
parameters is a JSON object.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE actions
        SET parameters = '{}'::jsonb
        WHERE parameters IS NULL OR parameters = 'null'::jsonb
        """
    )
    op.create_check_constraint(
        "ck_actions_parameters_json_object",
        "actions",
        "COALESCE(jsonb_typeof(parameters) = 'object', false)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_actions_parameters_json_object",
        "actions",
        type_="check",
    )
