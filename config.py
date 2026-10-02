from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    # Profticket
    COM_ID: int
    STOP_AFTER_ATTEMPT: int = 5
    WAIT_FIXED: int = 3
    PROXY_URL: str
    SCHEDULE_SOURCE: Literal['ermolova', 'profticket'] = 'ermolova'
    MOSBILET_PROXY_URL: str = ''
    MOSBILET_PROXY_CA_FILE: str = ''
    # Show Update Service
    UPDATE_INTERVAL: int = 1800  # 30 минут
    ERROR_RETRY_INTERVAL: int = 60
    MAX_DATA_AGE: int = 1800
    MAX_CONSECUTIVE_ERRORS: int = 3
    # Time settings
    DEFAULT_TIMEZONE: str = 'Europe/Moscow'

    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8'
    )


settings = Settings()
