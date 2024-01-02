from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    event,
    Table,
    func,
    DateTime,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship

from telegram.db import Base


def current_timestamp():
    return int(datetime.now().timestamp())


actors_spectacles = Table(
    'actors_spectacles',
    Base.metadata,
    Column('user_id', ForeignKey('users.user_id'), primary_key=True),
    Column(
        'spectacle_id', ForeignKey('spectacles.spectacle_id'), primary_key=True
    ),
)


class User(Base):
    __tablename__ = 'users'
    user_id = Column(
        BigInteger, primary_key=True, unique=True, autoincrement=False
    )

    username = Column(String)
    full_name = Column(String)
    actor = Column(Boolean, default=False)
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


class Spectacle(Base):
    __tablename__ = 'spectacles'
    spectacle_id = Column(
        BigInteger, primary_key=True, unique=True, autoincrement=True
    )
    title = Column(String)
    actors = relationship(
        'User', secondary=actors_spectacles,
        backref='participated_spectacles'
    )
