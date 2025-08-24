import logging
from datetime import datetime

import pytz
from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from telegram.db.models import Show, ShowSeatHistory, User
from telegram.filters.is_admin import IsAdmin
from telegram.keyboards.admin_keyboard import admin_main_menu_keyboard
from telegram.keyboards.analytics_keyboard import RUS_TO_MONTH
from telegram.keyboards.main_keyboard import main_keyboard
from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU, LEXICON_RU
from telegram.tg_utils import send_chunks_answer

logger = logging.getLogger(__name__)

admin_router = Router(name='admin_router')
admin_router.message.filter(IsAdmin())


@admin_router.message(F.text == LEXICON_BUTTONS_RU['/admin_menu'])
async def cmd_admin_menu(message: Message):
    await message.answer(
        LEXICON_RU['ADMIN_MENU_TITLE'],
        reply_markup=admin_main_menu_keyboard(),
    )


@admin_router.message(F.text == LEXICON_BUTTONS_RU['/admin_stats'])
async def cmd_admin_stats(message: Message, session: AsyncSession):
    """
    Отчёт по статистике пользователей для админа.
    Сейчас: количество пользователей, суммарное число запросов и топ-10
    по числу запросов.
    """
    # totals
    total_users = (
        await session.execute(select(func.count(User.user_id)))
    ).scalar_one()
    total_searches = (
        await session.execute(
            select(func.coalesce(func.sum(User.search_count), 0))
        )
    ).scalar_one()

    # top users by search_count
    top_users = (
        (
            await session.execute(
                select(User)
                .order_by(User.search_count.desc().nullslast())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    lines: list[str] = [
        f'<b>{LEXICON_RU["ADMIN_STATS_TITLE"]}</b>',
        f'Всего пользователей: <b>{total_users}</b>',
        f'Всего запросов: <b>{total_searches}</b>',
        '',
        '<b>Топ-10 пользователей по запросам:</b>',
    ]

    if top_users:
        for i, u in enumerate(top_users, 1):
            cnt = u.search_count or 0
            uname = f'@{u.username}' if u.username else '—'
            fname = u.bot_full_name or '—'
            choice = (u.spectacle_full_name or '—').title()
            lines.append(
                f'{i}.\n'
                f'• Имя: <b>{fname}</b>\n'
                f'• Username: {uname}\n'
                f'• ID: <code>{u.user_id}</code>\n'
                f'• Запросов: <b>{cnt}</b>\n'
                f'• 🎭 Выбор: <i>{choice}</i>'
            )
    else:
        lines.append('Нет данных по пользователям.')

    await send_chunks_answer(message, '\n'.join(lines))


@admin_router.message(F.text == LEXICON_BUTTONS_RU['/back_to_main_menu'])
async def cmd_admin_back_to_main(message: Message, session: AsyncSession):
    await message.answer(
        LEXICON_RU['MAIN_MENU'],
        reply_markup=await main_keyboard(message, session),
    )


@admin_router.message(F.text == LEXICON_BUTTONS_RU['/admin_users'])
async def cmd_admin_users_overview(message: Message, session: AsyncSession):
    pytz.timezone(settings.DEFAULT_TIMEZONE)

    total_users = (
        await session.execute(select(func.count(User.user_id)))
    ).scalar_one()
    banned_users = (
        await session.execute(
            select(func.count()).where(User.banned.is_(True))
        )
    ).scalar_one()
    blocked_users = (
        await session.execute(
            select(func.count()).where(User.bot_blocked.is_(True))
        )
    ).scalar_one()
    active_users = total_users - banned_users - blocked_users

    admin_flags = (
        await session.execute(select(func.count()).where(User.admin.is_(True)))
    ).scalar_one()
    actors = (
        await session.execute(select(func.count()).where(User.actor.is_(True)))
    ).scalar_one()
    asst_directors = (
        await session.execute(
            select(func.count()).where(User.assistant_director.is_(True))
        )
    ).scalar_one()
    administrators = (
        await session.execute(
            select(func.count()).where(User.administrator.is_(True))
        )
    ).scalar_one()

    chosen_actor_count = (
        await session.execute(
            select(func.count()).where(
                User.spectacle_full_name.is_not(None),
                User.spectacle_full_name != '',
            )
        )
    ).scalar_one()

    total_searches = (
        await session.execute(
            select(func.coalesce(func.sum(User.search_count), 0))
        )
    ).scalar_one()

    # Top 10 by searches
    top_search = (
        (
            await session.execute(
                select(User)
                .order_by(User.search_count.desc().nullslast())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    # Top 10 by throttling
    top_throttling = (
        (
            await session.execute(
                select(User)
                .order_by(User.throttling.desc().nullslast())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    lines: list[str] = [
        f'<b>{LEXICON_RU["ADMIN_USERS_TITLE"]}</b>',
        f'Всего пользователей: <b>{total_users}</b>',
        f'Активных: <b>{active_users}</b> | Забанено: <b>{banned_users}</b> | Блокировали бота: <b>{blocked_users}</b>',
        f'Админ-флаг: <b>{admin_flags}</b> | Роли — актёры: <b>{actors}</b>, пом.реж.: <b>{asst_directors}</b>, администраторы: <b>{administrators}</b>',
        f'Выбрали актёра/актрису: <b>{chosen_actor_count}</b>',
        f'Суммарно запросов: <b>{total_searches}</b>',
        '',
        '<b>Топ-10 по числу запросов:</b>',
    ]

    if top_search:
        for i, u in enumerate(top_search, 1):
            cnt = u.search_count or 0
            uname = f'@{u.username}' if u.username else '—'
            fname = u.bot_full_name or '—'
            choice = (u.spectacle_full_name or '—').title()
            lines.append(
                f'{i}.\n'
                f'• Имя: <b>{fname}</b>\n'
                f'• Username: {uname}\n'
                f'• ID: <code>{u.user_id}</code>\n'
                f'• Запросов: <b>{cnt}</b>\n'
                f'• 🎭 Выбор: <i>{choice}</i>'
            )
    else:
        lines.append('Нет данных по запросам.')

    lines.append('')
    lines.append('<b>Топ-10 по троттлингу:</b>')
    if top_throttling:
        for i, u in enumerate(top_throttling, 1):
            cnt = u.throttling or 0
            uname = f'@{u.username}' if u.username else '—'
            fname = u.bot_full_name or '—'
            choice = (u.spectacle_full_name or '—').title()
            lines.append(
                f'{i}.\n'
                f'• Имя: <b>{fname}</b>\n'
                f'• Username: {uname}\n'
                f'• ID: <code>{u.user_id}</code>\n'
                f'• Троттлинг: <b>{cnt}</b>\n'
                f'• 🎭 Выбор: <i>{choice}</i>'
            )
    else:
        lines.append('Нет данных по троттлингу.')

    await send_chunks_answer(message, '\n'.join(lines))


@admin_router.message(F.text == LEXICON_BUTTONS_RU['/admin_prefs'])
async def cmd_admin_user_prefs(message: Message, session: AsyncSession):
    # агрегируем выбор актёров/актрис
    name_expr = func.lower(func.trim(User.spectacle_full_name))
    total_users = (
        await session.execute(select(func.count(User.user_id)))
    ).scalar_one()
    chosen_count = (
        await session.execute(
            select(func.count()).where(
                User.spectacle_full_name.is_not(None),
                User.spectacle_full_name != '',
            )
        )
    ).scalar_one()
    no_choice_count = total_users - chosen_count
    unique_choices = (
        await session.execute(
            select(func.count(func.distinct(name_expr))).where(
                User.spectacle_full_name.is_not(None),
                User.spectacle_full_name != '',
            )
        )
    ).scalar_one()
    result = (
        await session.execute(
            select(name_expr.label('name'), func.count().label('cnt'))
            .where(
                User.spectacle_full_name.is_not(None),
                User.spectacle_full_name != '',
            )
            .group_by('name')
            .order_by(desc('cnt'))
            .limit(50)
        )
    ).all()

    lines: list[str] = [f'<b>{LEXICON_RU["ADMIN_PREFS_TITLE"]}</b>']
    lines.append(
        f'Всего с выбором: {chosen_count} | Без выбора: {no_choice_count} | Уникальных имён: {unique_choices}'
    )
    if not result:
        lines.append(LEXICON_RU['NO_PREFS'])
        await message.answer('\n'.join(lines))
        return

    lines.append('\n<b>Топ-выборов (до 50):</b>')
    for i, row in enumerate(result, 1):
        name, cnt = row[0], row[1]
        display = (name or '').title()
        lines.append(f'{i}.\n• Имя: {display}\n• Выборов: {cnt}')

    # примеры пользователей для первых 5
    top_names = [r[0] for r in result[:5]]
    if top_names:
        lines.append('\n<b>Примеры пользователей (по 5) для топ-5:</b>')
    for name in top_names:
        users = (
            (
                await session.execute(
                    select(User)
                    .where(
                        func.lower(func.trim(User.spectacle_full_name)) == name
                    )
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )
        if users:
            lines.append(f'{(name or "").title()}:')
            for u in users:
                uname = f'@{u.username}' if u.username else '—'
                fname = u.bot_full_name or '—'
                choice = (u.spectacle_full_name or '—').title()
                lines.append(
                    f'• Имя: {fname} | Username: {uname} | ID: {u.user_id} | 🎭 {choice}'
                )

    # Доп. выборки: пользователи без выбора — примеры до 10
    no_choice_users = (
        (
            await session.execute(
                select(User)
                .where(
                    (User.spectacle_full_name.is_(None))
                    | (User.spectacle_full_name == '')
                )
                .order_by(User.search_count.desc().nullslast())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    lines.append('\n<b>Без выбора (примеры до 10):</b>')
    if no_choice_users:
        for u in no_choice_users:
            uname = f'@{u.username}' if u.username else '—'
            fname = u.bot_full_name or '—'
            cnt = u.search_count or 0
            lines.append(
                f'• Имя: {fname} | Username: {uname} | ID: {u.user_id} | Запросов: {cnt}'
            )
    else:
        lines.append('Все пользователи сделали выбор.')

    await send_chunks_answer(message, '\n'.join(lines))


@admin_router.message(F.text == LEXICON_BUTTONS_RU['/admin_db'])
async def cmd_admin_db_overview(message: Message, session: AsyncSession):
    tz = pytz.timezone(settings.DEFAULT_TIMEZONE)

    total_shows = (
        await session.execute(select(func.count(Show.id)))
    ).scalar_one()
    active_shows = (
        await session.execute(
            select(func.count()).where(Show.is_deleted.is_(False))
        )
    ).scalar_one()
    deleted_shows = total_shows - active_shows

    seat_history_rows = (
        await session.execute(select(func.count(ShowSeatHistory.id)))
    ).scalar_one()

    latest_update_ts = (
        await session.execute(select(func.max(Show.updated_at)))
    ).scalar_one()
    if latest_update_ts:
        dt = datetime.fromtimestamp(int(latest_update_ts), tz)
        now = datetime.now(tz)
        age_sec = int((now - dt).total_seconds())
        if age_sec < 120:
            age_str = f'{age_sec} сек. назад'
        elif age_sec < 7200:
            age_str = f'{age_sec // 60} мин. назад'
        else:
            age_str = f'{age_sec // 3600} ч. назад'
        latest_str = f'{dt.strftime("%Y-%m-%d %H:%M:%S %Z")} ({age_str})'
    else:
        latest_str = '—'

    # Покажем разбивку по месяцам (активные)
    per_month = (
        await session.execute(
            select(Show.year, Show.month, func.count().label('cnt'))
            .where(Show.is_deleted.is_(False))
            .group_by(Show.year, Show.month)
            .order_by(Show.year.asc(), Show.month.asc())
        )
    ).all()

    num_to_rus = {v: k for k, v in RUS_TO_MONTH.items()}

    lines: list[str] = [
        f'<b>{LEXICON_RU["ADMIN_DB_TITLE"]}</b>',
        f'Шоу: всего <b>{total_shows}</b> | активных <b>{active_shows}</b> | удалённых <b>{deleted_shows}</b>',
        f'История мест: строк <b>{seat_history_rows}</b>',
        f'Последнее обновление: <b>{latest_str}</b>',
    ]

    if per_month:
        lines.append('\n<b>По месяцам (активные):</b>')
        for year, month, cnt in per_month:
            month_name = num_to_rus.get(month, str(month))
            lines.append(f'• {month_name} {year}: <b>{cnt}</b>')

    await send_chunks_answer(message, '\n'.join(lines))
