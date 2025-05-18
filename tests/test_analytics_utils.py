import unittest
from datetime import datetime

from services.profticket.analytics import (_calculate_real_sales_from_history,
                                           _calculate_returns_from_history,
                                           _calculate_show_sales_from_history,
                                           _get_show_details,
                                           filter_data_by_period,
                                           parse_show_date)
from telegram.db.models import Show, ShowSeatHistory


class AnalyticsUtilsTestCase(unittest.TestCase):
    def setUp(self):
        self.shows = [
            Show(id='s1', show_name='Alpha', month=1, year=2024, actors='[]'),
            Show(id='s2', show_name='Beta', month=2, year=2024, actors='[]'),
        ]
        self.histories = [
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=20, seats=8),
            ShowSeatHistory(show_id='s2', timestamp=10, seats=20),
            ShowSeatHistory(show_id='s2', timestamp=20, seats=15),
        ]

    def test_filter_data_by_period_all(self):
        filtered_shows, buckets = filter_data_by_period(
            self.shows, self.histories, None, None
        )
        self.assertEqual(len(filtered_shows), 2)
        self.assertIn('s1', buckets)
        self.assertIn('s2', buckets)
        self.assertEqual(len(buckets['s1']), 2)
        self.assertEqual(len(buckets['s2']), 2)

    def test_filter_data_by_period_month(self):
        filtered_shows, buckets = filter_data_by_period(
            self.shows, self.histories, 1, 2024
        )
        self.assertEqual(len(filtered_shows), 1)
        self.assertEqual(filtered_shows[0].id, 's1')
        self.assertIn('s1', buckets)
        self.assertNotIn('s2', buckets)

    def test_parse_show_date(self):
        dt = parse_show_date('2024-07-01 19:00')
        self.assertIsInstance(dt, datetime)
        dt2 = parse_show_date('2024-07-01T19:00:00')
        self.assertIsInstance(dt2, datetime)
        self.assertIsNone(parse_show_date('not a date'))

    def test_get_show_details(self):
        show = _get_show_details('s1', self.shows)
        self.assertIsNotNone(show)
        self.assertEqual(show.show_name, 'Alpha')
        self.assertIsNone(_get_show_details('nope', self.shows))

    def test_calculate_show_sales_from_history(self):
        # 10 -> 8, sold 2
        sales = _calculate_show_sales_from_history(
            [
                ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
                ShowSeatHistory(show_id='s1', timestamp=20, seats=8),
            ]
        )
        self.assertEqual(sales, 2)
        # Only one record
        self.assertEqual(
            _calculate_show_sales_from_history(
                [ShowSeatHistory(show_id='s1', timestamp=10, seats=10)]
            ),
            0,
        )
        # No sales (seats increased)
        self.assertEqual(
            _calculate_show_sales_from_history(
                [
                    ShowSeatHistory(show_id='s1', timestamp=10, seats=8),
                    ShowSeatHistory(show_id='s1', timestamp=20, seats=10),
                ]
            ),
            0,
        )

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
        old_method = _calculate_show_sales_from_history(history)
        self.assertEqual(old_method, 15)

        # Новый метод (суммирование всех интервалов продаж): 10 + 10 = 20
        real_sales = _calculate_real_sales_from_history(history)
        self.assertEqual(real_sales, 20)

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
        old_method = _calculate_show_sales_from_history(history)
        self.assertEqual(old_method, 0)

        # Новый метод: нет продаж, только возвраты
        real_sales = _calculate_real_sales_from_history(history)
        self.assertEqual(real_sales, 0)

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
        old_method = _calculate_show_sales_from_history(history)
        self.assertEqual(old_method, 20)

        # Новый метод: 10 + 10 + 10 = 30
        real_sales = _calculate_real_sales_from_history(history)
        self.assertEqual(real_sales, 30)

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

        # Функция должна подсчитать только возвраты: 5
        returns = _calculate_returns_from_history(history)
        self.assertEqual(returns, 5)

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

        returns = _calculate_returns_from_history(history)
        self.assertEqual(returns, 15)  # 10 + 5

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

        returns = _calculate_returns_from_history(history)
        self.assertEqual(returns, 10)  # 5 + 5

        # Проверяем, что продажи и возвраты считаются правильно
        sales = _calculate_real_sales_from_history(history)
        self.assertEqual(sales, 30)  # 10 + 10 + 10

        net_change = history[0].seats - history[-1].seats
        self.assertEqual(
            net_change, sales - returns
        )  # 100 - 80 = 30 - 10 = 20


if __name__ == '__main__':
    unittest.main()
