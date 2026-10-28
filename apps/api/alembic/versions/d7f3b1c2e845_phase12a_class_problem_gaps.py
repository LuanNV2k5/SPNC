"""phase12a class invite code and problem bank fields

Revision ID: d7f3b1c2e845
Revises: c6e2a9d4b710
Create Date: 2026-10-29 10:00:00.000000

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7f3b1c2e845'
down_revision: Union[str, Sequence[str], None] = 'c6e2a9d4b710'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# docs/38 D1: no 0/O/1/I/L
INVITE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def upgrade() -> None:
    """Upgrade schema."""
    # REQ-CLASS-001: unique invite code, backfilled for existing classes
    op.add_column('classes', sa.Column('invite_code', sa.String(length=16), nullable=True))
    bind = op.get_bind()
    used = set()
    for (class_id,) in bind.execute(sa.text("SELECT id FROM classes")).fetchall():
        code = None
        while code is None or code in used:
            code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(8))
        used.add(code)
        bind.execute(sa.text("UPDATE classes SET invite_code = :c WHERE id = :id"), {"c": code, "id": class_id})
    op.alter_column('classes', 'invite_code', nullable=False)
    op.create_unique_constraint(op.f('uq_classes_invite_code'), 'classes', ['invite_code'])

    # REQ-PROB-001 / domain §1: statement fields and difficulty; D5 soft delete
    op.add_column('problems', sa.Column('constraints', sa.Text(), nullable=True))
    op.add_column('problems', sa.Column('input_format', sa.Text(), nullable=True))
    op.add_column('problems', sa.Column('output_format', sa.Text(), nullable=True))
    op.add_column('problems', sa.Column('difficulty', sa.String(length=10), nullable=True))
    op.create_check_constraint(op.f('ck_problems_difficulty_valid'), 'problems',
                               "difficulty IS NULL OR difficulty IN ('EASY', 'MEDIUM', 'HARD')")
    op.add_column('problems', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_problems_owner_deleted', 'problems', ['owner_id', 'deleted_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_problems_owner_deleted', table_name='problems')
    op.drop_column('problems', 'deleted_at')
    op.drop_constraint(op.f('ck_problems_difficulty_valid'), 'problems', type_='check')
    op.drop_column('problems', 'difficulty')
    op.drop_column('problems', 'output_format')
    op.drop_column('problems', 'input_format')
    op.drop_column('problems', 'constraints')
    op.drop_constraint(op.f('uq_classes_invite_code'), 'classes', type_='unique')
    op.drop_column('classes', 'invite_code')
