import unittest
import types
import sys

sys.modules['aiogram'].Bot = type('Bot', (), {})

from services.profticket.profticket_snapshoter import ShowUpdateService
from telegram.db.models import Show, PriceHistory

class FakeProfticket:
    def __init__(self, data):
        self.data = data
    def set_date(self, m, y):
        pass
    async def collect_full_info(self):
        return self.data

class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)

class FakeResult:
    def __init__(self, items):
        self._items = items
    def scalars(self):
        return self._items
    def scalar(self):
        return self._items[0] if self._items else None

class FakeSession:
    def __init__(self):
        self.shows = {}
        self.price_history = []
    async def execute(self, stmt):
        from sqlalchemy.sql import Select, Delete
        from sqlalchemy.sql.dml import Insert
        if isinstance(stmt, Select):
            table = stmt.get_final_froms()[0].name
            if table == 'shows':
                return FakeResult([Obj(**v) for v in self.shows.values()])
            elif table == 'price_history':
                return FakeResult([Obj(**v) for v in self.price_history])
        elif isinstance(stmt, Insert):
            vals = {k: v for k, v in stmt.compile().params.items() if not k.startswith('param_')}
            if stmt.table.name == 'shows':
                self.shows[vals['id']] = vals
            elif stmt.table.name == 'price_history':
                self.price_history.append(vals)
            return FakeResult([])
        elif isinstance(stmt, Delete):
            ids = stmt.compile().params.get('id_1', [])
            for sid in list(self.shows):
                if sid not in ids:
                    del self.shows[sid]
            return FakeResult([])
        return FakeResult([])
    async def commit(self):
        pass
    async def rollback(self):
        pass

class PriceHistoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_record_on_price_change(self):
        data = {
            '1': {
                'show_id': 1,
                'theater': '',
                'scene': '',
                'show_name': 'n',
                'date': 'd',
                'duration': '',
                'age': '',
                'seats': 0,
                'image': '',
                'annotation': '',
                'min_price': 100,
                'max_price': 200,
                'pushkin': False,
                'buy_link': '',
                'actors': [],
            }
        }
        session = FakeSession()
        bot = types.SimpleNamespace(send_message=lambda *a, **kw: None)
        srv = ShowUpdateService(None, FakeProfticket(data), bot)
        await srv._update_month_data(session, 5, 2024)
        data['1']['min_price'] = 150
        data['1']['max_price'] = 250
        await srv._update_month_data(session, 5, 2024)
        self.assertEqual(len(session.price_history), 2)

    async def test_no_duplicate_when_price_same(self):
        data = {
            '1': {
                'show_id': 1,
                'theater': '',
                'scene': '',
                'show_name': 'n',
                'date': 'd',
                'duration': '',
                'age': '',
                'seats': 0,
                'image': '',
                'annotation': '',
                'min_price': 100,
                'max_price': 200,
                'pushkin': False,
                'buy_link': '',
                'actors': [],
            }
        }
        session = FakeSession()
        bot = types.SimpleNamespace(send_message=lambda *a, **kw: None)
        srv = ShowUpdateService(None, FakeProfticket(data), bot)
        await srv._update_month_data(session, 5, 2024)
        await srv._update_month_data(session, 5, 2024)
        self.assertEqual(len(session.price_history), 1)

if __name__ == '__main__':
    unittest.main()
