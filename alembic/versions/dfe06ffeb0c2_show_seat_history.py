"""add seat history table with index

Revision ID: dfe06ffeb0c2
Revises: 9598994bf033
Create Date: 2024-01-01 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'dfe06ffeb0c2'
down_revision: Union[str, None] = '9598994bf033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'show_seat_history',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('show_id', sa.String(), sa.ForeignKey('shows.id'), index=True),
        sa.Column('timestamp', sa.Integer(), nullable=False),
        sa.Column('seats', sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('show_seat_history')
