import unittest
import sys
import types
from sqlalchemy import select, create_engine
from sqlalchemy.orm import sessionmaker

from telegram.db.base import Base
from telegram.db.models import ShowSeatHistory

aiogram = sys.modules.get('aiogram')
if aiogram is None:
    aiogram = types.ModuleType('aiogram')
    sys.modules['aiogram'] = aiogram
aiogram.Bot = type('Bot', (), {})

from services.profticket.profticket_snapshoter import ShowUpdateService


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


class SeatHistoryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.sync_maker = sessionmaker(self.engine)

    async def asyncTearDown(self):
        self.engine.dispose()

    async def test_history_inserted(self):
        data = {
            'e1': {
                'show_id': '1',
                'theater': 't',
                'scene': 's',
                'show_name': 'n',
                'date': 'd',
                'duration': '1',
                'age': '0',
                'seats': 5,
                'image': '',
                'annotation': '',
                'min_price': 0,
                'max_price': 0,
                'pushkin': False,
                'buy_link': '',
                'actors': [],
            }
        }
        service = ShowUpdateService(None, DummyProfticket(data), DummyBot())

        sync_session = self.sync_maker()

        class FakeAsyncSession:
            def __init__(self, session):
                self._s = session

            async def execute(self, *a, **kw):
                return self._s.execute(*a, **kw)

            async def commit(self):
                self._s.commit()

            async def rollback(self):
                self._s.rollback()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                self._s.close()

        session = FakeAsyncSession(sync_session)

        await service._update_month_data(session, 1, 2024)
        res = await session.execute(select(ShowSeatHistory))
        history = res.scalar_one()
        self.assertEqual(history.show_id, 'e1')
        self.assertEqual(history.seats, 5)


if __name__ == '__main__':
    unittest.main()
