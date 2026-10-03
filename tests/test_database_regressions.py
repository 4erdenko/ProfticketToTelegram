from pathlib import Path

from tests.runtime_helpers import run_runtime_script


def test_registration_handles_two_simultaneous_first_messages(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        """
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from aiogram.types import Message, Update, User as TelegramUser
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from telegram.db import Base
from telegram.db.models import User
from telegram.middlewares.logging_to_db import UserLoggingMiddleware

async def check():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    ready = asyncio.Event()
    arrivals = 0

    class Session:
        def __init__(self):
            self.sync = sessions()

        async def get(self, model, key):
            nonlocal arrivals
            result = self.sync.get(model, key)
            assert result is None
            arrivals += 1
            if arrivals == 2:
                ready.set()
            await ready.wait()
            return result

        async def execute(self, statement):
            return self.sync.execute(statement)

        async def commit(self):
            self.sync.commit()

    sender = TelegramUser(id=12, first_name='Test', is_bot=False)
    update = Update(update_id=1, message=Message(
        message_id=1, date=datetime.now(timezone.utc),
        chat={'id': 12, 'type': 'private'}, from_user=sender, text='/start',
    ))
    middleware = UserLoggingMiddleware()
    first, second = Session(), Session()
    try:
        await asyncio.gather(
            middleware.on_process_message(update, {'session': first}),
            middleware.on_process_message(update, {'session': second}),
        )
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(User)) == 1
            assert session.get(User, 12).bot_full_name == 'Test'
    finally:
        first.sync.close()
        second.sync.close()
        engine.dispose()

asyncio.run(check())
""",
        tmp_path,
    )


def test_migration_accepts_percent_encoded_database_password(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        """
import io
from pathlib import Path

from alembic import command
from alembic.config import Config

root = Path(__import__('main').__file__).parent
output = io.StringIO()
config = Config(str(root / 'alembic.ini'), output_buffer=output)
config.set_main_option('script_location', str(root / 'alembic'))
command.upgrade(config, 'head', sql=True)
sql = output.getvalue()
assert 'UPDATE shows SET is_deleted = false' in sql
assert 'ALTER COLUMN is_deleted SET NOT NULL' in sql
assert 'ix_show_seat_history_show_time' in sql
""",
        tmp_path,
        {'DB_URL': 'postgresql+asyncpg://test:p%40ss@127.0.0.1/test'},
    )


def test_private_interaction_restores_notifications_after_unblocking(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        """
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, InaccessibleMessage, Message, Update, User as TelegramUser
from telegram.db.models import User
from telegram.middlewares.logging_to_db import UserLoggingMiddleware

async def check():
    user = User(user_id=12, bot_blocked=True, _bot_blocked_date=10)
    session = SimpleNamespace(get=AsyncMock(return_value=user), commit=AsyncMock())
    middleware = UserLoggingMiddleware()
    sender = TelegramUser(id=12, first_name='User', is_bot=False)
    for chat in ({'id': -10, 'type': 'group'}, {'id': 12, 'type': 'private'}):
        message = Message(message_id=1, date=datetime.now(timezone.utc),
                          chat=chat, from_user=sender, text='/start')
        await middleware.on_process_message(Update(update_id=1, message=message),
                                            {'session': session})
        if chat['type'] == 'group':
            assert user.bot_blocked
            session.commit.assert_not_awaited()
        else:
            assert not user.bot_blocked and user.bot_blocked_date is None
            session.commit.assert_awaited_once()

    for chat in ({'id': -10, 'type': 'group'}, {'id': 99, 'type': 'private'},
                 {'id': 12, 'type': 'private'}):
        user.bot_blocked = True
        user._bot_blocked_date = 10
        session.commit.reset_mock()
        message = Message(message_id=1, date=datetime.now(timezone.utc),
                          chat=chat, text='Subscription')
        callback = CallbackQuery(id='test', from_user=sender,
                                 chat_instance='test', message=message,
                                 data='subscription:menu')
        await middleware.on_process_message(
            Update(update_id=2, callback_query=callback), {'session': session},
        )
        if chat['id'] != sender.id:
            assert user.bot_blocked
            session.commit.assert_not_awaited()
        else:
            assert not user.bot_blocked and user.bot_blocked_date is None
            session.commit.assert_awaited_once()

    user.bot_blocked = True
    session.commit.reset_mock()
    for unavailable in (None, InaccessibleMessage(
        message_id=1, date=0, chat={'id': 12, 'type': 'private'},
    )):
        callback = CallbackQuery(id='test', from_user=sender,
                                 chat_instance='test', message=unavailable,
                                 inline_message_id='test' if unavailable is None else None,
                                 data='subscription:menu')
        await middleware.on_process_message(
            Update(update_id=3, callback_query=callback), {'session': session},
        )
        assert user.bot_blocked
        session.commit.assert_not_awaited()

asyncio.run(check())
""",
        tmp_path,
    )
