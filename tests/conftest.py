import sys
import types

import pytest


@pytest.fixture(autouse=True)
def stub_modules(monkeypatch):
    modules = {}

    # config settings stub
    config = types.ModuleType('config')

    class Settings:
        COM_ID = '1'
        MAX_MSG_LEN = 100
        ADMIN_ID = 1
        ADMIN_USERNAME = 'admin'
        PROXY_URL = ''
        STOP_AFTER_ATTEMPT = 3
        DEFAULT_TIMEZONE = 'Europe/Moscow'

    config.settings = Settings()
    modules['config'] = config

    # required external modules
    pymorphy2 = types.ModuleType('pymorphy2')

    class MorphAnalyzer:
        def parse(self, word):
            class Res:
                def __init__(self, w):
                    self.w = w

                def make_agree_with_number(self, num):
                    class Word:
                        def __init__(self, txt):
                            self.word = txt

                    return Word(f'{self.w}_{num}')

            return [Res(word)]

    pymorphy2.MorphAnalyzer = MorphAnalyzer
    modules['pymorphy2'] = pymorphy2

    httpx = types.ModuleType('httpx')

    class AsyncClient:
        def __init__(self, *a, **kw):
            pass

    httpx.AsyncClient = AsyncClient

    class Limits:
        def __init__(self, *a, **kw):
            pass

    httpx.Limits = Limits
    httpx.TimeoutException = Exception
    httpx.ProxyError = Exception
    httpx.HTTPStatusError = Exception
    modules['httpx'] = httpx

    aiosqlite = types.ModuleType('aiosqlite')

    class DummyCursor:
        def __init__(self, cur):
            self._cur = cur

        async def execute(self, *a, **kw):
            self._cur.execute(*a, **kw)
            return self

        async def fetchone(self):
            return self._cur.fetchone()

        async def fetchall(self):
            return self._cur.fetchall()

        async def close(self):
            self._cur.close()

    class DummyConnection:
        def __init__(self, connection):
            import asyncio
            self._conn = connection
            self._tx = asyncio.Queue()

        async def execute(self, *a, **kw):
            return self._conn.execute(*a, **kw)

        async def commit(self):
            self._conn.commit()

        async def close(self):
            self._conn.close()

        async def cursor(self):
            return DummyCursor(self._conn.cursor())

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await self.close()

    class ConnectAwaitable:
        def __init__(self, conn):
            self._conn = conn
            self.daemon = True

        def __await__(self):
            async def _wrap():
                return self._conn

            return _wrap().__await__()

    def connect(*a, **kw):
        import sqlite3
        conn = sqlite3.connect(':memory:')
        return ConnectAwaitable(DummyConnection(conn))

    aiosqlite.connect = connect
    aiosqlite.Connection = DummyConnection
    # minimal error attributes for SQLAlchemy
    aiosqlite.Error = Exception
    aiosqlite.DatabaseError = Exception
    aiosqlite.IntegrityError = Exception
    aiosqlite.NotSupportedError = Exception
    aiosqlite.OperationalError = Exception
    aiosqlite.ProgrammingError = Exception
    aiosqlite.sqlite_version = '3.0'
    aiosqlite.sqlite_version_info = (3, 0, 0)
    modules['aiosqlite'] = aiosqlite

    fake_useragent = types.ModuleType('fake_useragent')

    class UserAgent:
        @property
        def random(self):
            return 'agent'

    fake_useragent.UserAgent = UserAgent
    modules['fake_useragent'] = fake_useragent

    tenacity = types.ModuleType('tenacity')
    tenacity.retry = lambda *a, **k: (lambda f: f)
    tenacity.retry_if_exception_type = lambda *a, **k: None
    tenacity.stop_after_attempt = lambda *a, **k: None
    tenacity.wait_exponential = lambda *a, **k: None
    modules['tenacity'] = tenacity

    pytz = types.ModuleType('pytz')
    pytz.timezone = lambda tz: None
    modules['pytz'] = pytz

    dateutil = types.ModuleType('dateutil')
    rdelta = types.ModuleType('dateutil.relativedelta')

    class relativedelta:
        def __init__(self, *a, **k):
            pass

    rdelta.relativedelta = relativedelta
    modules['dateutil.relativedelta'] = rdelta
    modules['dateutil'] = dateutil

    aiogram = types.ModuleType('aiogram')
    aiogram_types = types.ModuleType('aiogram.types')

    class Message:
        def __init__(self, text=''):
            self.text = text

    aiogram_types.Message = Message
    modules['aiogram'] = aiogram
    modules['aiogram.types'] = aiogram_types

    sys.modules.update(modules)
    yield
    for name in modules:
        sys.modules.pop(name, None)
