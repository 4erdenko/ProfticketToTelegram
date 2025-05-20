# Все импорты должны быть в начале файла
import datetime
import sys
import types

import pytest

# --- PYTZ MOCK (глобально, до любых импортов) ---
pytz = types.ModuleType('pytz')


class MockTimezone(datetime.tzinfo):
    def localize(self, dt: datetime.datetime) -> datetime.datetime:
        return dt.replace(tzinfo=self)

    def utcoffset(self, dt):
        return datetime.timedelta(hours=3)  # Moscow offset

    def dst(self, dt):
        return datetime.timedelta(0)


def mock_timezone(tz):
    return MockTimezone()


pytz.timezone = mock_timezone
sys.modules['pytz'] = pytz
# --- END PYTZ MOCK ---


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
        MAX_CONSECUTIVE_ERRORS = 3

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
    aiogram.types = aiogram_types  # Добавляем types как атрибут aiogram
    modules['aiogram'] = aiogram
    modules['aiogram.types'] = aiogram_types

    sys.modules.update(modules)
    yield
    for name in modules:
        sys.modules.pop(name, None)
