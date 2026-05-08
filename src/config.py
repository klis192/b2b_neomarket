"""
Конфигурация приложения.
Все секреты и настройки — из переменных окружения.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- База данных ---
    database_url: str = "postgresql://b2b_user:b2b_pass@db:5432/b2b_db"

    # --- JWT ---
    jwt_secret: str = "dev-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_ttl: int = 3600        # 1 час
    refresh_token_ttl: int = 2_592_000  # 30 дней

    # --- Межсервисные ключи ---
    b2b_to_mod_key: str = "secret-b2b-to-mod"
    mod_to_b2b_key: str = "secret-mod-to-b2b"
    b2c_to_b2b_key: str = "secret-b2c-to-b2b"
    b2b_to_b2c_key: str = "secret-b2b-to-b2c"

    # --- URL сервисов (для исходящих событий, M2) ---
    moderation_url: str = "http://moderation:8001"
    b2c_url: str = "http://b2c:8002"

    # --- Приложение ---
    app_title: str = "NeoMarket B2B — Кабинет продавца"
    app_version: str = "1.0.0"
    debug: bool = True

    model_config = {"env_file": ".env"}


settings = Settings()
