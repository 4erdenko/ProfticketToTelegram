"""empty message

Revision ID: b890ff1a5b99
Revises: e00f3228618e
Create Date: 2024-12-21 21:08:51.553415

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b890ff1a5b99'
down_revision: Union[str, None] = 'e00f3228618e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('shows',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('show_id', sa.Integer(), nullable=True),
    sa.Column('theater', sa.String(), nullable=True),
    sa.Column('scene', sa.String(), nullable=True),
    sa.Column('show_name', sa.String(), nullable=True),
    sa.Column('date', sa.String(), nullable=True),
    sa.Column('duration', sa.String(), nullable=True),
    sa.Column('age', sa.String(), nullable=True),
    sa.Column('seats', sa.Integer(), nullable=True),
    sa.Column('image', sa.String(), nullable=True),
    sa.Column('annotation', sa.String(), nullable=True),
    sa.Column('min_price', sa.Integer(), nullable=True),
    sa.Column('max_price', sa.Integer(), nullable=True),
    sa.Column('pushkin', sa.Boolean(), nullable=True),
    sa.Column('buy_link', sa.String(), nullable=True),
    sa.Column('actors', sa.String(), nullable=True),
    sa.Column('month', sa.Integer(), nullable=True),
    sa.Column('year', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('shows')
    # ### end Alembic commands ###