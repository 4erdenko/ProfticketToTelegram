from pathlib import Path

import pytest

from tests.runtime_helpers import run_runtime_script

BOOTSTRAP = r"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from telegram.db.subscriptions import SubscriptionTarget
from telegram.filters import month_filter
from telegram.handlers import analytics_handlers as analytics
from telegram.handlers import personal_handlers as personal
from telegram.handlers import subscription_handlers as handlers
from telegram.handlers import user_handlers as users
from telegram.keyboards.subscription_keyboard import SubscriptionAction
from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU
from telegram.lexicon.subscriptions import LEXICON_SUBSCRIPTIONS
from telegram.utils.startup import setup_dispatcher

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
        if type(method).__name__ == 'AnswerCallbackQuery':
            return True
        return Message(message_id=100, date=datetime.now(timezone.utc),
                       chat=Chat(id=getattr(method, 'chat_id', 5), type='private'),
                       from_user=User(id=999, is_bot=True, first_name='Bot'),
                       text=getattr(method, 'text', None))

async def setup():
    offline = OfflineSession()
    bot = Bot('1:test', session=offline)
    dispatcher = await setup_dispatcher()
    month_filter.get_available_months = AsyncMock(return_value=[])
    users.main_keyboard = AsyncMock(return_value=None)
    analytics.main_keyboard = AsyncMock(return_value=None)
    personal.main_keyboard = AsyncMock(return_value=None)
    records = {}
    targets = {
        'show': SubscriptionTarget('show', 'show:10', 'Гамлет <новый>'),
        'actor': SubscriptionTarget('actor', 'анна мария-смирнова',
                                    'Анна Мария-Смирнова'),
    }
    async def search(session, kind, query, limit=8):
        return [] if query == 'missing' else [targets[kind]]
    async def save(session, owner, target, interval):
        row = SimpleNamespace(id=1, user_id=owner, kind=target.kind,
                              key=target.key, label=target.label,
                              interval_seconds=interval, enabled=True)
        records[row.id] = row
        return row
    async def get(session, owner, identifier):
        row = records.get(identifier)
        return row if row and row.user_id == owner else None
    async def update(session, owner, identifier, **changes):
        row = await get(session, owner, identifier)
        if row:
            for key, value in changes.items():
                setattr(row, key, value)
        return row
    async def delete(session, owner, identifier):
        if await get(session, owner, identifier):
            del records[identifier]
            return True
        return False
    handlers.search_targets = AsyncMock(side_effect=search)
    handlers.save_subscription = AsyncMock(side_effect=save)
    handlers.get_subscription = AsyncMock(side_effect=get)
    handlers.list_subscriptions = AsyncMock(side_effect=lambda session, owner:
        [row for row in records.values() if row.user_id == owner])
    handlers.update_subscription = AsyncMock(side_effect=update)
    handlers.delete_subscription = AsyncMock(side_effect=delete)
    handlers.get_user = AsyncMock(return_value=SimpleNamespace(
        spectacle_full_name='анна мария-смирнова'))
    session = object()
    identifier = 0
    async def feed(text=None, action=None, owner=5, chat_type='private'):
        nonlocal identifier
        identifier += 1
        sender = User(id=owner, is_bot=False, first_name='User')
        message = Message(message_id=identifier, date=datetime.now(timezone.utc),
                          chat=Chat(id=owner, type=chat_type),
                          from_user=sender, text=text)
        if action is not None:
            message = message.model_copy(update={
                'from_user': User(id=999, is_bot=True, first_name='Bot')})
            callback = CallbackQuery(id=str(identifier), from_user=sender,
                                     chat_instance='offline', message=message,
                                     data=action.pack())
            update = Update(update_id=identifier, callback_query=callback)
        else:
            update = Update(update_id=identifier, message=message)
        await dispatcher.feed_update(bot, update, session=session)
    state = dispatcher.fsm.get_context(bot, chat_id=5, user_id=5)
    return bot, dispatcher, offline, state, records, feed
"""


def test_digest_pagination_checks_owner_and_preserves_current_flow(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    async def get_digest(session, owner, identifier):
        if owner == 5 and identifier == 123:
            return SimpleNamespace(id=123, pages=['First <b>page</b>', 'Second page'])
        return None
    handlers.get_digest = AsyncMock(side_effect=get_digest)
    try:
        await state.set_state(handlers.SubscriptionStates.searching)
        await state.update_data(token='active-search', kind='actor')
        original = await state.get_data()
        for page in (1, 0):
            await feed(action=SubscriptionAction(action='digest', reference='123', value=str(page)))
            request = offline.requests[-1]
            assert type(request).__name__ == 'EditMessageText'
            assert request.text == ['First <b>page</b>', 'Second page'][page]
            assert request.parse_mode == 'HTML'
            assert request.link_preview_options.is_disabled
            assert await state.get_state() == handlers.SubscriptionStates.searching.state
            assert await state.get_data() == original
        for reference, value, owner, chat in [
            ('123', '1', 6, 'private'), ('124', '0', 5, 'private'),
            ('123', '2', 5, 'private'), ('123', '-1', 5, 'private'),
            ('bad', '0', 5, 'private'), ('123', '1', 5, 'group'),
        ]:
            before = len(offline.requests)
            await feed(action=SubscriptionAction(action='digest', reference=reference, value=value),
                       owner=owner, chat_type=chat)
            assert len(offline.requests) == before + 1
            assert type(offline.requests[-1]).__name__ == 'AnswerCallbackQuery'
            assert offline.requests[-1].show_alert
        assert await state.get_data() == original
    finally:
        await bot.session.close()
        await dispatcher.storage.close()
asyncio.run(run())
""",
        tmp_path,
    )


