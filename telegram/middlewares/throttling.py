from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram import BaseMiddleware
from cachetools import TTLCache

from config import settings
from telegram.db import User

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from typing import Any

    from aiogram.types import TelegramObject


class ThrottledError(Exception):
    pass


@dataclass(kw_only=True, slots=True)
class ThrottlingData:
    rate: int = 0
    sent_warning: bool = False


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._cache: TTLCache[int, ThrottlingData] = TTLCache(
            maxsize=10_000, ttl=settings.TTL_IN_SEC
        )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any | None:
        event_user: User = data['event_from_user']

        session = data['session']
        if not event_user:
            return None

        if event_user.id not in self._cache:
            self._cache[event_user.id] = ThrottlingData()

        throttling_data = self._cache[event_user.id]

        if throttling_data.rate == settings.MAX_RATE_SEC_IN_TTL:
            self._cache[event_user.id] = throttling_data

            if not throttling_data.sent_warning:
                throttling_data.sent_warning = True
                user = await session.get(User, event_user.id)
                user.throttling += 1
                await session.commit()
                raise ThrottledError

            return None
        throttling_data.rate += 1

        return await handler(event, data)
