from aiogram.filters import BaseFilter
from aiogram.types import Message

from config import settings


class IsAdmin(BaseFilter):
    """

    :class: IsAdmin

    This class is a filter that checks if a user is an admin by comparing
    their ID to the admin ID defined in the settings.

    """
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id == settings.ADMIN_ID
