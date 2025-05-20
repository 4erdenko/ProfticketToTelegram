from datetime import datetime
from config import settings
import pytz

from sqlalchemy import (BigInteger, Boolean, Column, ForeignKey, Integer,
                        String, func)

from telegram.db import Base


def current_timestamp():
    tz = pytz.timezone(settings.DEFAULT_TIMEZONE)
    return int(datetime.now(tz).timestamp())


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
        tz = pytz.timezone(settings.DEFAULT_TIMEZONE)
        return (
            datetime.fromtimestamp(self._bot_blocked_date, tz)
            if self._bot_blocked_date
            else None
        )

    @bot_blocked_date.setter
    def bot_blocked_date(self, value):
        tz = pytz.timezone(settings.DEFAULT_TIMEZONE)
        self._bot_blocked_date = int(value.timestamp()) if value else None


class Show(Base):
    __tablename__ = 'shows'

    id = Column(String, primary_key=True)  # id события
    show_id = Column(Integer)  # id шоу/спектакля
    theater = Column(String)  # название театра
    scene = Column(String)  # название сцены
    show_name = Column(String)  # название спектакля
    date = Column(String)  # дата и время
    duration = Column(String)  # продолжительность
    age = Column(String)  # возрастное ограничение
    seats = Column(Integer)  # количество мест
    previous_seats = Column(Integer)  # прошлое количество мест
    image = Column(String)  # ссылка на изображение
    annotation = Column(String)  # описание
    min_price = Column(Integer)  # минимальная цена
    max_price = Column(Integer)  # максимальная цена
    pushkin = Column(Boolean, default=False)  # поддержка Пушкинской карты
    buy_link = Column(String)  # ссылка на покупку
    actors = Column(String)  # JSON строка со списком актеров
    month = Column(Integer)  # месяц
    year = Column(Integer)  # год
    updated_at = Column(
        Integer
    )  # время последнего обновления (Unix timestamp)
    is_deleted = Column(Boolean, default=False)  # мягкое удаление


class ShowSeatHistory(Base):
    __tablename__ = 'show_seat_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    show_id = Column(String, ForeignKey('shows.id'), index=True)
    timestamp = Column(Integer, default=current_timestamp, index=True)
    seats = Column(Integer)
