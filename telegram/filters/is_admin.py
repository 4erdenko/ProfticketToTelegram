from aiogram.filters import BaseFilter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from telegram.db.models import User


def has_admin_access(user_id: int, user: User | None = None) -> bool:
    return user_id == settings.ADMIN_ID or bool(getattr(user, 'admin', False))


class IsAdmin(BaseFilter):
    """

    :class: IsAdmin

    This class is a filter that checks if a user is an admin by comparing
    their ID to the admin ID defined in the settings.

    """

    async def __call__(self, message: Message, session: AsyncSession) -> bool:
        if not message.from_user:
            return False
        user_id = message.from_user.id
        if has_admin_access(user_id):
            return True
        user = await session.get(User, user_id)
        return has_admin_access(user_id, user)
