"""Persist notification subscriptions and their delivery baselines."""

import sqlalchemy as sa

from alembic import op

revision: str = 'c920bf740e61'
down_revision: str = 'a137bd92c410'
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.BigInteger(),
            sa.ForeignKey('users.user_id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('interval_seconds', sa.Integer(), nullable=False),
        sa.Column(
            'enabled', sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('next_due_at', sa.Integer(), nullable=False),
        sa.Column('last_sent_at', sa.Integer()),
        sa.Column('baseline', sa.JSON(), nullable=False),
        sa.Column('retry_at', sa.Integer()),
        sa.Column(
            'failure_count', sa.Integer(), nullable=False, server_default='0'
        ),
        sa.Column(
            'needs_baseline',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.UniqueConstraint('user_id', 'kind', 'key'),
        sa.CheckConstraint("kind IN ('show', 'actor')"),
        sa.CheckConstraint(
            'interval_seconds IN (1800, 3600, 21600, 43200, 86400, 604800)'
        ),
    )
    op.create_index('ix_subscriptions_user_id', 'subscriptions', ['user_id'])
    op.create_index(
        'ix_subscriptions_due',
        'subscriptions',
        ['enabled', 'next_due_at', 'retry_at'],
    )


def downgrade() -> None:
    op.drop_table('subscriptions')