def test_maintenance_blocks_subscription_callbacks_without_changing_state(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
from telegram.lexicon.lexicon_ru import LEXICON_RU

async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    records[1] = SimpleNamespace(id=1, user_id=5, kind='show', label='Test',
                                 enabled=True, interval_seconds=1800)
    handlers.get_digest = AsyncMock()
    try:
        await state.set_state(handlers.SubscriptionStates.choosing_interval)
        await state.update_data(token='flow', target={
            'kind': 'show', 'key': 'show:10', 'label': 'Test'})
        original = await state.get_data()
        dispatcher['maintenance_mode'] = True
        for action, reference, value in [
            ('toggle', '1', '0'), ('delete', '1', ''),
            ('interval', '1', '3600'), ('save', 'flow', '1800'),
            ('view', '1', ''), ('digest', '123', '1'),
        ]:
            before = len(offline.requests)
            await feed(action=SubscriptionAction(
                action=action, reference=reference, value=value))
            assert len(offline.requests) == before + 1
            response = offline.requests[-1]
            assert type(response).__name__ == 'AnswerCallbackQuery'
            assert response.text == LEXICON_RU['MAINTENANCE']
            assert response.show_alert
            assert await state.get_data() == original
            assert await state.get_state() == handlers.SubscriptionStates.choosing_interval.state
        for method in (handlers.update_subscription, handlers.delete_subscription,
                       handlers.save_subscription, handlers.get_subscription,
                       handlers.get_digest):
            method.assert_not_awaited()
        assert records[1].enabled
        dispatcher['maintenance_mode'] = False
        await feed(action=SubscriptionAction(action='toggle', reference='1', value='0'))
        handlers.update_subscription.assert_awaited_once()
        assert not records[1].enabled
    finally:
        await bot.session.close()
        await dispatcher.storage.close()
asyncio.run(run())
""",
        tmp_path,
    )


def test_subscription_search_and_management_through_dispatcher(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    try:
        await state.set_state(analytics.AnalyticsStates.choosing_month)
        await state.update_data(old='data')
        await feed(text=LEXICON_BUTTONS_RU['/subscriptions'])
        assert await state.get_state() is None
        data = await state.get_data()
        assert set(data) == {'token'} and isinstance(data['token'], str)
        await feed(action=SubscriptionAction(action='search', reference='show'))
        await feed(text='Гам')
        assert handlers.search_targets.await_args.args[1:] == ('show', 'Гам')
        data = await state.get_data()
        old_choice = SubscriptionAction(action='choose', reference=data['token'], value='0')
        await feed(text='Гамлет')
        data = await state.get_data()
        await feed(action=old_choice)
        assert offline.requests[-1].show_alert
        assert await state.get_state() == handlers.SubscriptionStates.searching.state
        await feed(action=SubscriptionAction(action='choose',
            reference=data['token'], value='0'))
        assert '&lt;новый&gt;' in offline.requests[-1].text
        data = await state.get_data()
        save = SubscriptionAction(action='save', reference=data['token'], value='1800')
        await feed(action=save)
        assert await state.get_state() is None
        assert handlers.save_subscription.await_args.args[1] == 5
        assert records[1].key == 'show:10' and records[1].interval_seconds == 1800
        await feed(action=save)
        assert handlers.save_subscription.await_count == 1
        assert offline.requests[-1].show_alert
        await feed(action=SubscriptionAction(action='toggle', reference='1', value='0'))
        assert not records[1].enabled
        assert LEXICON_SUBSCRIPTIONS['paused'] in offline.requests[-1].text
        await feed(action=SubscriptionAction(action='intervals', reference='1'))
        intervals = [SubscriptionAction.unpack(button.callback_data).value
                     for row in offline.requests[-1].reply_markup.inline_keyboard
                     for button in row if SubscriptionAction.unpack(
                         button.callback_data).action == 'interval']
        assert set(intervals) == {'1800', '3600', '21600', '43200', '86400', '604800'}
        await feed(action=SubscriptionAction(action='interval', reference='1', value='604800'))
        assert records[1].interval_seconds == 604800 and not records[1].enabled
        await feed(action=SubscriptionAction(action='toggle', reference='1', value='1'))
        assert records[1].enabled
        await feed(action=SubscriptionAction(action='delete', reference='1'))
        assert not records
        assert LEXICON_SUBSCRIPTIONS['deleted'] in offline.requests[-1].text
        await feed(action=SubscriptionAction(action='current'))
        data = await state.get_data()
        assert data['target']['key'] == 'анна мария-смирнова'
        assert LEXICON_SUBSCRIPTIONS['actor_disclaimer'] in offline.requests[-1].text
        await feed(text='/start')
        assert await state.get_state() is None
        await feed(action=SubscriptionAction(action='save', reference=data['token'], value='3600'))
        assert handlers.save_subscription.await_count == 1
    finally:
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_subscription_callbacks_require_private_chat_and_owner(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    try:
        records[1] = SimpleNamespace(id=1, user_id=5, kind='show', key='show:10',
                                    label='Гамлет', interval_seconds=86400, enabled=True)
        for action, value in [('view', ''), ('toggle', '0'), ('interval', '3600'), ('delete', '')]:
            await feed(action=SubscriptionAction(action=action, reference='1', value=value), owner=7)
            assert handlers.get_subscription.await_args.args[1:] == (7, 1)
            assert records[1].enabled and records[1].interval_seconds == 86400
        handlers.update_subscription.assert_not_awaited()
        handlers.delete_subscription.assert_not_awaited()
        before = handlers.get_subscription.await_count
        await feed(action=SubscriptionAction(action='delete', reference='1'), chat_type='group')
        assert offline.requests[-1].text == LEXICON_SUBSCRIPTIONS['private_only']
        assert handlers.get_subscription.await_count == before
        await feed(text='/subscriptions', chat_type='group')
        assert offline.requests[-1].text == LEXICON_SUBSCRIPTIONS['private_only']
        await state.set_state(personal.ChooseYourFighter.set_your_fighter)
        await feed(text='/subscriptions')
        assert await state.get_state() is None
        await feed(action=SubscriptionAction(action='search', reference='actor'))
        await feed(text='missing')
        assert LEXICON_SUBSCRIPTIONS['search_empty'] == offline.requests[-1].text
        await feed(text='Анна')
        assert handlers.search_targets.await_args.args[1:] == ('actor', 'Анна')
        await feed(text=LEXICON_BUTTONS_RU['/back_to_main_menu'])
        assert await state.get_state() is None
        owner_ids = []
        async def keyboard(message, session):
            owner_ids.append(message.from_user.id)
            return None
        handlers.main_keyboard = keyboard
        await feed(action=SubscriptionAction(action='main'))
        assert owner_ids == [5]
    finally:
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_old_analytics_buttons_escape_actor_name_input(tmp_path: Path) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
from telegram.lexicon.lexicon_ru import LEGACY_ANALYTICS_BUTTONS

async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    analytics.AnalyticsRepository.available_months = AsyncMock(
        return_value=[(1, 2027)])
    personal.set_spectacle_fio = AsyncMock()
    try:
        for text, command in LEGACY_ANALYTICS_BUTTONS.items():
            await feed(text='/set_actor')
            assert await state.get_state() == personal.ChooseYourFighter.set_your_fighter.state
            await feed(text=text)
            expected_state = (
                analytics.AnalyticsStates.choosing_month
                if command == '/report_predict_sell_out'
                else analytics.AnalyticsStates.choosing_month_for_top
            )
            assert await state.get_state() == expected_state.state
            assert (await state.get_data())['report_type_to_generate'] == LEXICON_BUTTONS_RU[command]
        personal.set_spectacle_fio.assert_not_awaited()
        assert analytics.AnalyticsRepository.available_months.await_count == len(LEGACY_ANALYTICS_BUTTONS)
    finally:
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize('save_fails', [False, True])
@pytest.mark.parametrize('navigation', ['search', 'menu'])
def test_delayed_subscription_save_preserves_new_flow(
    tmp_path: Path, save_fails: bool, navigation: str
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nSAVE_FAILS = {save_fails!r}\nNAVIGATION = {navigation!r}\n'
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    started, finish = asyncio.Event(), asyncio.Event()
    original_save = handlers.save_subscription.side_effect
    async def delayed_save(*args):
        started.set()
        await finish.wait()
        if SAVE_FAILS:
            raise ValueError('Target removed')
        return await original_save(*args)
    handlers.save_subscription = AsyncMock(side_effect=delayed_save)
    pending = None
    try:
        await feed(action=SubscriptionAction(action='current'))
        data = await state.get_data()
        pending = asyncio.create_task(feed(action=SubscriptionAction(
            action='save', reference=data['token'], value='3600')))
        await started.wait()
        await feed(action=SubscriptionAction(action='menu'))
        if NAVIGATION == 'search':
            await feed(action=SubscriptionAction(action='search', reference='actor'))
        expected_state = await state.get_state()
        expected_data = await state.get_data()
        request_count = len(offline.requests)
        finish.set()
        await pending
        assert await state.get_state() == expected_state
        assert await state.get_data() == expected_data
        assert len(offline.requests) == request_count
        assert bool(records) is not SAVE_FAILS
        if NAVIGATION == 'search':
            before = handlers.search_targets.await_count
            await feed(text='Анна')
            assert handlers.search_targets.await_count == before + 1
            assert handlers.search_targets.await_args.args[1:] == ('actor', 'Анна')
            assert offline.requests[-1].text == LEXICON_SUBSCRIPTIONS['search_results']
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize('navigation', ['actor', 'show', 'menu', 'choose'])
def test_delayed_subscription_search_preserves_new_flow(
    tmp_path: Path, navigation: str
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nNAVIGATION = {navigation!r}\n'
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    started, finish = asyncio.Event(), asyncio.Event()
    original_search = handlers.search_targets.side_effect
    async def delayed_search(session, kind, query, limit=8):
        if query == 'Гам':
            started.set()
            await finish.wait()
            return [SubscriptionTarget('show', 'show:old', 'Old result')]
        return await original_search(session, kind, query, limit)
    handlers.search_targets = AsyncMock(side_effect=delayed_search)
    pending = None
    try:
        await feed(action=SubscriptionAction(action='search', reference='show'))
        pending = asyncio.create_task(feed(text='Гам'))
        await started.wait()
        if NAVIGATION == 'menu':
            await feed(action=SubscriptionAction(action='menu'))
        elif NAVIGATION == 'show':
            await feed(text='Гамлет')
        else:
            await feed(action=SubscriptionAction(action='search', reference='actor'))
            await feed(text='Анна')
            if NAVIGATION == 'choose':
                data = await state.get_data()
                await feed(action=SubscriptionAction(
                    action='choose', reference=data['token'], value='0'))
        expected_state = await state.get_state()
        expected_data = await state.get_data()
        request_count = len(offline.requests)
        finish.set()
        await pending
        assert await state.get_state() == expected_state
        assert await state.get_data() == expected_data
        assert len(offline.requests) == request_count
        if NAVIGATION in {'actor', 'show'}:
            await feed(action=SubscriptionAction(
                action='choose', reference=expected_data['token'], value='0'))
            assert await state.get_state() == handlers.SubscriptionStates.choosing_interval.state
            target = (await state.get_data())['target']
            assert target['key'] != 'show:old'
            assert target['kind'] == NAVIGATION
        elif NAVIGATION == 'choose':
            await feed(action=SubscriptionAction(
                action='save', reference=expected_data['token'], value='3600'))
            assert records[1].kind == 'actor'
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize('delayed_lookup', ['user', 'targets'])
@pytest.mark.parametrize('navigation', ['menu', 'choose'])
def test_delayed_current_actor_lookup_preserves_new_flow(
    tmp_path: Path, delayed_lookup: str, navigation: str
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nDELAYED_LOOKUP = {delayed_lookup!r}\nNAVIGATION = {navigation!r}\n'
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    started, finish = asyncio.Event(), asyncio.Event()
    if DELAYED_LOOKUP == 'user':
        original_user = handlers.get_user.return_value
        async def delayed_user(*args):
            started.set()
            await finish.wait()
            return original_user
        handlers.get_user = AsyncMock(side_effect=delayed_user)
    else:
        original_search = handlers.search_targets.side_effect
        async def delayed_search(session, kind, query, limit=8):
            if kind == 'actor':
                started.set()
                await finish.wait()
            return await original_search(session, kind, query, limit)
        handlers.search_targets = AsyncMock(side_effect=delayed_search)
    pending = None
    try:
        pending = asyncio.create_task(feed(action=SubscriptionAction(action='current')))
        await started.wait()
        if NAVIGATION == 'menu':
            handlers.get_user = AsyncMock(return_value=None)
            await feed(action=SubscriptionAction(action='menu'))
        else:
            await feed(action=SubscriptionAction(action='search', reference='show'))
            await feed(text='Гамлет')
            data = await state.get_data()
            await feed(action=SubscriptionAction(
                action='choose', reference=data['token'], value='0'))
        expected_state = await state.get_state()
        expected_data = await state.get_data()
        request_count = len(offline.requests)
        finish.set()
        await pending
        assert await state.get_state() == expected_state
        assert await state.get_data() == expected_data
        assert len(offline.requests) == request_count
        if NAVIGATION == 'choose':
            await feed(action=SubscriptionAction(
                action='save', reference=expected_data['token'], value='3600'))
            assert records[1].kind == 'show'
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_new_search_invalidates_choices_before_lookup(tmp_path: Path) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    started, finish = asyncio.Event(), asyncio.Event()
    original_search = handlers.search_targets.side_effect
    async def delayed_search(session, kind, query, limit=8):
        if query == 'Гамлет':
            started.set()
            await finish.wait()
        return await original_search(session, kind, query, limit)
    handlers.search_targets = AsyncMock(side_effect=delayed_search)
    pending = None
    try:
        await feed(action=SubscriptionAction(action='search', reference='show'))
        await feed(text='Гам')
        old_token = (await state.get_data())['token']
        pending = asyncio.create_task(feed(text='Гамлет'))
        await started.wait()
        data = await state.get_data()
        assert data['token'] != old_token
        assert data['choices'] == []
        await feed(action=SubscriptionAction(
            action='choose', reference=old_token, value='0'))
        assert offline.requests[-1].show_alert
        assert await state.get_state() == handlers.SubscriptionStates.searching.state
        finish.set()
        await pending
        data = await state.get_data()
        await feed(action=SubscriptionAction(
            action='choose', reference=data['token'], value='0'))
        assert await state.get_state() == handlers.SubscriptionStates.choosing_interval.state
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize(
    ('action', 'value'),
    [
        ('view', ''),
        ('intervals', ''),
        ('toggle', '0'),
        ('interval', '3600'),
        ('delete', ''),
    ],
)
def test_delayed_subscription_lookup_preserves_new_search(
    tmp_path: Path, action: str, value: str
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nACTION = {action!r}\nVALUE = {value!r}\n'
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    records[1] = SimpleNamespace(id=1, user_id=5, kind='show', key='show:10',
                                label='Гамлет', interval_seconds=86400, enabled=True)
    started, finish = asyncio.Event(), asyncio.Event()
    original_get = handlers.get_subscription.side_effect
    async def delayed_get(*args):
        started.set()
        await finish.wait()
        return await original_get(*args)
    handlers.get_subscription = AsyncMock(side_effect=delayed_get)
    pending = None
    try:
        pending = asyncio.create_task(feed(action=SubscriptionAction(
            action=ACTION, reference='1', value=VALUE)))
        await started.wait()
        await feed(action=SubscriptionAction(action='menu'))
        await feed(action=SubscriptionAction(action='search', reference='actor'))
        expected_state = await state.get_state()
        expected_data = await state.get_data()
        request_count = len(offline.requests)
        finish.set()
        await pending
        assert await state.get_state() == expected_state
        assert await state.get_data() == expected_data
        assert len(offline.requests) == request_count
        handlers.update_subscription.assert_not_awaited()
        handlers.delete_subscription.assert_not_awaited()
        await feed(text='Анна')
        assert handlers.search_targets.await_args.args[1:] == ('actor', 'Анна')
        assert offline.requests[-1].text == LEXICON_SUBSCRIPTIONS['search_results']
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize(
    ('action', 'value'),
    [('toggle', '0'), ('interval', '3600'), ('delete', '')],
)
def test_started_subscription_write_finishes_without_replacing_new_search(
    tmp_path: Path, action: str, value: str
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nACTION = {action!r}\nVALUE = {value!r}\n'
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    records[1] = SimpleNamespace(id=1, user_id=5, kind='show', key='show:10',
                                label='Гамлет', interval_seconds=86400, enabled=True)
    started, finish = asyncio.Event(), asyncio.Event()
    original_write = (handlers.delete_subscription.side_effect if ACTION == 'delete'
                      else handlers.update_subscription.side_effect)
    async def delayed_write(*args, **kwargs):
        started.set()
        await finish.wait()
        return await original_write(*args, **kwargs)
    if ACTION == 'delete':
        handlers.delete_subscription = AsyncMock(side_effect=delayed_write)
    else:
        handlers.update_subscription = AsyncMock(side_effect=delayed_write)
    pending = None
    try:
        pending = asyncio.create_task(feed(action=SubscriptionAction(
            action=ACTION, reference='1', value=VALUE)))
        await started.wait()
        await feed(action=SubscriptionAction(action='menu'))
        await feed(action=SubscriptionAction(action='search', reference='actor'))
        expected_state = await state.get_state()
        expected_data = await state.get_data()
        request_count = len(offline.requests)
        finish.set()
        await pending
        assert await state.get_state() == expected_state
        assert await state.get_data() == expected_data
        assert len(offline.requests) == request_count
        if ACTION == 'delete':
            assert not records
        elif ACTION == 'toggle':
            assert not records[1].enabled
        else:
            assert records[1].interval_seconds == 3600
        await feed(text='Анна')
        assert handlers.search_targets.await_args.args[1:] == ('actor', 'Анна')
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize(
    'screen', ['menu', 'list', 'missing', 'empty_list', 'command']
)
def test_delayed_subscription_screen_preserves_new_search(
    tmp_path: Path, screen: str
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nSCREEN = {screen!r}\n'
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    if SCREEN != 'empty_list':
        records[1] = SimpleNamespace(id=1, user_id=5, kind='show', key='show:10',
                                    label='Гамлет', interval_seconds=86400, enabled=True)
    started, finish = asyncio.Event(), asyncio.Event()
    if SCREEN in {'list', 'missing'}:
        original_list = handlers.list_subscriptions.side_effect
        async def delayed_list(*args):
            started.set()
            await finish.wait()
            return original_list(*args)
        handlers.list_subscriptions = AsyncMock(side_effect=delayed_list)
    else:
        original_user = handlers.get_user.return_value
        async def delayed_user(*args):
            started.set()
            await finish.wait()
            return original_user
        handlers.get_user = AsyncMock(side_effect=delayed_user)
    pending = None
    try:
        if SCREEN == 'command':
            pending = asyncio.create_task(feed(text='/subscriptions'))
        else:
            action = SubscriptionAction(
                action='view', reference='9') if SCREEN == 'missing' else SubscriptionAction(
                    action='list' if SCREEN in {'list', 'empty_list'} else 'menu')
            pending = asyncio.create_task(feed(action=action))
        await started.wait()
        await feed(action=SubscriptionAction(action='search', reference='actor'))
        expected_state = await state.get_state()
        expected_data = await state.get_data()
        request_count = len(offline.requests)
        finish.set()
        await pending
        assert await state.get_state() == expected_state
        assert await state.get_data() == expected_data
        assert len(offline.requests) == request_count
        await feed(text='Анна')
        assert handlers.search_targets.await_args.args[1:] == ('actor', 'Анна')
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_delayed_subscription_card_does_not_replace_newer_card(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    for identifier, label in [(1, 'Hamlet'), (2, 'Macbeth')]:
        records[identifier] = SimpleNamespace(
            id=identifier, user_id=5, kind='show', key=f'show:{identifier}',
            label=label, interval_seconds=86400, enabled=True)
    started, finish = asyncio.Event(), asyncio.Event()
    original_get = handlers.get_subscription.side_effect
    async def delayed_get(session, owner, identifier):
        if identifier == 1:
            started.set()
            await finish.wait()
        return await original_get(session, owner, identifier)
    handlers.get_subscription = AsyncMock(side_effect=delayed_get)
    pending = None
    try:
        pending = asyncio.create_task(feed(action=SubscriptionAction(
            action='view', reference='1')))
        await started.wait()
        await feed(action=SubscriptionAction(action='view', reference='2'))
        assert await state.get_state() is None
        assert 'Macbeth' in offline.requests[-1].text
        request_count = len(offline.requests)
        finish.set()
        await pending
        assert await state.get_state() is None
        assert len(offline.requests) == request_count
        assert 'Macbeth' in offline.requests[-1].text
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_delayed_subscription_acknowledgement_preserves_new_search(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    records[1] = SimpleNamespace(id=1, user_id=5, kind='show', key='show:10',
                                label='Гамлет', interval_seconds=86400, enabled=True)
    started, finish = asyncio.Event(), asyncio.Event()
    original_request = offline.make_request
    first_acknowledgement = True
    async def delayed_request(bot, method, timeout=None):
        nonlocal first_acknowledgement
        if type(method).__name__ == 'AnswerCallbackQuery' and first_acknowledgement:
            first_acknowledgement = False
            started.set()
            await finish.wait()
        return await original_request(bot, method, timeout)
    offline.make_request = delayed_request
    pending = None
    try:
        pending = asyncio.create_task(feed(action=SubscriptionAction(
            action='view', reference='1')))
        await started.wait()
        await feed(action=SubscriptionAction(action='search', reference='actor'))
        expected_state = await state.get_state()
        expected_data = await state.get_data()
        finish.set()
        await pending
        assert await state.get_state() == expected_state
        assert await state.get_data() == expected_data
        handlers.get_subscription.assert_not_awaited()
        screen_texts = [request.text for request in offline.requests
                        if type(request).__name__ in {'SendMessage', 'EditMessageText'}]
        assert screen_texts == [LEXICON_SUBSCRIPTIONS['search_actor']]
        await feed(text='Анна')
        assert handlers.search_targets.await_args.args[1:] == ('actor', 'Анна')
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize('first_finished', ['old', 'new'])
def test_overlapping_subscription_acknowledgements_show_newest_card(
    tmp_path: Path, first_finished: str
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nFIRST_FINISHED = {first_finished!r}\n'
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    for identifier, label in [(1, 'Hamlet'), (2, 'Macbeth')]:
        records[identifier] = SimpleNamespace(
            id=identifier, user_id=5, kind='show', key=f'show:{identifier}',
            label=label, interval_seconds=86400, enabled=True)
    started = {name: asyncio.Event() for name in ['old', 'new']}
    finish = {name: asyncio.Event() for name in ['old', 'new']}
    original_request = offline.make_request
    async def delayed_request(bot, method, timeout=None):
        if type(method).__name__ == 'AnswerCallbackQuery':
            name = 'old' if method.callback_query_id == '1' else 'new'
            started[name].set()
            await finish[name].wait()
        return await original_request(bot, method, timeout)
    offline.make_request = delayed_request
    pending = {}
    try:
        pending['old'] = asyncio.create_task(feed(action=SubscriptionAction(
            action='view', reference='1')))
        await started['old'].wait()
        pending['new'] = asyncio.create_task(feed(action=SubscriptionAction(
            action='view', reference='2')))
        await started['new'].wait()
        finish[FIRST_FINISHED].set()
        await pending[FIRST_FINISHED]
        other = 'new' if FIRST_FINISHED == 'old' else 'old'
        finish[other].set()
        await pending[other]
        assert await state.get_state() is None
        handlers.get_subscription.assert_awaited_once()
        assert handlers.get_subscription.await_args.args[1:] == (5, 2)
        screens = [request.text for request in offline.requests
                   if type(request).__name__ == 'EditMessageText']
        assert len(screens) == 1 and 'Macbeth' in screens[0]
    finally:
        for event in finish.values():
            event.set()
        await asyncio.gather(*pending.values())
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_duplicate_main_callbacks_send_newest_menu_once(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
from aiogram.exceptions import TelegramBadRequest

async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    started, finish = asyncio.Event(), asyncio.Event()
    original_request = offline.make_request
    removed_messages = set()
    async def remove_markup(bot, method, timeout=None):
        if type(method).__name__ == 'EditMessageReplyMarkup':
            key = (method.chat_id, method.message_id)
            if key in removed_messages:
                raise TelegramBadRequest(method=method,
                    message='Bad Request: message is not modified')
            removed_messages.add(key)
        return await original_request(bot, method, timeout)
    offline.make_request = remove_markup
    first_keyboard = True
    async def keyboard(*args):
        nonlocal first_keyboard
        if first_keyboard:
            first_keyboard = False
            started.set()
            await finish.wait()
        return None
    handlers.main_keyboard = AsyncMock(side_effect=keyboard)
    sender = User(id=5, is_bot=False, first_name='User')
    message = Message(message_id=77, date=datetime.now(timezone.utc),
                      chat=Chat(id=5, type='private'),
                      from_user=User(id=999, is_bot=True, first_name='Bot'))
    async def click(identifier):
        callback = CallbackQuery(id=str(identifier), from_user=sender,
                                 chat_instance='offline', message=message,
                                 data=SubscriptionAction(action='main').pack())
        await dispatcher.feed_update(bot,
            Update(update_id=identifier, callback_query=callback), session=object())
    pending = None
    try:
        pending = asyncio.create_task(click(1))
        await started.wait()
        old_token = (await state.get_data())['token']
        await click(2)
        expected_data = await state.get_data()
        assert expected_data['token'] != old_token
        finish.set()
        await pending
        menus = [request for request in offline.requests
                 if type(request).__name__ == 'SendMessage'
                 and request.text == handlers.LEXICON_RU['MAIN_MENU']]
        assert len(menus) == 1
        assert removed_messages == {(5, 77)}
        assert handlers.main_keyboard.await_count == 2
        assert await state.get_state() is None
        assert await state.get_data() == expected_data
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_main_callback_propagates_other_markup_errors(tmp_path: Path) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
from aiogram.exceptions import TelegramBadRequest

async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    original_request = offline.make_request
    async def fail_markup(bot, method, timeout=None):
        if type(method).__name__ == 'EditMessageReplyMarkup':
            raise TelegramBadRequest(method=method,
                message='Bad Request: message cannot be edited')
        return await original_request(bot, method, timeout)
    offline.make_request = fail_markup
    handlers.main_keyboard = AsyncMock(return_value=None)
    try:
        try:
            await feed(action=SubscriptionAction(action='main'))
        except TelegramBadRequest as error:
            assert 'message cannot be edited' in str(error)
        else:
            raise AssertionError('Unexpected Telegram error was swallowed')
        handlers.main_keyboard.assert_not_awaited()
        assert not any(type(request).__name__ == 'SendMessage'
                       for request in offline.requests)
    finally:
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize('delay', ['ack', 'store'])
def test_subscription_frequency_is_saved_once_per_selection(
    tmp_path: Path, delay: str
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nDELAY = {delay!r}\n'
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    started, finish = asyncio.Event(), asyncio.Event()
    original_save = handlers.save_subscription.side_effect
    original_request = offline.make_request
    first_ack = True
    async def delayed_ack(bot, method, timeout=None):
        nonlocal first_ack
        if type(method).__name__ == 'AnswerCallbackQuery' and first_ack:
            first_ack = False
            started.set()
            await finish.wait()
        return await original_request(bot, method, timeout)
    async def delayed_save(*args):
        if args[-1] == 1800 and DELAY == 'store':
            started.set()
            await finish.wait()
        return await original_save(*args)
    handlers.save_subscription = AsyncMock(side_effect=delayed_save)
    pending = None
    try:
        await feed(action=SubscriptionAction(action='current'))
        token = (await state.get_data())['token']
        if DELAY == 'ack':
            offline.make_request = delayed_ack
        pending = asyncio.create_task(feed(action=SubscriptionAction(
            action='save', reference=token, value='1800')))
        await started.wait()
        for interval in ('3600', '1800'):
            await feed(action=SubscriptionAction(
                action='save', reference=token, value=interval))
            assert offline.requests[-1].text == LEXICON_SUBSCRIPTIONS['stale']
            assert offline.requests[-1].show_alert is True
        assert handlers.save_subscription.await_count == (DELAY == 'store')
        finish.set()
        await pending
        handlers.save_subscription.assert_awaited_once()
        assert records[1].interval_seconds == 1800
        cards = [request.text for request in offline.requests
                 if type(request).__name__ == 'EditMessageText'
                 and LEXICON_SUBSCRIPTIONS['created'] in request.text]
        assert len(cards) == 1
        assert 'раз в 30 минут' in cards[0]
        assert await state.get_state() is None
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize('interval', ['invalid', '300'])
def test_invalid_subscription_frequency_preserves_selection(
    tmp_path: Path, interval: str
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nINTERVAL = {interval!r}\n'
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    try:
        await feed(action=SubscriptionAction(action='current'))
        data = await state.get_data()
        await feed(action=SubscriptionAction(
            action='save', reference=data['token'], value=INTERVAL))
        handlers.save_subscription.assert_not_awaited()
        assert await state.get_state() == handlers.SubscriptionStates.choosing_interval.state
        assert await state.get_data() == data
        await feed(action=SubscriptionAction(
            action='save', reference=data['token'], value='3600'))
        handlers.save_subscription.assert_awaited_once()
        assert records[1].interval_seconds == 3600
        assert await state.get_state() is None
    finally:
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_claimed_subscription_save_failure_returns_to_menu(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    handlers.save_subscription = AsyncMock(side_effect=ValueError('Target removed'))
    try:
        await feed(action=SubscriptionAction(action='current'))
        token = (await state.get_data())['token']
        await feed(action=SubscriptionAction(
            action='save', reference=token, value='3600'))
        handlers.save_subscription.assert_awaited_once()
        assert not records
        assert offline.requests[-1].text == LEXICON_SUBSCRIPTIONS['target_missing']
        assert await state.get_state() is None
        assert (await state.get_data())['token'] != token
    finally:
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_pending_subscription_save_acknowledgement_preserves_new_search(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + r"""
async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    started, finish = asyncio.Event(), asyncio.Event()
    original_request = offline.make_request
    first_ack = True
    async def delayed_ack(bot, method, timeout=None):
        nonlocal first_ack
        if type(method).__name__ == 'AnswerCallbackQuery' and first_ack:
            first_ack = False
            started.set()
            await finish.wait()
        return await original_request(bot, method, timeout)
    pending = None
    try:
        await feed(action=SubscriptionAction(action='current'))
        token = (await state.get_data())['token']
        offline.make_request = delayed_ack
        pending = asyncio.create_task(feed(action=SubscriptionAction(
            action='save', reference=token, value='3600')))
        await started.wait()
        await feed(action=SubscriptionAction(action='search', reference='show'))
        expected_data = await state.get_data()
        request_count = len(offline.requests)
        finish.set()
        await pending
        handlers.save_subscription.assert_not_awaited()
        assert not records
        assert await state.get_state() == handlers.SubscriptionStates.searching.state
        assert await state.get_data() == expected_data
        assert len(offline.requests) == request_count + 1
        assert type(offline.requests[-1]).__name__ == 'AnswerCallbackQuery'
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize('stage', ['ack', 'store'])
@pytest.mark.parametrize('new_search', [False, True])
def test_subscription_save_failure_preserves_retry_or_new_search(
    tmp_path: Path, stage: str, new_search: bool
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nSTAGE = {stage!r}\nNEW_SEARCH = {new_search!r}\n'
        + r"""
from aiogram.exceptions import TelegramNetworkError
from sqlalchemy.exc import OperationalError

async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    started, finish = asyncio.Event(), asyncio.Event()
    original_save = handlers.save_subscription.side_effect
    original_request = offline.make_request
    first_failure = True
    async def fail_ack(bot, method, timeout=None):
        nonlocal first_failure
        if type(method).__name__ == 'AnswerCallbackQuery' and first_failure:
            first_failure = False
            started.set()
            await finish.wait()
            raise TelegramNetworkError(method=method, message='Connection lost')
        return await original_request(bot, method, timeout)
    async def fail_save(*args):
        nonlocal first_failure
        if first_failure:
            first_failure = False
            started.set()
            await finish.wait()
            raise OperationalError('SELECT', {}, Exception('Connection lost'))
        return await original_save(*args)
    expected_error = TelegramNetworkError if STAGE == 'ack' else OperationalError
    pending = None
    try:
        await feed(action=SubscriptionAction(action='current'))
        token = (await state.get_data())['token']
        action = SubscriptionAction(action='save', reference=token, value='3600')
        if STAGE == 'ack':
            offline.make_request = fail_ack
        else:
            handlers.save_subscription = AsyncMock(side_effect=fail_save)
        pending = asyncio.create_task(feed(action=action))
        await started.wait()
        if NEW_SEARCH:
            await feed(action=SubscriptionAction(action='search', reference='show'))
            expected_data = await state.get_data()
        finish.set()
        try:
            await pending
        except expected_error:
            pass
        else:
            raise AssertionError('Transient failure was swallowed')
        pending = None
        assert not records
        if NEW_SEARCH:
            assert await state.get_state() == handlers.SubscriptionStates.searching.state
            assert await state.get_data() == expected_data
            await feed(action=action)
            assert offline.requests[-1].text == LEXICON_SUBSCRIPTIONS['stale']
            assert handlers.save_subscription.await_count == (STAGE == 'store')
            await feed(text='Гамлет')
            assert offline.requests[-1].text == LEXICON_SUBSCRIPTIONS['search_results']
        else:
            assert await state.get_state() == handlers.SubscriptionStates.choosing_interval.state
            assert (await state.get_data())['token'] == token
            await feed(action=action)
            assert handlers.save_subscription.await_count == (2 if STAGE == 'store' else 1)
            assert records[1].interval_seconds == 3600
            assert 'раз в час' in offline.requests[-1].text
            assert LEXICON_SUBSCRIPTIONS['created'] in offline.requests[-1].text
            assert await state.get_state() is None
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


@pytest.mark.parametrize('new_search', [False, True])
def test_subscription_save_menu_failure_preserves_retry_or_new_search(
    tmp_path: Path, new_search: bool
) -> None:
    run_runtime_script(
        BOOTSTRAP
        + f'\nNEW_SEARCH = {new_search!r}\n'
        + r"""
from sqlalchemy.exc import OperationalError

async def run():
    bot, dispatcher, offline, state, records, feed = await setup()
    started, finish = asyncio.Event(), asyncio.Event()
    original_save = handlers.save_subscription.side_effect
    first_save = True
    async def target_missing(*args):
        nonlocal first_save
        if first_save:
            first_save = False
            raise ValueError('Target removed')
        return await original_save(*args)
    async def fail_menu(*args):
        started.set()
        await finish.wait()
        raise OperationalError('SELECT', {}, Exception('Connection lost'))
    pending = None
    try:
        await feed(action=SubscriptionAction(action='current'))
        token = (await state.get_data())['token']
        action = SubscriptionAction(action='save', reference=token, value='3600')
        handlers.save_subscription = AsyncMock(side_effect=target_missing)
        handlers.get_user = AsyncMock(side_effect=fail_menu)
        pending = asyncio.create_task(feed(action=action))
        await started.wait()
        if NEW_SEARCH:
            await feed(action=SubscriptionAction(action='search', reference='show'))
            expected_data = await state.get_data()
        finish.set()
        try:
            await pending
        except OperationalError:
            pass
        else:
            raise AssertionError('Menu lookup failure was swallowed')
        pending = None
        assert not records
        if NEW_SEARCH:
            assert await state.get_state() == handlers.SubscriptionStates.searching.state
            assert await state.get_data() == expected_data
            await feed(action=action)
            assert offline.requests[-1].text == LEXICON_SUBSCRIPTIONS['stale']
            handlers.save_subscription.assert_awaited_once()
            await feed(text='Гамлет')
            assert offline.requests[-1].text == LEXICON_SUBSCRIPTIONS['search_results']
        else:
            assert await state.get_state() == handlers.SubscriptionStates.choosing_interval.state
            assert (await state.get_data())['token'] == token
            await feed(action=action)
            assert handlers.save_subscription.await_count == 2
            assert records[1].interval_seconds == 3600
            assert 'раз в час' in offline.requests[-1].text
            assert LEXICON_SUBSCRIPTIONS['created'] in offline.requests[-1].text
            assert await state.get_state() is None
    finally:
        finish.set()
        if pending is not None:
            await pending
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )
