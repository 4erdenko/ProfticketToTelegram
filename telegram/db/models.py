from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey,
                        Integer, String, Table, event, func)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship

from telegram.db import Base


def current_timestamp():
    return int(datetime.now().timestamp())

class User(Base):
    __tablename__ = 'users'
    user_id = Column(
        BigInteger, primary_key=True, unique=True, autoincrement=False
    )

    username = Column(String)
    bot_full_name = Column(String)
    spectacle_full_name = Column(String)
    search_count = Column(Integer, default=0)
    actor = Column(Boolean, default=False)
    assistant_director = Column(Boolean, default=False)
    administrator = Column(Boolean, default=False)
    throttling = Column(Integer, default=0)
    banned = Column(Boolean, default=False)
    admin = Column(Boolean, default=False)
    start_bot_date = Column(
        Integer, server_default=func.extract('epoch', func.now())
    )
    bot_blocked = Column(Boolean, default=False)
    _bot_blocked_date = Column('bot_blocked_date', Integer)

    @property
    def bot_blocked_date(self):
        return (
            datetime.fromtimestamp(self._bot_blocked_date)
            if self._bot_blocked_date
            else None
        )

    @bot_blocked_date.setter
    def bot_blocked_date(self, value):
        self._bot_blocked_date = int(value.timestamp()) if value else None

