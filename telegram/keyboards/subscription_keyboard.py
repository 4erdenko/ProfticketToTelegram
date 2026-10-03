from collections.abc import Sequence
from typing import Any

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram.lexicon.subscriptions import (
    INTERVAL_LABELS,
    LEXICON_SUBSCRIPTIONS,
)

PAGE_SIZE = 6


class SubscriptionAction(CallbackData, prefix='sub'):
    action: str
    reference: str = ''
    value: str = ''


def _button(
    text: str, action: str, reference: str = '', value: str = ''
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=SubscriptionAction(
            action=action, reference=reference, value=value
        ).pack(),
    )


def _label(label: str) -> str:
    return label if len(label) <= 48 else label[:45] + '…'


def subscription_digest_keyboard(
    identifier: int, page: int, total: int
) -> InlineKeyboardMarkup:
    buttons = []
    reference = str(identifier)
    if page:
        buttons.append(_button('←', 'digest', reference, str(page - 1)))
    buttons.append(
        _button(f'{page + 1}/{total}', 'digest', reference, str(page))
    )
    if page + 1 < total:
        buttons.append(
            _button(
                LEXICON_SUBSCRIPTIONS['digest_next'],
                'digest',
                reference,
                str(page + 1),
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def subscription_menu_keyboard(
    current_actor: str | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [_button('🎭 Найти спектакль', 'search', 'show')],
        [_button('👤 Найти актёра', 'search', 'actor')],
    ]
    if current_actor:
        rows.append([_button(f'👤 {_label(current_actor)}', 'current')])
    rows.extend(
        [
            [_button('📋 Мои подписки', 'list', '0')],
            [_button('↩️ Главное меню', 'main')],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscription_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button('↩️ К подпискам', 'menu')]]
    )


def subscription_results_keyboard(
    labels: Sequence[str], token: str
) -> InlineKeyboardMarkup:
    rows = [
        [_button(_label(label), 'choose', token, str(index))]
        for index, label in enumerate(labels)
    ]
    rows.append([_button('↩️ К подпискам', 'menu')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscription_intervals_keyboard(
    reference: str, *, creating: bool
) -> InlineKeyboardMarkup:
    action = 'save' if creating else 'interval'
    buttons = [
        _button(label, action, reference, str(interval))
        for interval, label in INTERVAL_LABELS.items()
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    if creating:
        rows.append([_button('↩️ К подпискам', 'menu')])
    else:
        rows.append([_button('↩️ К подписке', 'view', reference)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscription_card_keyboard(
    subscription_id: int, *, enabled: bool
) -> InlineKeyboardMarkup:
    reference = str(subscription_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button('🕒 Изменить частоту', 'intervals', reference)],
            [
                _button(
                    '⏸ Пауза' if enabled else '▶️ Включить',
                    'toggle',
                    reference,
                    '0' if enabled else '1',
                ),
                _button('❌ Отписаться', 'delete', reference),
            ],
            [_button('📋 Мои подписки', 'list', '0')],
        ]
    )


def subscription_list_keyboard(
    subscriptions: Sequence[Any], page: int = 0
) -> InlineKeyboardMarkup:
    page = max(0, min(page, (len(subscriptions) - 1) // PAGE_SIZE))
    rows = []
    for subscription in subscriptions[
        page * PAGE_SIZE : (page + 1) * PAGE_SIZE
    ]:
        icon = '🎭' if subscription.kind == 'show' else '👤'
        status = '' if subscription.enabled else ' ⏸'
        rows.append(
            [
                _button(
                    f'{icon} {_label(subscription.label)}{status}',
                    'view',
                    str(subscription.id),
                )
            ]
        )
    navigation = []
    if page:
        navigation.append(_button('←', 'list', str(page - 1)))
    if (page + 1) * PAGE_SIZE < len(subscriptions):
        navigation.append(_button('→', 'list', str(page + 1)))
    if navigation:
        rows.append(navigation)
    rows.append([_button('↩️ К подпискам', 'menu')])
    return InlineKeyboardMarkup(inline_keyboard=rows)
