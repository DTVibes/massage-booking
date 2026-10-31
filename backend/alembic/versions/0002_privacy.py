"""privacy policy: consent, anonymization, operator details

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('privacy_accepted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('anonymized_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('settings', sa.Column('operator_name', sa.String(length=300), server_default='', nullable=False))
    op.add_column('settings', sa.Column('operator_inn', sa.String(length=12), server_default='', nullable=False))
    op.add_column('settings', sa.Column('privacy_email', sa.String(length=200), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('settings', 'privacy_email')
    op.drop_column('settings', 'operator_inn')
    op.drop_column('settings', 'operator_name')
    op.drop_column('users', 'anonymized_at')
    op.drop_column('users', 'privacy_accepted_at')
