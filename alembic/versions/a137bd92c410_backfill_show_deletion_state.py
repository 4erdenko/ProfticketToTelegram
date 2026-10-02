"""Backfill and constrain the show deletion state."""

from alembic import op

revision: str = 'a137bd92c410'
down_revision: str = 'fb93e353abb0'
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.execute('UPDATE shows SET is_deleted = false WHERE is_deleted IS NULL')
    op.alter_column(
        'shows', 'is_deleted', nullable=False, server_default='false'
    )
    op.create_index(
        'ix_show_seat_history_show_time',
        'show_seat_history',
        ['show_id', 'timestamp', 'id'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_show_seat_history_show_time', table_name='show_seat_history'
    )
    op.alter_column('shows', 'is_deleted', nullable=True, server_default=None)
