"""phase13a snapshot content-addressed key

Revision ID: f9b5d3e6a012
Revises: e8a4c2d5f901
Create Date: 2026-10-29 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f9b5d3e6a012'
down_revision: Union[str, Sequence[str], None] = 'e8a4c2d5f901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # docs/39 D1 (DCR SPNC_SNAPSHOT_CONTENT_KEY): several snapshot rows may share one immutable blob
    op.drop_constraint(op.f('uq_code_snapshots_object_key'), 'code_snapshots', type_='unique')
    op.create_index('ix_code_snapshots_object_key', 'code_snapshots', ['object_key'])


def downgrade() -> None:
    """Downgrade schema. Fails if rows already share a key (expected after upgrade use)."""
    op.drop_index('ix_code_snapshots_object_key', table_name='code_snapshots')
    op.create_unique_constraint(op.f('uq_code_snapshots_object_key'), 'code_snapshots', ['object_key'])
