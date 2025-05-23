import sys
import types
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

if 'aiogram' not in sys.modules:
    sys.modules['aiogram'] = types.ModuleType('aiogram')
if not hasattr(sys.modules['aiogram'], 'Bot'):

    class Bot:
        async def send_message(self, *a, **kw):
            pass

    sys.modules['aiogram'].Bot = Bot

from services.profticket import analytics
from services.profticket.profticket_snapshoter import ShowUpdateService
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory


class DummyProfticket:
    def __init__(self, data):
        self.data = data

    def set_date(self, month, year):
        pass

    async def collect_full_info(self):
        return self.data


class DummyBot:
    async def send_message(self, *a, **kw):
        pass


class FakeAsyncSession:
    def __init__(self, sync_session):
        self._session = sync_session

    async def execute(self, *a, **kw):
        return self._session.execute(*a, **kw)

    async def commit(self):
        self._session.commit()

    async def rollback(self):
        self._session.rollback()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._session.close()


class SeatHistoryTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        self.engine.dispose()

    async def test_history_created(self):
        data = {
            'e1': {
                'show_id': '1',
                'theater': 't',
                'scene': 's',
                'show_name': 'n',
                'date': 'd',
                'duration': '1h',
                'age': '0+',
                'seats': 5,
                'image': 'i',
                'annotation': 'a',
                'min_price': 0,
                'max_price': 0,
                'pushkin': False,
                'buy_link': 'b',
                'actors': ['ac'],
            }
        }
        service = ShowUpdateService(
            self.Session, DummyProfticket(data), DummyBot()
        )
        sync_session = self.Session()
        async with FakeAsyncSession(sync_session) as session:
            await service._update_month_data(session, 1, 2024)
            res = await session.execute(select(ShowSeatHistory))
            history = res.scalars().all()
            self.assertEqual(len(history), 1)
            row = history[0]
            self.assertEqual(row.show_id, 'e1')
            self.assertEqual(row.seats, 5)

    def test_calculate_average_sales_rate_for_show(self):
        history_s1 = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=20, seats=7),
            ShowSeatHistory(show_id='s1', timestamp=30, seats=5),
        ]
        rate = analytics.calculate_average_sales_rate_for_show(history_s1)
        self.assertIsNone(rate)

        # Интервалы в 1 час (новый минимум)
        history_s2 = [
            ShowSeatHistory(show_id='s2', timestamp=0, seats=10),
            ShowSeatHistory(
                show_id='s2', timestamp=1 * 3600, seats=7
            ),  # 3 билета за 1 час
            ShowSeatHistory(
                show_id='s2', timestamp=2 * 3600, seats=5
            ),  # 2 билета за 1 час
        ]
        rate = analytics.calculate_average_sales_rate_for_show(history_s2)
        # Медиана между 3/3600 и 2/3600
        median_rate = (3 / 3600 + 2 / 3600) / 2
        self.assertAlmostEqual(rate, median_rate, places=7)

    def test_predict_sold_out(self):
        history_s1 = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=20, seats=7),
            ShowSeatHistory(show_id='s1', timestamp=30, seats=5),
        ]
        pred = analytics.predict_sold_out(history_s1)
        self.assertIsNone(pred)

        history_s2 = [
            ShowSeatHistory(show_id='s2', timestamp=0, seats=10),
            ShowSeatHistory(show_id='s2', timestamp=1 * 3600, seats=7),
            ShowSeatHistory(show_id='s2', timestamp=2 * 3600, seats=5),
        ]
        pred = analytics.predict_sold_out(history_s2)
        # Теперь pred тоже None, т.к. только 2 интервала (меньше 3)
        self.assertIsNone(pred)

    def test_top_shows_by_sales(self):
        shows_data = [
            Show(
                id='s1',
                show_name='Show Alpha',
                month=1,
                year=2024,
                actors='[]',
            ),
            Show(
                id='s1b',
                show_name='Show Alpha',
                month=1,
                year=2024,
                actors='[]',
            ),
            Show(
                id='s2', show_name='Show Beta', month=1, year=2024, actors='[]'
            ),
            Show(
                id='s3',
                show_name='Show Gamma',
                month=2,
                year=2024,
                actors='[]',
            ),
        ]
        histories_data = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=30, seats=5),  # s1 sold 5
            ShowSeatHistory(show_id='s1b', timestamp=10, seats=8),
            ShowSeatHistory(
                show_id='s1b', timestamp=30, seats=6
            ),  # s1b sold 2
            ShowSeatHistory(show_id='s2', timestamp=10, seats=20),
            ShowSeatHistory(show_id='s2', timestamp=30, seats=17),  # s2 sold 3
            ShowSeatHistory(show_id='s3', timestamp=10, seats=100),
            ShowSeatHistory(
                show_id='s3', timestamp=30, seats=90
            ),  # s3 sold 10 (month 2)
        ]
        top_all_time = analytics.top_shows_by_sales(
            shows_data, histories_data, n=3
        )
        # Для all time топ не пустой
        self.assertEqual(len(top_all_time), 3)
        self.assertEqual(top_all_time[0][0], 'Show Gamma')
        self.assertEqual(top_all_time[0][1], 10)
        self.assertEqual(top_all_time[1][0], 'Show Alpha')
        self.assertEqual(top_all_time[1][1], 5)
        self.assertEqual(top_all_time[2][0], 'Show Beta')
        self.assertEqual(top_all_time[2][1], 3)
        self.assertEqual(
            len([x for x in top_all_time if x[0] == 'Show Alpha']), 1
        )

        top_month1 = analytics.top_shows_by_sales(
            shows_data, histories_data, month=1, year=2024, n=2
        )
        # Теперь результат совпадает с all time для этого месяца
        self.assertEqual(len(top_month1), 2)
        self.assertEqual(top_month1[0], ('Show Alpha', 5, 's1'))
        self.assertEqual(top_month1[1], ('Show Beta', 3, 's2'))

    def test_top_artists_by_sales(self):
        shows = [
            Show(
                id='s1',
                actors='["Alice", "Bob"]',
                month=1,
                year=2024,
                show_name='S1',
            ),
            Show(
                id='s2',
                actors='["Alice", "Charlie"]',
                month=1,
                year=2024,
                show_name='S2',
            ),
            Show(
                id='s3', actors='["Bob"]', month=1, year=2024, show_name='S3'
            ),
            Show(
                id='s4', actors='["David"]', month=2, year=2024, show_name='S4'
            ),
        ]
        histories = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=20, seats=5),  # s1 sold 5
            ShowSeatHistory(show_id='s2', timestamp=10, seats=20),
            ShowSeatHistory(
                show_id='s2', timestamp=20, seats=10
            ),  # s2 sold 10
            ShowSeatHistory(show_id='s3', timestamp=10, seats=15),
            ShowSeatHistory(show_id='s3', timestamp=20, seats=10),  # s3 sold 5
            ShowSeatHistory(show_id='s4', timestamp=10, seats=30),
            ShowSeatHistory(
                show_id='s4', timestamp=20, seats=20
            ),  # s4 sold 10
        ]
        result_month1 = analytics.top_artists_by_sales(
            shows, histories, month=1, year=2024, n=3
        )
        expected_month1 = sorted(
            [('Alice', 15), ('Bob', 10), ('Charlie', 10)],
            key=lambda x: (-x[1], x[0]),
        )
        self.assertEqual(result_month1, expected_month1)

    def test_top_artists_by_sales_with_titles(self):
        # Тест для проверки обработки титулов
        shows = [
            Show(
                id='s1',
                actors='["Народный артист России", "Олег Меньшиков", '
                '"Иван Иванов"]',
                month=1,
                year=2024,
                show_name='S1',
            ),
            Show(
                id='s2',
                actors='["Народная артистка России", "Анна Петрова", '
                '"лауреат Государственных премий", "Петр Сидоров"]',
                month=1,
                year=2024,
                show_name='S2',
            ),
            Show(
                id='s3',
                actors='["Иван Иванов", "Заслуженный артист России", '
                '"Сергей Смирнов"]',
                month=1,
                year=2024,
                show_name='S3',
            ),
        ]

        histories = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=20),
            ShowSeatHistory(
                show_id='s1', timestamp=20, seats=10
            ),  # s1 sold 10
            ShowSeatHistory(show_id='s2', timestamp=10, seats=30),
            ShowSeatHistory(
                show_id='s2', timestamp=20, seats=18
            ),  # s2 sold 12
            ShowSeatHistory(show_id='s3', timestamp=10, seats=25),
            ShowSeatHistory(show_id='s3', timestamp=20, seats=17),  # s3 sold 8
        ]

        result = analytics.top_artists_by_sales(shows, histories, n=10)

        # Проверяем, что титулы правильно обрабатываются
        titles = [
            'Народный артист России',
            'Народная артистка России',
            'лауреат Государственных премий',
            'Заслуженный артист России',
        ]

        # Титулы не должны быть в результате
        for title in titles:
            self.assertFalse(any(artist[0] == title for artist in result))

        # Проверяем, что актеры правильно учтены
        actors_expected = {
            'Олег Меньшиков': 10,
            'Иван Иванов': 18,  # 10 + 8 (участвует в s1 и s3)
            'Анна Петрова': 12,
            'Петр Сидоров': 12,
            'Сергей Смирнов': 8,
        }

        for artist, count in result:
            self.assertEqual(
                count,
                actors_expected.get(artist, 0),
                f'Неверное количество продаж для {artist}: {count} '
                f'(ожидалось {actors_expected.get(artist, 0)})',
            )

        # Проверяем общее количество артистов в результате
        self.assertEqual(
            len(result),
            len(actors_expected),
            f'Неверное количество артистов в результате: {len(result)} '
            f'(ожидалось {len(actors_expected)})',
        )

    def test_top_shows_by_current_sales_speed(self):
        shows_data = [
            Show(
                id='s1',
                show_name='Show Alpha',
                month=1,
                year=2024,
                actors='[]',
            ),
            Show(
                id='s1b',
                show_name='Show Alpha',
                month=1,
                year=2024,
                actors='[]',
            ),
            Show(
                id='s2', show_name='Show Beta', month=1, year=2024, actors='[]'
            ),
        ]
        histories_data = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=20, seats=7),
            ShowSeatHistory(show_id='s1', timestamp=30, seats=5),
            ShowSeatHistory(show_id='s1b', timestamp=10, seats=8),
            ShowSeatHistory(show_id='s1b', timestamp=20, seats=7),
            ShowSeatHistory(show_id='s1b', timestamp=30, seats=6),
            ShowSeatHistory(show_id='s2', timestamp=10, seats=20),
            ShowSeatHistory(show_id='s2', timestamp=20, seats=18),
            ShowSeatHistory(show_id='s2', timestamp=30, seats=17),
        ]
        top_speed = analytics.top_shows_by_current_sales_speed(
            shows_data, histories_data, n=2
        )
        # Нет валидных интервалов — результат пустой
        self.assertEqual(len(top_speed), 0)

        histories_data = [
            ShowSeatHistory(show_id='s1', timestamp=0, seats=10),
            ShowSeatHistory(
                show_id='s1', timestamp=1 * 3600, seats=7
            ),  # 3 билета за 1 час
            ShowSeatHistory(
                show_id='s1', timestamp=2 * 3600, seats=5
            ),  # 2 билета за 1 час
            ShowSeatHistory(show_id='s2', timestamp=0, seats=20),
            ShowSeatHistory(
                show_id='s2', timestamp=1 * 3600, seats=18
            ),  # 2 билета за 1 час
            ShowSeatHistory(
                show_id='s2', timestamp=2 * 3600, seats=17
            ),  # 1 билет за 1 час
        ]
        top_speed = analytics.top_shows_by_current_sales_speed(
            shows_data, histories_data, n=2
        )
        self.assertEqual(len(top_speed), 0)

    def test_shows_predicted_to_sell_out_soonest(self):
        from datetime import datetime, timedelta

        future_date = (datetime.now() + timedelta(days=10)).strftime(
            '%Y-%m-%d %H:%M'
        )
        shows_data = [
            Show(
                id='s1', show_name='Show Alpha', actors='[]', date=future_date
            ),
            Show(
                id='s2', show_name='Show Beta', actors='[]', date=future_date
            ),
            Show(
                id='s3', show_name='Show Gamma', actors='[]', date=future_date
            ),  # Already sold out
        ]

        # Короткие интервалы (10 сек) — не должно быть прогнозов
        histories_data_short = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=20, seats=7),
            ShowSeatHistory(show_id='s1', timestamp=30, seats=5),
            ShowSeatHistory(show_id='s2', timestamp=10, seats=20),
            ShowSeatHistory(show_id='s2', timestamp=20, seats=18),
            ShowSeatHistory(show_id='s2', timestamp=30, seats=17),
            ShowSeatHistory(show_id='s3', timestamp=10, seats=1),
            ShowSeatHistory(show_id='s3', timestamp=20, seats=0),
        ]
        predictions_short = analytics.shows_predicted_to_sell_out_soonest(
            shows_data, histories_data_short, n=3
        )
        self.assertEqual(len(predictions_short), 0)

        # Интервалы в 1 час (но только 2 интервала — прогнозов не будет)
        histories_data = [
            ShowSeatHistory(show_id='s1', timestamp=0, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=1 * 3600, seats=7),
            ShowSeatHistory(show_id='s1', timestamp=2 * 3600, seats=5),
            ShowSeatHistory(show_id='s2', timestamp=0, seats=20),
            ShowSeatHistory(show_id='s2', timestamp=1 * 3600, seats=18),
            ShowSeatHistory(show_id='s2', timestamp=2 * 3600, seats=17),
            ShowSeatHistory(show_id='s3', timestamp=0, seats=1),
            ShowSeatHistory(show_id='s3', timestamp=1 * 3600, seats=0),
        ]
        predictions = analytics.shows_predicted_to_sell_out_soonest(
            shows_data, histories_data, n=3
        )
        # Нет ни одного прогноза, т.к. везде <3 интервала
        self.assertEqual(len(predictions), 0)

    def test_predict_sold_out_future_and_past(self):
        from datetime import datetime, timedelta
        import pytz
        from config import settings

        tz = pytz.timezone(settings.DEFAULT_TIMEZONE)
        now = datetime.now(tz)

        hist = [
            ShowSeatHistory(
                show_id='s1',
                timestamp=int((now - timedelta(hours=3)).timestamp()),
                seats=120,
            ),
            ShowSeatHistory(
                show_id='s1',
                timestamp=int((now - timedelta(hours=2)).timestamp()),
                seats=100,
            ),
            ShowSeatHistory(
                show_id='s1',
                timestamp=int((now - timedelta(hours=1)).timestamp()),
                seats=80,
            ),
            ShowSeatHistory(show_id='s1', timestamp=int(now.timestamp()), seats=60),
        ]

        show_dt = now + timedelta(hours=5)
        future_pred = analytics.predict_sold_out(
            hist, show_dt, now_ts=int(now.timestamp())
        )
        self.assertIsNotNone(future_pred)
        self.assertGreater(future_pred, int(now.timestamp()))
        self.assertLessEqual(future_pred, int(show_dt.timestamp()))

        past_pred = analytics.predict_sold_out(
            hist, show_dt, now_ts=future_pred
        )
        self.assertIsNone(past_pred)

    def test_shows_predicted_to_sell_out_returns_show_date(self):
        from datetime import datetime, timedelta
        import pytz
        from config import settings

        tz = pytz.timezone(settings.DEFAULT_TIMEZONE)
        now = datetime.now(tz)
        show_date = (now + timedelta(hours=4)).strftime('%Y-%m-%d %H:%M')

        shows_data = [Show(id='s1', show_name='Alpha', actors='[]', date=show_date)]

        histories = [
            ShowSeatHistory(
                show_id='s1',
                timestamp=int((now - timedelta(hours=3)).timestamp()),
                seats=100,
            ),
            ShowSeatHistory(
                show_id='s1',
                timestamp=int((now - timedelta(hours=2)).timestamp()),
                seats=80,
            ),
            ShowSeatHistory(
                show_id='s1',
                timestamp=int((now - timedelta(hours=1)).timestamp()),
                seats=60,
            ),
            ShowSeatHistory(show_id='s1', timestamp=int(now.timestamp()), seats=40),
        ]

        predictions = analytics.shows_predicted_to_sell_out_soonest(
            shows_data, histories, n=1
        )
        self.assertEqual(len(predictions), 1)
        name, pred_ts, _id, returned_date = predictions[0]
        self.assertEqual(returned_date, show_date)
        self.assertGreater(pred_ts, int(now.timestamp()))
