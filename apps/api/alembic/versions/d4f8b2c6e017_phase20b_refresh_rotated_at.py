"""phase20b refresh token rotated_at

Revision ID: d4f8b2c6e017
Revises: c3e7a1f5d920
Create Date: 2026-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f8b2c6e017'
down_revision: Union[str, Sequence[str], None] = 'c3e7a1f5d920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # docs/47 D10: when a refresh token was rotated (never set by logout or family revocation)
    op.add_column('refresh_sessions', sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('refresh_sessions', 'rotated_at')
