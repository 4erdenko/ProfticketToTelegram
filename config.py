import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Bot
    IN_DOCKER: str
    BOT_TOKEN: str
    TEST_BOT_TOKEN: str
    ADMIN_ID: int
    ADMIN_USERNAME: str
    MAINTENANCE: bool
    MAX_MSG_LEN: int = 4069
    #
    # Throttling
    TTL_IN_SEC: int = 20
    MAX_RATE_SEC_IN_TTL: int = 10
    # # DB
    DB_URL: str
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    # Profticket
    COM_ID: int
    STOP_AFTER_ATTEMPT: int = 5
    WAIT_FIXED: int = 3
    PROXY_URL: str
    # Show Update Service
    UPDATE_INTERVAL: int = 600
    ERROR_RETRY_INTERVAL: int = 60
    MAX_DATA_AGE: int = 3600
    MAX_CONSECUTIVE_ERRORS: int = 3
    # Time settings
    DEFAULT_TIMEZONE: str = 'Europe/Moscow'

    class Config:
        if os.environ.get('IN_DOCKER') != '1':
            env_file = '.env'
            env_file_encoding = 'utf-8'


settings = Settings()
