import unittest
from datetime import datetime

from telegram.utils import prediction


class SoldOutPredictionTestCase(unittest.TestCase):
    def tearDown(self):
        prediction.SHOW_SEAT_HISTORY.clear()

    def test_linear_prediction(self):
        show_id = 's1'
        base = 1000
        prediction.SHOW_SEAT_HISTORY[show_id] = [
            (base, 10),
            (base + 100, 8),
            (base + 200, 6),
        ]
        est = prediction.estimate_sold_out_date(show_id)
        self.assertIsNotNone(est)
        self.assertEqual(int(est.timestamp()), base + 500)


if __name__ == '__main__':
    unittest.main()
