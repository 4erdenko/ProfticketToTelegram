from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db.user_operations import get_available_months


class MonthFilter(BaseFilter):
    def __init__(self, personal: bool = False):
        self.personal = personal

    async def __call__(
        self, message: Message, session: AsyncSession
    ) -> bool | dict[str, Any]:
        months = await get_available_months(session)
        if not months:
            return False

        # Получаем список названий месяцев
        month_names = [month[1] for month in months]

        # В персональном режиме проверяем с префиксом
        if self.personal:
            month_names = [f'👤 {name}' for name in month_names]

        # Проверяем, что текст сообщения соответствует одному из месяцев
        return (
            {'is_personal': self.personal}
            if message.text in month_names
            else False
        )
