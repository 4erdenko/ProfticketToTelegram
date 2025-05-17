from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, Integer, String, func

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


class PriceHistory(Base):
    __tablename__ = 'price_history'

    id = Column(Integer, primary_key=True)
    show_id = Column(String)
    timestamp = Column(Integer, default=current_timestamp)
    min_price = Column(Integer)
    max_price = Column(Integer)

