import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject, Update
from sqlalchemy.dialects.postgresql import insert

from telegram.db.models import User

logger = logging.getLogger(__name__)


class UserLoggingMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()

    async def on_process_message(
        self, update: types.Update, data: dict[str, Any]
    ) -> None:
        session = data['session']
        event_user = data.get('event_from_user')
        if event_user is None and update.message:
            event_user = update.message.from_user
        if event_user is not None:
            user = await session.get(User, event_user.id)
            if not user:
                statement = insert(User).values(
                    user_id=event_user.id,
                    username=event_user.username,
                    bot_full_name=event_user.full_name,
                )
                await session.execute(
                    statement.on_conflict_do_nothing(
                        index_elements=[User.user_id]
                    )
                )
                await session.commit()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            await self.on_process_message(event, data)
        result = await handler(event, data)
        return result
