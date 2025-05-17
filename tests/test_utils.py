import unittest

from services.profticket.profticket_api import ProfticketsInfo
from services.profticket import utils as pt_utils
from telegram import tg_utils


class UtilsTestCase(unittest.TestCase):
    def test_pluralize(self):
        self.assertEqual(pt_utils.pluralize('word', 2), 'word_2')

    def test_generate_buy_link(self):
        api = ProfticketsInfo('42')
        link = api._generate_buy_link('e1', 's1')
        exp = (
            f'{api.CUSTOMER_BUY_URL}42/shows/s1?eventsIds%5B%5D=e1&language=ru-RU'
        )
        self.assertEqual(link, exp)

    def test_create_url_without_date(self):
        api = ProfticketsInfo('42')
        with self.assertRaises(ValueError):
            api._create_url(1)

    def test_create_url_with_date(self):
        api = ProfticketsInfo('42')
        api.set_date(5, 2024)
        url = api._create_url(2)
        exp = (
            "https://widget.profticket.ru/api/event/list/?company_id=42"
            "&type=events&page=2&period_id=4&hall_id=&date=2024.5&name=&language=ru-RU"
        )
        self.assertEqual(url, exp)

    def test_get_headers(self):
        api = ProfticketsInfo('42')
        api.user_agent_provider.get_random_user_agent = lambda: 'UA'
        headers = api._get_headers()
        self.assertEqual(headers['User-Agent'], 'UA')

    def test_split_message_by_separator(self):
        text = (
            'a\n------------------------\nb\n'
            '------------------------\nc'
        )
        parts = tg_utils.split_message_by_separator(text, max_length=40)
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[0].endswith('------------------------'))

    def test_parse_show_date(self):
        d1 = tg_utils.parse_show_date('18 мая 2025, вс, 16:00')
        d2 = tg_utils.parse_show_date('20 мая 2025, вт, 20:00')
        self.assertLess(d1, d2)


class CheckTextTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_check_text(self):
        msg = tg_utils.Message('Тест Тестович!!!')
        self.assertEqual(await tg_utils.check_text(msg), 'тест тестович')

    async def test_check_text_invalid(self):
        msg = tg_utils.Message('invalid')
        self.assertIsNone(await tg_utils.check_text(msg))


if __name__ == '__main__':
    unittest.main()
