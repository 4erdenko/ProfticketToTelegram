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
        # Короткие интервалы (10 сек) — должны быть проигнорированы, результат None
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
        median_rate = (3/3600 + 2/3600) / 2
        self.assertAlmostEqual(rate, median_rate, places=7)

    def test_predict_sold_out(self):
        # Короткие интервалы (10 сек) — должны быть проигнорированы, результат None
        history_s1 = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=20, seats=7),
            ShowSeatHistory(show_id='s1', timestamp=30, seats=5),
        ]
        pred = analytics.predict_sold_out(history_s1)
        self.assertIsNone(pred)

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
        pred = analytics.predict_sold_out(history_s2)
        # Медиана между 3/3600 и 2/3600
        median_rate = (3/3600 + 2/3600) / 2
        last_timestamp = 2 * 3600
        expected_pred = last_timestamp + 5 / median_rate
        self.assertAlmostEqual(pred, expected_pred, delta=10)

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
        self.assertEqual(len(top_all_time), 3)
        self.assertEqual(top_all_time[0][0], 'Show Gamma')
        self.assertEqual(top_all_time[0][1], 10)
        self.assertEqual(top_all_time[1][0], 'Show Alpha')
        self.assertEqual(top_all_time[1][1], 7)
        self.assertEqual(top_all_time[2][0], 'Show Beta')
        self.assertEqual(top_all_time[2][1], 3)
        self.assertEqual(
            len([x for x in top_all_time if x[0] == 'Show Alpha']), 1
        )

        top_month1 = analytics.top_shows_by_sales(
            shows_data, histories_data, month=1, year=2024, n=2
        )
        self.assertEqual(len(top_month1), 2)
        self.assertEqual(top_month1[0], ('Show Alpha', 7, 's1'))
        self.assertEqual(top_month1[1], ('Show Beta', 3, 's2'))

        histories_no_sales = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10)
        ]  # only one record
        top_no_sales = analytics.top_shows_by_sales(
            shows_data, histories_no_sales, n=1
        )
        self.assertEqual(len(top_no_sales), 0)

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

        result_all_time = analytics.top_artists_by_sales(shows, histories, n=4)
        # All time: Alice=15, Bob=10, Charlie=10, David=10 (s4)
        expected_all_time = sorted(
            [('Alice', 15), ('Bob', 10), ('Charlie', 10), ('David', 10)],
            key=lambda x: (-x[1], x[0]),
        )
        self.assertEqual(result_all_time, expected_all_time)

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
        # Все еще должно быть 0 результатов, т.к. интервал < 1 часа
        self.assertEqual(len(top_speed), 0)

        # Теперь добавим интервалы в 1 час (новый минимум)
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
        self.assertEqual(len(top_speed), 2)
        # Проверяем, что Show Alpha выше Show Beta по скорости
        self.assertEqual(top_speed[0][0], 'Show Alpha')
        self.assertEqual(top_speed[1][0], 'Show Beta')
        # Проверяем диапазон скоростей (не больше 5 билетов/час)
        for name, rate, _ in top_speed:
            rate_per_hour = rate * 3600
            self.assertLessEqual(rate_per_hour, 5.0)
            self.assertGreater(rate_per_hour, 0.0)
        # Проверяем, что медиана для Show Alpha: (3/3600, 2/3600) -> медиана = 2.5/3600
        expected_median_alpha = (3/3600 + 2/3600) / 2
        self.assertAlmostEqual(top_speed[0][1], expected_median_alpha, places=7)
        # Для Show Beta: (2/3600, 1/3600) -> медиана = 1.5/3600
        expected_median_beta = (2/3600 + 1/3600) / 2
        self.assertAlmostEqual(top_speed[1][1], expected_median_beta, places=7)

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
        
        # Короткие интервалы (10 сек) — должны быть проигнорированы
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
        
        # При коротких интервалах не должно быть прогнозов
        predictions_short = analytics.shows_predicted_to_sell_out_soonest(
            shows_data, histories_data_short, n=3
        )
        self.assertEqual(len(predictions_short), 0)
        
        # Интервалы в 1 час (новый минимум)
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
            
            ShowSeatHistory(show_id='s3', timestamp=0, seats=1),
            ShowSeatHistory(
                show_id='s3', timestamp=1 * 3600, seats=0
            ),  # Уже распродано
        ]
        
        predictions = analytics.shows_predicted_to_sell_out_soonest(
            shows_data, histories_data, n=3
        )
        
        # Должно быть 2 прогноза (s3 уже распродано)
        self.assertEqual(len(predictions), 2)
        
        # Проверяем порядок: Show Alpha должен быть первым, т.к. медиана скорости продаж выше
        self.assertEqual(predictions[0][0], 'Show Alpha')
        self.assertEqual(predictions[1][0], 'Show Beta')
        
        # Проверяем прогнозы более гибко
        # Show Alpha: медиана = 2.5/3600, осталось 5 билетов, 5/(2.5/3600) = 7200 секунд
        last_timestamp_s1 = 2 * 3600
        expected_s1_sold_out = last_timestamp_s1 + 5 / ((3/3600 + 2/3600)/2)
        self.assertAlmostEqual(
            predictions[0][1], int(expected_s1_sold_out), delta=10
        )
        
        # Show Beta: медиана = 1.5/3600, осталось 17 билетов, 17/(1.5/3600) = ~40800 секунд
        last_timestamp_s2 = 2 * 3600
        expected_s2_sold_out = last_timestamp_s2 + 17 / ((2/3600 + 1/3600)/2)
        self.assertAlmostEqual(
            predictions[1][1], int(expected_s2_sold_out), delta=10
        )
