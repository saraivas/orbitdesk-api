"""add organizations.deleted_at for soft delete (ADR 0007)

Revision ID: b7e1c2d4a9f0
Revises: 695d274629ae
Create Date: 2026-11-25 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e1c2d4a9f0'
down_revision: Union[str, Sequence[str], None] = '695d274629ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'deleted_at')
