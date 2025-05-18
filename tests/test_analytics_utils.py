import unittest
from services.profticket.analytics import filter_data_by_period, parse_show_date, _get_show_details, _calculate_show_sales_from_history
from telegram.db.models import Show, ShowSeatHistory
from datetime import datetime

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
        filtered_shows, buckets = filter_data_by_period(self.shows, self.histories, None, None)
        self.assertEqual(len(filtered_shows), 2)
        self.assertIn('s1', buckets)
        self.assertIn('s2', buckets)
        self.assertEqual(len(buckets['s1']), 2)
        self.assertEqual(len(buckets['s2']), 2)

    def test_filter_data_by_period_month(self):
        filtered_shows, buckets = filter_data_by_period(self.shows, self.histories, 1, 2024)
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
        sales = _calculate_show_sales_from_history([
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10),
            ShowSeatHistory(show_id='s1', timestamp=20, seats=8),
        ])
        self.assertEqual(sales, 2)
        # Only one record
        self.assertEqual(_calculate_show_sales_from_history([
            ShowSeatHistory(show_id='s1', timestamp=10, seats=10)
        ]), 0)
        # No sales (seats increased)
        self.assertEqual(_calculate_show_sales_from_history([
            ShowSeatHistory(show_id='s1', timestamp=10, seats=8),
            ShowSeatHistory(show_id='s1', timestamp=20, seats=10),
        ]), 0)

if __name__ == '__main__':
    unittest.main() 