"""add_token_blacklist_table

Revision ID: a1b2c3d4e5f6
Revises: fc3e037c11c0
Create Date: 2024-07-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'fc3e037c11c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'token_blacklist',
        sa.Column('token_hash', sa.String(length=255), nullable=False, index=True),
        sa.Column('token_type', sa.String(length=50), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_token_blacklist_id'), 'token_blacklist', ['id'], unique=True)
    op.create_index(op.f('ix_token_blacklist_token_hash'), 'token_blacklist', ['token_hash'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_token_blacklist_token_hash'), table_name='token_blacklist')
    op.drop_index(op.f('ix_token_blacklist_id'), table_name='token_blacklist')
    op.drop_table('token_blacklist')
