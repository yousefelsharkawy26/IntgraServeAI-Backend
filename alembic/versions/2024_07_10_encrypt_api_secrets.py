"""rename encrypted_primary_secret/secondary_secret and add app-level encryption

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2024-07-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('api_authentications', 'encrypted_primary_secret', new_column_name='primary_secret')
    op.alter_column('api_authentications', 'encrypted_secondary_secret', new_column_name='secondary_secret')


def downgrade() -> None:
    op.alter_column('api_authentications', 'primary_secret', new_column_name='encrypted_primary_secret')
    op.alter_column('api_authentications', 'secondary_secret', new_column_name='encrypted_secondary_secret')
