from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from telegram.db import User

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncSession


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any | None:
        event_user = data.get('event_from_user')
        session: AsyncSession = data['session']

        if not event_user:
            return None

        user = await session.get(User, event_user.id)
        if user and user.banned:
            return None
        return await handler(event, data)
