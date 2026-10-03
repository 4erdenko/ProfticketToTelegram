import secrets
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db.models import Subscription
from telegram.db.subscriptions import (
    SubscriptionTarget,
    delete_subscription,
    get_digest,
    get_subscription,
    list_subscriptions,
    save_subscription,
    search_targets,
    update_subscription,
)
from telegram.db.user_operations import get_user
from telegram.keyboards.main_keyboard import main_keyboard
from telegram.keyboards.subscription_keyboard import (
    SubscriptionAction,
    subscription_back_keyboard,
    subscription_card_keyboard,
    subscription_digest_keyboard,
    subscription_intervals_keyboard,
    subscription_list_keyboard,
    subscription_menu_keyboard,
    subscription_results_keyboard,
)
from telegram.lexicon.lexicon_ru import (
    LEGACY_ANALYTICS_BUTTONS,
    LEXICON_BUTTONS_RU,
    LEXICON_MONTHS_RU,
    LEXICON_RU,
)
from telegram.lexicon.subscriptions import (
    INTERVAL_LABELS,
    LEXICON_SUBSCRIPTIONS,
)
from telegram.tg_utils import normalize_actor_name

subscription_router = Router(name=__name__)
MANAGEMENT_ACTIONS = {'view', 'intervals', 'interval', 'toggle', 'delete'}
NAVIGATION = {
    *LEGACY_ANALYTICS_BUTTONS,
    *LEXICON_BUTTONS_RU.values(),
    *LEXICON_MONTHS_RU.values(),
    '↩️',
    'Этот',
    'Следующий',
    'Назад',
    'Этот месяц',
    'Следующий месяц',
    'Выбрать актёра/актрису',
}
SEARCH_INPUT = (
    F.text
    & ~F.text.startswith('/')
    & ~F.text.startswith(LEXICON_BUTTONS_RU['/shows_with'])
    & ~F.text.startswith('👤 ')
    & ~F.text.in_(NAVIGATION)
)


class SubscriptionStates(StatesGroup):
    searching = State()
    choosing_interval = State()


def _target_title(kind: str, label: str) -> str:
    icon = '🎭' if kind == 'show' else '👤'
    label = label if len(label) <= 160 else label[:157] + '…'
    return f'{icon} <b>{escape(label)}</b>'


async def _edit(
    message: Message, text: str, keyboard: InlineKeyboardMarkup
) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if 'message is not modified' not in str(error).lower():
            raise


async def _menu(session: AsyncSession, user_id: int) -> InlineKeyboardMarkup:
    user = await get_user(session, user_id)
    actor = user.spectacle_full_name if user else None
    return subscription_menu_keyboard(actor.title() if actor else None)


async def _start_flow(state: FSMContext, expected: State | None = None) -> str:
    token = secrets.token_hex(4)
    await state.clear()
    if expected is not None:
        await state.set_state(expected)
    await state.update_data(token=token)
    return token


async def _start_search(state: FSMContext, kind: str) -> str:
    token = await _start_flow(state, SubscriptionStates.searching)
    await state.update_data(kind=kind, choices=[])
    return token


async def _is_current_flow(
    state: FSMContext, expected: State | str | None, token: str | None
) -> bool:
    expected_state = (
        expected.state if isinstance(expected, State) else expected
    )
    return (
        await state.get_state() == expected_state
        and (await state.get_data()).get('token') == token
    )


async def _restore_save_selection(
    state: FSMContext, token: str | None, reference: str
) -> None:
    if await _is_current_flow(
        state, SubscriptionStates.choosing_interval, token
    ):
        await state.update_data(token=reference)


async def _choose_target(
    message: Message, state: FSMContext, target: SubscriptionTarget
) -> None:
    token = secrets.token_hex(4)
    await state.set_state(SubscriptionStates.choosing_interval)
    await state.update_data(
        token=token,
        target={'kind': target.kind, 'key': target.key, 'label': target.label},
    )
    text = _target_title(target.kind, target.label)
    text += '\n\n' + LEXICON_SUBSCRIPTIONS['choose_interval']
    if target.kind == 'actor':
        text += '\n\n' + LEXICON_SUBSCRIPTIONS['actor_disclaimer']
    await _edit(
        message,
        text,
        subscription_intervals_keyboard(token, creating=True),
    )


