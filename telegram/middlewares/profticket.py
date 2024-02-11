from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services.profticket.profticket_api import ProfticketsInfo


class ProfticketSessionMiddleware(BaseMiddleware):
    def __init__(self, profitcket_object: ProfticketsInfo):
        super().__init__()
        self.profticket_object = profitcket_object

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data['profticket'] = self.profticket_object
        return await handler(event, data)
