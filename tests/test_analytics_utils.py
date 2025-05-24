import unittest
from datetime import datetime

from services.profticket.analytics import (calendar_pace_dashboard,
                                           filter_data_by_period,
                                           get_net_sales_and_returns,
                                           parse_show_date)
from telegram.db.models import Show, ShowSeatHistory


def old_calc_sales(history):
    if len(history) < 2:
        return 0
    diff = history[0].seats - history[-1].seats
    return diff if diff > 0 else 0


class AnalyticsUtilsTestCase(unittest.TestCase):
    def setUp(self):
        self.shows = [
            Show(id='s1', show_name='Alpha', month=1, year=2024, actors='[]'),
            Show(id='s2', show_name='Beta', month=2, year=2024, actors='[]'),
            Show(
                id='s3',
                show_name='Gamma',
                month=1,
                year=2024,
                actors='[]',
                is_deleted=True,
            ),
        ]
        self.histories = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=20, seats=8),
            ShowSeatHistory(show_id='s2', timestamp=10, seats=20),
            ShowSeatHistory(show_id='s2', timestamp=20, seats=15),
            ShowSeatHistory(show_id='s3', timestamp=10, seats=5),
            ShowSeatHistory(show_id='s3', timestamp=20, seats=0),
        ]

    def test_filter_data_by_period_all(self):
        filtered_shows, buckets = filter_data_by_period(
            self.shows, self.histories, None, None
        )
        # Deleted shows are excluded by default
        self.assertEqual(len(filtered_shows), 2)
        self.assertIn('s1', buckets)
        self.assertIn('s2', buckets)
        self.assertNotIn('s3', buckets)
        self.assertEqual(len(buckets['s1']), 2)
        self.assertEqual(len(buckets['s2']), 2)

    def test_filter_data_by_period_month(self):
        filtered_shows, buckets = filter_data_by_period(
            self.shows, self.histories, 1, 2024
        )
        self.assertEqual(len(filtered_shows), 1)
        self.assertEqual(filtered_shows[0].id, 's1')
        # Теперь bucket всегда содержит все истории для show_id
        self.assertIn('s1', buckets)
        self.assertEqual(len(buckets['s1']), 2)
        self.assertNotIn('s3', buckets)

    def test_parse_show_date(self):
        dt = parse_show_date('2024-07-01 19:00')
        self.assertIsInstance(dt, datetime)
        dt2 = parse_show_date('2024-07-01T19:00:00')
        self.assertIsInstance(dt2, datetime)
        self.assertIsNone(parse_show_date('not a date'))

    def test_calculate_show_sales_from_history(self):
        # 10 -> 8, sold 2
        sold, returned = get_net_sales_and_returns(
            [
                ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
                ShowSeatHistory(show_id='s1', timestamp=20, seats=8),
            ]
        )
        self.assertEqual(sold, 2)
        self.assertEqual(returned, 0)

        # Only one record
        sold, returned = get_net_sales_and_returns(
            [ShowSeatHistory(show_id='s1', timestamp=10, seats=10)]
        )
        self.assertEqual(sold, 0)
        self.assertEqual(returned, 0)

        # No sales (seats increased)
        sold, returned = get_net_sales_and_returns(
            [
                ShowSeatHistory(show_id='s1', timestamp=10, seats=8),
                ShowSeatHistory(show_id='s1', timestamp=20, seats=10),
            ]
        )
        self.assertEqual(sold, 0)
        self.assertEqual(returned, 2)

    def test_calculate_real_sales_with_returns(self):
        # Сценарий с возвратами - должен считать все продажи
        history = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=100),  # Начало
            ShowSeatHistory(
                show_id='s1', timestamp=20, seats=90
            ),  # Продано 10
            ShowSeatHistory(
                show_id='s1', timestamp=30, seats=95
            ),  # Возвращено 5
            ShowSeatHistory(
                show_id='s1', timestamp=40, seats=85
            ),  # Продано ещё 10
        ]
        # Старый метод (разница начала и конца): 100 - 85 = 15
        old_method = old_calc_sales(history)
        self.assertEqual(old_method, 15)

        sold, returned = get_net_sales_and_returns(history)
        self.assertEqual(sold, 20)  # 10 + 10
        self.assertEqual(returned, 5)

    def test_calculate_real_sales_only_returns(self):
        # Сценарий только с возвратами
        history = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=100),
            ShowSeatHistory(
                show_id='s1', timestamp=20, seats=110
            ),  # Возврат 10
            ShowSeatHistory(
                show_id='s1', timestamp=30, seats=115
            ),  # Возврат ещё 5
        ]
        # Старый метод: отрицательная разница, вернёт 0
        old_method = old_calc_sales(history)
        self.assertEqual(old_method, 0)

        sold, returned = get_net_sales_and_returns(history)
        self.assertEqual(sold, 0)
        self.assertEqual(returned, 15)

    def test_calculate_real_sales_complex_pattern(self):
        # Сложный пример: продажи-возвраты-продажи-возвраты
        history = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=100),
            ShowSeatHistory(
                show_id='s1', timestamp=20, seats=90
            ),  # Продано 10
            ShowSeatHistory(show_id='s1', timestamp=30, seats=95),  # Возврат 5
            ShowSeatHistory(
                show_id='s1', timestamp=40, seats=85
            ),  # Продано 10
            ShowSeatHistory(show_id='s1', timestamp=50, seats=90),  # Возврат 5
            ShowSeatHistory(
                show_id='s1', timestamp=60, seats=80
            ),  # Продано 10
        ]
        # Старый метод: 100 - 80 = 20
        old_method = old_calc_sales(history)
        self.assertEqual(old_method, 20)

        sold, returned = get_net_sales_and_returns(history)
        self.assertEqual(sold, 30)  # 10 + 10 + 10
        self.assertEqual(returned, 10)

    def test_calculate_returns(self):
        # Сценарий с возвратами
        history = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=100),  # Начало
            ShowSeatHistory(
                show_id='s1', timestamp=20, seats=90
            ),  # Продано 10
            ShowSeatHistory(
                show_id='s1', timestamp=30, seats=95
            ),  # Возвращено 5
            ShowSeatHistory(
                show_id='s1', timestamp=40, seats=85
            ),  # Продано ещё 10
        ]

        sold, returned = get_net_sales_and_returns(history)
        self.assertEqual(sold, 20)
        self.assertEqual(returned, 5)

    def test_calculate_returns_only_returns(self):
        # Сценарий только с возвратами
        history = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=100),
            ShowSeatHistory(
                show_id='s1', timestamp=20, seats=110
            ),  # Возврат 10
            ShowSeatHistory(
                show_id='s1', timestamp=30, seats=115
            ),  # Возврат ещё 5
        ]

        sold, returned = get_net_sales_and_returns(history)
        self.assertEqual(sold, 0)
        self.assertEqual(returned, 15)  # 10 + 5

    def test_calculate_returns_complex(self):
        # Сложный сценарий: продажи-возвраты-продажи-возвраты
        history = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=100),
            ShowSeatHistory(
                show_id='s1', timestamp=20, seats=90
            ),  # Продано 10
            ShowSeatHistory(show_id='s1', timestamp=30, seats=95),  # Возврат 5
            ShowSeatHistory(
                show_id='s1', timestamp=40, seats=85
            ),  # Продано 10
            ShowSeatHistory(show_id='s1', timestamp=50, seats=90),  # Возврат 5
            ShowSeatHistory(
                show_id='s1', timestamp=60, seats=80
            ),  # Продано 10
        ]

        sold, returned = get_net_sales_and_returns(history)
        self.assertEqual(returned, 10)  # 5 + 5
        self.assertEqual(sold, 30)  # 10 + 10 + 10

        net_change = history[0].seats - history[-1].seats
        # 100 - 80 = 30 - 10 = 20
        self.assertEqual(net_change, sold - returned)

    def test_calendar_pace_dashboard_with_n_parameter(self):
        """Тест что функция calendar_pace_dashboard
        принимает параметр n без ошибок"""

        # Создаем тестовые данные
        shows = [
            Show(
                id='s1',
                show_name='Test Show 1',
                month=5,
                year=2024,
                date='2024-05-15 19:00',
                actors='[]',
            ),
            Show(
                id='s2',
                show_name='Test Show 2',
                month=5,
                year=2024,
                date='2024-05-16 19:00',
                actors='[]',
            ),
        ]

        histories = [
            ShowSeatHistory(show_id='s1', timestamp=1000, seats=100),
            ShowSeatHistory(show_id='s1', timestamp=2000, seats=90),  # sold 10
            ShowSeatHistory(
                show_id='s1', timestamp=3000, seats=95
            ),  # returned 5
            ShowSeatHistory(show_id='s2', timestamp=1000, seats=80),
            ShowSeatHistory(show_id='s2', timestamp=2000, seats=70),  # sold 10
        ]

        # Тест что функция принимает параметр n
        result = calendar_pace_dashboard(
            shows=shows,
            histories=histories,
            month=5,
            year=2024,
            n=10,  # Этот параметр должен приниматься без ошибок
        )

        # Проверяем что результат имеет ожидаемую структуру
        self.assertIsInstance(result, dict)
        self.assertIn('dates', result)
        self.assertIn('gross_sales', result)
        self.assertIn('net_sales', result)
        self.assertIn('refunds', result)
        self.assertIn('show_names', result)

        # Проверяем что данные корректны
        self.assertEqual(len(result['dates']), 2)
        self.assertEqual(result['gross_sales'][0], 10)  # s1 sold 10 gross
        self.assertEqual(
            result['net_sales'][0], 5
        )     # s1 net = 10 - 5 returns = 5
        self.assertEqual(result['refunds'][0], 5)       # s1 returned 5
        self.assertEqual(result['gross_sales'][1], 10)  # s2 sold 10
        self.assertEqual(result['net_sales'][1], 10)    # s2 no returns
        self.assertEqual(result['refunds'][1], 0)       # s2 no returns


if __name__ == '__main__':
    unittest.main()