async def _card(
    message: Message, subscription: Subscription, notice: str = ''
) -> None:
    text = _target_title(subscription.kind, subscription.label)
    status = 'enabled' if subscription.enabled else 'paused'
    text += '\n\n' + LEXICON_SUBSCRIPTIONS[status]
    text += '\n' + LEXICON_SUBSCRIPTIONS['interval'].format(
        interval=INTERVAL_LABELS[subscription.interval_seconds].lower()
    )
    text += '\n\n' + LEXICON_SUBSCRIPTIONS['notification_note']
    if subscription.kind == 'actor':
        text += '\n\n' + LEXICON_SUBSCRIPTIONS['actor_disclaimer']
    if notice:
        text += '\n\n' + notice
    await _edit(
        message,
        text,
        subscription_card_keyboard(
            subscription.id, enabled=subscription.enabled
        ),
    )


async def _list(
    message: Message,
    session: AsyncSession,
    user_id: int,
    state: FSMContext,
    token: str,
    page: int = 0,
    notice: str = '',
) -> None:
    subscriptions = await list_subscriptions(session, user_id)
    if not await _is_current_flow(state, None, token):
        return
    text = LEXICON_SUBSCRIPTIONS['list' if subscriptions else 'empty']
    if notice:
        text = notice + '\n\n' + text
    keyboard = (
        subscription_list_keyboard(subscriptions, page)
        if subscriptions
        else await _menu(session, user_id)
    )
    if not await _is_current_flow(state, None, token):
        return
    await _edit(message, text, keyboard)


