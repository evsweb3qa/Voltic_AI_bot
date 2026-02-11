#/config.py
import os
from typing import List
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import field_validator
from pydantic import ConfigDict
from pydantic import Field

# Определяет, какой .env файл использовать
env_file = ".env.production.bot" if os.getenv("ENVIRONMENT") == "production" else ".env"
load_dotenv(env_file)


class Settings(BaseSettings):
    # PostgreSQL Database
    DATA_BASE_URL: str
    POSTGRES_PORT_RAG: str

    # Telegram
    BOT_TN: str
    ADMIN_IDS: List[int]

    #Open AI
    OPENAI_API_KEY: str
    AI_ENABLED: bool
    AI_MODEL: str
    AI_MAX_TOKENS: int
    AI_TEMPERATURE: float
    COLLECT_TRAINING_DATA: bool = Field(default=False, validation_alias="COLLECT_TRAINING_DATA")
    RAG_ENABLED: bool

    ADMIN_IDS: List[int]
    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    WELCOME_PHOTO_ID: str


    model_config = ConfigDict(
        extra="ignore",  # ← игнорировать лишние переменные (например, ENVIRONMENT)
        case_sensitive=False,
        env_file_encoding="utf-8"
    )
# Глобальный экземпляр
settings = Settings()