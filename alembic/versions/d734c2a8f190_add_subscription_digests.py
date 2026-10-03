"""Keep complete subscription digests available through pagination."""

import sqlalchemy as sa

from alembic import op

revision: str = 'd734c2a8f190'
down_revision: str = 'c920bf740e61'
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        'subscription_digests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.BigInteger(),
            sa.ForeignKey('users.user_id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('pages', sa.JSON(), nullable=False),
    )
    op.create_index(
        'ix_subscription_digests_user_id', 'subscription_digests', ['user_id']
    )


def downgrade() -> None:
    op.drop_table('subscription_digests')
