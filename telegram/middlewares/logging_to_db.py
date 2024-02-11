import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject, Update

from telegram.db.models import User

logger = logging.getLogger(__name__)


class UserLoggingMiddleware(BaseMiddleware):
    def __init__(self):

        super().__init__()

    async def on_process_message(
        self, update: types.Update, data: Dict[str, Any]
    ) -> None:
        session = data['session']
        if update.message:
            message = update.message
            user = await session.get(User, message.from_user.id)
            if not user:
                user = User(
                    user_id=message.from_user.id,
                    username=message.from_user.username,
                    bot_full_name=message.from_user.full_name,
                )
                session.add(user)
                await session.commit()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            await self.on_process_message(event, data)
        result = await handler(event, data)
        return result
