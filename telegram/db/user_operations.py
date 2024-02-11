import logging
from typing import Type

from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db import User

logger = logging.getLogger(__name__)


async def get_user(session: AsyncSession, user_id: int) -> Type[User] | None:
    return await session.get(User, user_id)


async def search_count(session: AsyncSession, user_id: int):
    user = await get_user(session, user_id)
    if user.search_count is not None:
        user.search_count += 1
    else:
        user.search_count = 1
    await session.commit()
