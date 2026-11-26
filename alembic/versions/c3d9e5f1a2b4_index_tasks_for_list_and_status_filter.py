"""index tasks for the list order and the status filter

Replaces ix_tasks_organization_id: ix_tasks_org_created starts with the same
column, so it serves every lookup the old index did.

Revision ID: c3d9e5f1a2b4
Revises: b7e1c2d4a9f0
Create Date: 2026-11-25 22:00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c3d9e5f1a2b4'
down_revision: Union[str, Sequence[str], None] = 'b7e1c2d4a9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_tasks_org_created', 'tasks', ['organization_id', 'created_at'])
    op.create_index('ix_tasks_org_status_created', 'tasks', ['organization_id', 'status', 'created_at'])
    op.drop_index('ix_tasks_organization_id', table_name='tasks')


def downgrade() -> None:
    op.create_index('ix_tasks_organization_id', 'tasks', ['organization_id'])
    op.drop_index('ix_tasks_org_status_created', table_name='tasks')
    op.drop_index('ix_tasks_org_created', table_name='tasks')
