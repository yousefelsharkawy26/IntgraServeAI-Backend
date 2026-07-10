"""add assigned_agent_id to chat_conversations

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2024-07-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'chat_conversations',
        sa.Column('assigned_agent_id', sa.UUID(), nullable=True)
    )
    op.create_index(
        op.f('ix_chat_conversations_assigned_agent_id'),
        'chat_conversations',
        ['assigned_agent_id'],
        unique=False
    )
    op.create_foreign_key(
        'fk_chat_conversations_assigned_agent_id_users',
        'chat_conversations',
        'users',
        ['assigned_agent_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_chat_conversations_assigned_agent_id_users',
        'chat_conversations',
        type_='foreignkey'
    )
    op.drop_index(
        op.f('ix_chat_conversations_assigned_agent_id'),
        table_name='chat_conversations'
    )
    op.drop_column('chat_conversations', 'assigned_agent_id')