@subscription_router.message(
    or_f(
        Command('subscriptions'),
        F.text == LEXICON_BUTTONS_RU['/subscriptions'],
    )
)
async def cmd_subscriptions(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if message.chat.type != 'private':
        await message.answer(LEXICON_SUBSCRIPTIONS['private_only'])
        return
    token = await _start_flow(state)
    keyboard = await _menu(session, message.from_user.id)
    if not await _is_current_flow(state, None, token):
        return
    await message.answer(
        LEXICON_SUBSCRIPTIONS['menu'],
        reply_markup=keyboard,
    )


@subscription_router.message(SubscriptionStates.searching, SEARCH_INPUT)
async def cmd_search_subscription(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if message.chat.type != 'private':
        return
    query = message.text.strip()
    if len(query) < 2 or len(query) > 100:
        key = 'search_short' if len(query) < 2 else 'search_long'
        await message.answer(LEXICON_SUBSCRIPTIONS[key])
        return
    data = await state.get_data()
    token = secrets.token_hex(4)
    await state.update_data(token=token, choices=[])
    targets = await search_targets(session, data['kind'], query, limit=8)
    if not await _is_current_flow(state, SubscriptionStates.searching, token):
        return
    await state.update_data(
        choices=[
            {'kind': target.kind, 'key': target.key, 'label': target.label}
            for target in targets
        ],
    )
    await message.answer(
        LEXICON_SUBSCRIPTIONS['search_results' if targets else 'search_empty'],
        reply_markup=subscription_results_keyboard(
            [target.label for target in targets], token
        ),
    )


@subscription_router.message(
    StateFilter(SubscriptionStates.searching), ~F.text
)
async def cmd_subscription_search_hint(
    message: Message, state: FSMContext
) -> None:
    data = await state.get_data()
    await message.answer(LEXICON_SUBSCRIPTIONS[f'search_{data["kind"]}'])


@subscription_router.message(
    StateFilter(SubscriptionStates.choosing_interval),
    ~F.text.startswith('/'),
    ~F.text.in_(NAVIGATION),
    ~F.text.startswith(LEXICON_BUTTONS_RU['/shows_with']),
    ~F.text.startswith('👤 '),
)
async def cmd_subscription_interval_hint(message: Message) -> None:
    await message.answer(LEXICON_SUBSCRIPTIONS['choose_interval'])


@subscription_router.callback_query(
    SubscriptionAction.filter(F.action == 'digest')
)
async def callback_digest(
    callback: CallbackQuery,
    callback_data: SubscriptionAction,
    session: AsyncSession,
) -> None:
    message = callback.message
    reference, value = callback_data.reference, callback_data.value
    if (
        not isinstance(message, Message)
        or message.chat.type != 'private'
        or message.chat.id != callback.from_user.id
        or not reference.isdecimal()
        or not value.isdecimal()
    ):
        await callback.answer(
            LEXICON_SUBSCRIPTIONS['digest_missing'], show_alert=True
        )
        return
    digest = await get_digest(session, callback.from_user.id, int(reference))
    page = int(value)
    if digest is None or page >= len(digest.pages):
        await callback.answer(
            LEXICON_SUBSCRIPTIONS['digest_missing'], show_alert=True
        )
        return
    await callback.answer()
    try:
        await message.edit_text(
            digest.pages[page],
            parse_mode='HTML',
            reply_markup=subscription_digest_keyboard(
                digest.id, page, len(digest.pages)
            ),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except TelegramBadRequest as error:
        if 'message is not modified' not in str(error).lower():
            raise


@subscription_router.callback_query(SubscriptionAction.filter())
async def callback_subscription(
    callback: CallbackQuery,
    callback_data: SubscriptionAction,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    message = callback.message
    if not isinstance(message, Message) or message.chat.type != 'private':
        await callback.answer(
            LEXICON_SUBSCRIPTIONS['private_only'], show_alert=True
        )
        return
    action = callback_data.action
    reference, value = callback_data.reference, callback_data.value
    data = await state.get_data()
    previous_state = await state.get_state()
    token = data.get('token')
    if action in {'choose', 'save'}:
        expected = (
            SubscriptionStates.searching
            if action == 'choose'
            else SubscriptionStates.choosing_interval
        )
        if previous_state != expected.state or data.get('token') != reference:
            await callback.answer(
                LEXICON_SUBSCRIPTIONS['stale'], show_alert=True
            )
            return
    if action in MANAGEMENT_ACTIONS and (
        not reference.isdecimal()
        or (
            action == 'interval'
            and (not value.isdecimal() or int(value) not in INTERVAL_LABELS)
        )
        or (action == 'toggle' and value not in {'0', '1'})
    ):
        await callback.answer()
        return
    if action in MANAGEMENT_ACTIONS or action in {'menu', 'main', 'list'}:
        token = await _start_flow(state)
        previous_state = None
    elif action == 'search' and reference in {'show', 'actor'}:
        token = await _start_search(state, reference)
        previous_state = SubscriptionStates.searching.state
    elif action == 'current':
        token = await _start_search(state, 'actor')
        previous_state = SubscriptionStates.searching.state
    elif action == 'save':
        if not value.isdecimal() or int(value) not in INTERVAL_LABELS:
            await callback.answer()
            return
        token = secrets.token_hex(4)
        await state.update_data(token=token)
    try:
        await callback.answer()
    except Exception:
        if action == 'save':
            await _restore_save_selection(state, token, reference)
        raise
    if not await _is_current_flow(state, previous_state, token):
        return
    user_id = callback.from_user.id
    if action == 'menu':
        keyboard = await _menu(session, user_id)
        if not await _is_current_flow(state, None, token):
            return
        await _edit(
            message,
            LEXICON_SUBSCRIPTIONS['menu'],
            keyboard,
        )
    elif action == 'main':
        try:
            await message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest as error:
            if 'message is not modified' not in str(error).lower():
                raise
        if not await _is_current_flow(state, None, token):
            return
        keyboard_message = message.model_copy(
            update={'from_user': callback.from_user}
        )
        keyboard = await main_keyboard(keyboard_message, session)
        if not await _is_current_flow(state, None, token):
            return
        await message.answer(
            LEXICON_RU['MAIN_MENU'],
            reply_markup=keyboard,
        )
    elif action == 'search' and reference in {'show', 'actor'}:
        await _edit(
            message,
            LEXICON_SUBSCRIPTIONS[f'search_{reference}'],
            subscription_back_keyboard(),
        )
    elif action == 'current':
        user = await get_user(session, user_id)
        if not await _is_current_flow(
            state, SubscriptionStates.searching, token
        ):
            return
        name = user.spectacle_full_name if user else None
        targets = (
            await search_targets(session, 'actor', name, limit=8)
            if name
            else []
        )
        if not await _is_current_flow(
            state, SubscriptionStates.searching, token
        ):
            return
        target = next(
            (
                target
                for target in targets
                if target.key == normalize_actor_name(name)
            ),
            None,
        )
        if target is not None:
            await _choose_target(message, state, target)
        else:
            await _edit(
                message,
                LEXICON_SUBSCRIPTIONS['current_missing'],
                subscription_back_keyboard(),
            )
    elif action == 'choose':
        choices = data.get('choices', [])
        if not value.isdecimal() or int(value) >= len(choices):
            return
        await _choose_target(
            message, state, SubscriptionTarget(**choices[int(value)])
        )
    elif action == 'save':
        try:
            subscription = await save_subscription(
                session,
                user_id,
                SubscriptionTarget(**data['target']),
                int(value),
            )
        except ValueError:
            try:
                keyboard = await _menu(session, user_id)
            except Exception:
                await _restore_save_selection(state, token, reference)
                raise
            if not await _is_current_flow(
                state, SubscriptionStates.choosing_interval, token
            ):
                return
            await _start_flow(state)
            await _edit(
                message,
                LEXICON_SUBSCRIPTIONS['target_missing'],
                keyboard,
            )
            return
        except Exception:
            await _restore_save_selection(state, token, reference)
            raise
        if not await _is_current_flow(
            state, SubscriptionStates.choosing_interval, token
        ):
            return
        await _start_flow(state)
        await _card(message, subscription, LEXICON_SUBSCRIPTIONS['created'])
    elif action == 'list':
        await _list(
            message,
            session,
            user_id,
            state,
            token,
            int(reference) if reference.isdecimal() else 0,
        )
    elif action in MANAGEMENT_ACTIONS:
        subscription_id = int(reference)
        subscription = await get_subscription(
            session, user_id, subscription_id
        )
        if not await _is_current_flow(state, None, token):
            return
        if subscription is None:
            await _list(
                message,
                session,
                user_id,
                state,
                token,
                notice=LEXICON_SUBSCRIPTIONS['missing'],
            )
            return
        if action == 'view':
            await _card(message, subscription)
        elif action == 'intervals':
            await _edit(
                message,
                _target_title(subscription.kind, subscription.label)
                + '\n\n'
                + LEXICON_SUBSCRIPTIONS['choose_interval'],
                subscription_intervals_keyboard(reference, creating=False),
            )
        elif action == 'delete':
            await delete_subscription(session, user_id, subscription_id)
            if not await _is_current_flow(state, None, token):
                return
            await _list(
                message,
                session,
                user_id,
                state,
                token,
                notice=LEXICON_SUBSCRIPTIONS['deleted'],
            )
        else:
            if action == 'interval':
                subscription = await update_subscription(
                    session,
                    user_id,
                    subscription_id,
                    interval_seconds=int(value),
                )
            else:
                subscription = await update_subscription(
                    session, user_id, subscription_id, enabled=value == '1'
                )
            if not await _is_current_flow(state, None, token):
                return
            if subscription is not None:
                notice = (
                    LEXICON_SUBSCRIPTIONS['changed']
                    if action == 'interval'
                    else ''
                )
                await _card(message, subscription, notice)
            else:
                await _list(
                    message,
                    session,
                    user_id,
                    state,
                    token,
                    notice=LEXICON_SUBSCRIPTIONS['missing'],
                )


@subscription_router.callback_query(F.data.startswith('sub:'))
async def callback_invalid_subscription(callback: CallbackQuery) -> None:
    await callback.answer(LEXICON_SUBSCRIPTIONS['stale'], show_alert=True)
