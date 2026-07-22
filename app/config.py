from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./storage/crm.db"
    SECRET_KEY: str = "dev-secret-change-in-production"
    ADMIN_EMAIL: str = "admin@crm.local"
    ADMIN_PASSWORD: str = "admin"

    HERMES_API_URL: str = "http://localhost:8080"
    HERMES_API_TOKEN: str = ""
    # Серверный read-таймаут httpx (сколько ждать ответ агента). Агентные запросы
    # с tool-use (MCP + веб-поиск) легитимно идут десятки секунд — 30с не хватает,
    # поэтому дефолт поднят до 300с. Соединение/запись обрываются быстрее (см.
    # hermes_service.py — раздельный httpx.Timeout).
    HERMES_TIMEOUT: int = 300
    HERMES_ENABLED: bool = True
    # Клиентский (браузерный) таймаут: на сколько секунд дольше серверного браузер
    # ждёт ответ перед тем, как показать «не дождались» (AbortController). Буфер
    # нужен, чтобы сервер успел вернуть свой timeout-ответ раньше браузера.
    HERMES_CLIENT_TIMEOUT_BUFFER: int = 15

    DADATA_API_KEY: str = ""
    DADATA_SECRET_KEY: str = ""
    DADATA_TIMEOUT: int = 15

    APP_BASE_URL: str = "http://localhost:8000"

    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    TEMPLATES_DIR: Path = BASE_DIR / "app" / "templates"
    STATIC_DIR: Path = BASE_DIR / "app" / "static"
    DOCX_TEMPLATES_DIR: Path = BASE_DIR / "templates_docx"
    LIBRARY_DIR: Path = BASE_DIR / "storage" / "library"

    class Config:
        env_file = ".env"


settings = Settings()

# Ensure storage directory exists
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
(settings.STORAGE_DIR / "documents").mkdir(parents=True, exist_ok=True)
settings.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
