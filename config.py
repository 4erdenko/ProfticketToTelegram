import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Bot
    BOT_TOKEN: str
    TEST_BOT_TOKEN: str
    ADMIN_ID: int
    ADMIN_USERNAME: str
    MAINTENANCE: bool
    #
    # Throttling
    TTL_IN_SEC: int = 20
    MAX_RATE_SEC_IN_TTL: int = 5
    # # DB
    DB_URL: str
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    PGADMIN_DEFAULT_PASSWORD: str
    PGADMIN_DEFAULT_EMAIL: str
    # # Channel
    # CHANNEL_ID: str

    class Config:
        if os.environ.get('IN_DOCKER') != '1':
            env_file = '.env'
            env_file_encoding = 'utf-8'


settings = Settings()