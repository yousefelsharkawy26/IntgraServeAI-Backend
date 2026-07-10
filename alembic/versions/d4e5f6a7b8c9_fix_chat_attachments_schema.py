"""fix chat attachments schema

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-10 07:05:00.000000

This migration reconciles existing databases that may have a partially-created
chat_attachments table with the current SQLAlchemy model.  The table is queried
whenever chat messages are loaded with attachments, so missing columns cause
conversation detail endpoints to fail with 500.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column['name'] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, 'chat_attachments'):
        op.create_table(
            'chat_attachments',
            sa.Column('chat_message_id', sa.UUID(), nullable=False),
            sa.Column('filename', sa.String(length=500), nullable=False),
            sa.Column('content_type', sa.String(length=100), nullable=False, server_default='application/octet-stream'),
            sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('storage_path', sa.String(length=1000), nullable=False, server_default=''),
            sa.Column('storage_backend', sa.String(length=50), nullable=False, server_default='local'),
            sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.ForeignKeyConstraint(['chat_message_id'], ['chat_messages.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_chat_attachments_chat_message_id'), 'chat_attachments', ['chat_message_id'], unique=False)
        op.create_index(op.f('ix_chat_attachments_id'), 'chat_attachments', ['id'], unique=True)
        return

    existing = _column_names(inspector, 'chat_attachments')

    with op.batch_alter_table('chat_attachments') as batch_op:
        if 'content_type' not in existing:
            batch_op.add_column(sa.Column('content_type', sa.String(length=100), nullable=False, server_default='application/octet-stream'))
        if 'size_bytes' not in existing:
            batch_op.add_column(sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'))
        if 'storage_path' not in existing:
            batch_op.add_column(sa.Column('storage_path', sa.String(length=1000), nullable=False, server_default=''))
        if 'storage_backend' not in existing:
            batch_op.add_column(sa.Column('storage_backend', sa.String(length=50), nullable=False, server_default='local'))
        if 'uploaded_at' not in existing:
            batch_op.add_column(sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')))

    # Add indexes if they are missing.  Existing deployments may already have
    # some indexes depending on how the partial table was created.
    inspector = sa.inspect(bind)
    indexes = {index['name'] for index in inspector.get_indexes('chat_attachments')}
    if 'ix_chat_attachments_chat_message_id' not in indexes:
        op.create_index(op.f('ix_chat_attachments_chat_message_id'), 'chat_attachments', ['chat_message_id'], unique=False)
    if 'ix_chat_attachments_id' not in indexes:
        op.create_index(op.f('ix_chat_attachments_id'), 'chat_attachments', ['id'], unique=True)


def downgrade() -> None:
    # Keep this conservative: dropping these columns could destroy attachment
    # metadata/files for environments that already rely on them.
    pass
