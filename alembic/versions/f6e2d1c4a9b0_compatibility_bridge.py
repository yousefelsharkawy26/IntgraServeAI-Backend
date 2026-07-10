"""compatibility bridge for legacy local revision

Revision ID: f6e2d1c4a9b0
Revises: fc3e037c11c0
Create Date: 2026-07-10 03:15:00.000000

This no-op migration preserves compatibility with local databases that were
stamped with revision f6e2d1c4a9b0 before the current migration chain was
normalized. It lets those databases continue upgrading to the later security
migrations, including token_blacklist.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'f6e2d1c4a9b0'
down_revision: Union[str, Sequence[str], None] = 'fc3e037c11c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Compatibility-only bridge. Schema changes continue in the next migration.
    pass


def downgrade() -> None:
    # Compatibility-only bridge.
    pass
