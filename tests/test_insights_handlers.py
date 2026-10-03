from pathlib import Path

from tests.runtime_helpers import run_runtime_script


def test_trends_explain_unknown_inventory_and_preserve_old_buttons(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        """
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.types import Chat, Message, Update, User

from services.profticket.analytics_repository import AnalyticsRepository, ReportData
from services.profticket.insights import InventoryInsights
from telegram.db.models import Show
from telegram.handlers import analytics_handlers as handlers
from telegram.keyboards.analytics_keyboard import analytics_main_menu_keyboard
from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU, LEXICON_RU

class OfflineSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.requests = []
    async def close(self):
        pass
    async def stream_content(self, *args, **kwargs):
        yield b''
    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        return Message(message_id=100, date=datetime.now(timezone.utc),
                       chat=Chat(id=5, type='private'), text=method.text)

async def run():
    offline = OfflineSession()
    bot = Bot('1:test', session=offline)
    dispatcher = Dispatcher()
    dispatcher.include_router(handlers.analytics_router)
    AnalyticsRepository.available_months = AsyncMock(return_value=[(1, 2027)])
    show = Show(id='event', show_name='Play <foo> & Bar',
                date='2027-01-10 19:00', seats=None)
    report = ReportData([show], insights={
        'event': InventoryInsights(reason='unknown_inventory'),
    })
    AnalyticsRepository.report = AsyncMock(return_value=report)
    state = dispatcher.fsm.get_context(bot, chat_id=5, user_id=5)
    identifier = 0
    async def feed(text):
        nonlocal identifier
        identifier += 1
        message = Message(message_id=identifier, date=datetime.now(timezone.utc),
                          chat=Chat(id=5, type='private'),
                          from_user=User(id=5, is_bot=False, first_name='User'),
                          text=text)
        await dispatcher.feed_update(bot, Update(update_id=identifier, message=message),
                                     session=None)
    try:
        trends = LEXICON_BUTTONS_RU['/report_trends']
        assert trends in [button.text for row in
                          analytics_main_menu_keyboard().keyboard for button in row]
        await feed(trends)
        await feed(LEXICON_BUTTONS_RU['/period_all_time'])
        AnalyticsRepository.report.assert_awaited_once_with('trends', None, None, n=10)
        text = offline.requests[-1].text
        assert 'Play &lt;foo&gt; &amp; Bar' in text
        assert 'Билетов на сайте: <b>пока неизвестно</b>' in text
        assert '10.01.2027 в 19:00' in text
        assert 'неизвестно, сколько билетов осталось' in text
        assert 'Число билетов на сайте меняется не только из-за продаж.' in text
        assert await state.get_state() is None
        await feed('🏆 Топ продаж (спектакли)')
        assert (
            (await state.get_data())['report_type_to_generate']
            == LEXICON_BUTTONS_RU['/report_top_shows_sales']
        )
        await feed('⏳ Прогноз Sold Out')
        assert await state.get_state() == handlers.AnalyticsStates.choosing_month.state
        AnalyticsRepository.report.return_value = ReportData([])
        await feed('Январь 2027')
        assert LEXICON_RU['NO_RELIABLE_FORECAST'] in offline.requests[-1].text
    finally:
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )
