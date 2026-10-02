from pathlib import Path

from tests.runtime_helpers import run_runtime_script


def test_html_chunks_preserve_formatting_and_unicode(tmp_path: Path) -> None:
    run_runtime_script(
        r"""
from html.parser import HTMLParser
from telegram.tg_utils import split_message_by_separator

class Parsed(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.text = ''
        self.feed(html)
        assert not self.tags
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'a':
            assert dict(attrs)['href'] == 'https://example.com/?a=1&b=2'
    def handle_endtag(self, tag):
        assert self.tags.pop() == tag
    def handle_data(self, text):
        self.text += text

source = '<b><i>' + '🎭&amp;&#x1f600;' * 100 + '</i></b>'
source += '<a href="https://example.com/?a=1&amp;b=2">' + 'x' * 300 + '</a>'
chunks = split_message_by_separator(source, separator='\n\n', max_length=80)
assert len(chunks) > 2
visible = [Parsed(chunk).text for chunk in chunks]
assert all(text.strip() and len(text.encode('utf-16-le')) // 2 <= 80
           for text in visible)
assert ''.join(visible) == Parsed(source).text
assert split_message_by_separator('', max_length=80) == []
assert all(split_message_by_separator('x' * 200, max_length=80))
""",
        tmp_path,
    )


def test_continuation_prefix_fits_message_limit(tmp_path: Path) -> None:
    run_runtime_script(
        r"""
import asyncio
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import AsyncMock
from telegram import tg_utils

class Parsed(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.text = ''
        self.feed(html)
    def handle_data(self, text):
        self.text += text

message = SimpleNamespace(answer=AsyncMock())
tg_utils.asyncio.sleep = AsyncMock()
asyncio.run(tg_utils.send_chunks_answer(message, '<b>' + '🎭' * 1000 + '</b>'))
sent = [call.args[0] for call in message.answer.call_args_list]
assert len(sent) > 10
assert 'Продолжение (2/' in sent[1]
assert all(0 < len(Parsed(text).text.encode('utf-16-le')) // 2 <= 100
           for text in sent)
""",
        tmp_path,
        {'MAX_MSG_LEN': '100'},
    )


def test_actor_normalization_matches_cast_and_rejects_buttons(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from telegram.db.models import Show
from telegram.db.user_operations import get_shows_from_db
from telegram.tg_utils import check_text

name = asyncio.run(check_text(SimpleNamespace(text='  Анна  Мария‑Смирнова ')))
assert name == 'анна мария-смирнова'
for text in ('📊 Аналитика', 'Ivan <foo>', '/set_actor', 'October 2026'):
    assert asyncio.run(check_text(SimpleNamespace(text=text))) is None
show = Show(id='1', actors=json.dumps(['Анна Мария-Смирнова']),
            show_name='Example', date='02.10.2026, 19:00', seats=5,
            updated_at=1800000000)
result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [show]))
session = SimpleNamespace(execute=AsyncMock(return_value=result))
report = asyncio.run(get_shows_from_db(session, 10, 2026, actor_filter=name))
assert 'Example' in report
""",
        tmp_path,
    )


def test_start_and_navigation_leave_actor_form(tmp_path: Path) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.types import Chat, Message, Update, User
from telegram.filters import month_filter
from telegram.handlers import analytics_handlers as analytics
from telegram.handlers import personal_handlers as personal
from telegram.handlers import user_handlers as users

class OfflineSession(BaseSession):
    async def close(self):
        pass
    async def stream_content(self, *args, **kwargs):
        yield b''
    async def make_request(self, bot, method, timeout=None):
        return Message(message_id=10, date=datetime.now(timezone.utc),
                       chat=Chat(id=5, type='private'), text=method.text)

async def run():
    bot = Bot('1:test', session=OfflineSession())
    dp = Dispatcher()
    dp.include_router(users.user_router)
    dp.include_router(personal.personal_user_router)
    dp.include_router(analytics.analytics_router)
    users.main_keyboard = AsyncMock(return_value=None)
    personal.main_keyboard = AsyncMock(return_value=None)
    month_filter.get_available_months = AsyncMock(return_value=[])
    personal.set_spectacle_fio = AsyncMock()
    state = dp.fsm.get_context(bot, chat_id=5, user_id=5)
    for i, text in enumerate(['/start', '📊 Аналитика', '↩️'], 1):
        await state.set_state(personal.ChooseYourFighter.set_your_fighter)
        message = Message(message_id=i, date=datetime.now(timezone.utc),
                          chat=Chat(id=5, type='private'),
                          from_user=User(id=5, is_bot=False, first_name='user'),
                          text=text)
        await dp.feed_update(bot, Update(update_id=i, message=message),
                             session=None)
        assert await state.get_state() is None
    personal.set_spectacle_fio.assert_not_awaited()
    await dp.storage.close()
    await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_database_admin_flag_matches_keyboard_access(tmp_path: Path) -> None:
    run_runtime_script(
        r"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from telegram.filters.is_admin import IsAdmin, has_admin_access

async def run():
    message = SimpleNamespace(from_user=SimpleNamespace(id=5))
    for flag in (True, False):
        user = SimpleNamespace(admin=flag)
        session = SimpleNamespace(get=AsyncMock(return_value=user))
        assert await IsAdmin()(message, session) == flag
        assert has_admin_access(5, user) == flag
    assert await IsAdmin()(SimpleNamespace(from_user=SimpleNamespace(id=1)),
                           SimpleNamespace())

asyncio.run(run())
""",
        tmp_path,
    )


def test_admin_report_escapes_names_and_counts_active_union(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import Session
from telegram.db.models import User
from telegram.handlers import admin_handlers

metadata = MetaData()
table = User.__table__.to_metadata(metadata)
table.c.start_bot_date.server_default = None
engine = create_engine('sqlite://')
metadata.create_all(engine)
with engine.begin() as connection:
    connection.execute(table.insert(), [
        {'user_id': 1, 'banned': True, 'bot_blocked': True,
         'bot_full_name': '<Foo> & Bar', 'spectacle_full_name': '<Actor>'},
        {'user_id': 2, 'banned': False, 'bot_blocked': False,
         'bot_full_name': 'Normal', 'spectacle_full_name': None},
    ])

async def run():
    with Session(engine) as session:
        async def execute(query):
            return session.execute(query)
        message = SimpleNamespace(answer=AsyncMock())
        admin_handlers.send_chunks_answer = AsyncMock()
        await admin_handlers.cmd_admin_users_overview(
            message, SimpleNamespace(execute=execute))
        report = admin_handlers.send_chunks_answer.call_args.args[1]
        assert 'Активных: <b>1</b>' in report
        assert '&lt;Foo&gt; &amp; Bar' in report
        assert '<Foo>' not in report and '<Actor>' not in report

asyncio.run(run())
engine.dispose()
""",
        tmp_path,
    )
