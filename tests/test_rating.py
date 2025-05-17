import unittest
import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from telegram.db.base import Base
from telegram.db.models import Show, User
from telegram.db.user_operations import get_top_shows_and_actors


class RatingTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.SyncSession = sessionmaker(bind=self.engine)

    async def asyncTearDown(self):
        self.engine.dispose()

    async def test_rating(self):
        sync_session = self.SyncSession()

        class DummyAsyncSession:
            def __init__(self, s):
                self.s = s

            async def execute(self, *a, **k):
                return self.s.execute(*a, **k)

            async def commit(self):
                self.s.commit()

            async def get(self, *a, **k):
                return self.s.get(*a, **k)

            def add_all(self, *a, **k):
                self.s.add_all(*a, **k)

        session = DummyAsyncSession(sync_session)
        now = int(datetime.utcnow().timestamp())

        show1 = Show(
            id='1',
            show_id=1,
            show_name='A',
            date='',
            seats=50,
            previous_seats=100,
            actors=json.dumps(['Actor1', 'Actor2']),
            month=5,
            year=2024,
            updated_at=now,
        )
        show2 = Show(
            id='2',
            show_id=2,
            show_name='B',
            date='',
            seats=10,
            previous_seats=20,
            actors=json.dumps(['Actor2']),
            month=5,
            year=2024,
            updated_at=now,
        )
        session.add_all([show1, show2])

        user1 = User(user_id=1, spectacle_full_name='Actor2', search_count=3)
        user2 = User(user_id=2, spectacle_full_name='Actor3', search_count=1)
        session.add_all([user1, user2])
        await session.commit()

        top_shows, top_actors = await get_top_shows_and_actors(session, months=1, limit=2)

        self.assertEqual(top_shows, [('A', 50), ('B', 10)])
        self.assertEqual(top_actors[0], ('actor2', 63))
        self.assertEqual(top_actors[1], ('actor1', 50))


if __name__ == '__main__':
    unittest.main()
