from pathlib import Path
from pydantic_settings import BaseSettings

# Dev-дефолты секретов: в профиле prod (CRM_ENV=prod) их использование запрещено —
# RuntimeError на import, приложение не стартует (RAI-OS-DIR-002).
DEV_DEFAULT_SECRET_KEY = "dev-secret-change-in-production"
DEV_DEFAULT_ADMIN_PASSWORD = "admin"


class Settings(BaseSettings):
    # Профиль среды: dev (локальная разработка, допустимы dev-дефолты) | prod
    # (прод-деплой: fail-fast на дефолтных/пустых SECRET_KEY/ADMIN_PASSWORD).
    CRM_ENV: str = "dev"
    DATABASE_URL: str = "sqlite+aiosqlite:///./storage/crm.db"
    SECRET_KEY: str = DEV_DEFAULT_SECRET_KEY
    ADMIN_EMAIL: str = "admin@crm.local"
    ADMIN_PASSWORD: str = DEV_DEFAULT_ADMIN_PASSWORD

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
    # Каталог товаров. Картинки — только здесь (volume, переживает пересоздание
    # контейнера); app/static не используется — он запекается в образ.
    CATALOG_DIR: Path = BASE_DIR / "storage" / "catalog"
    CATALOG_IMAGES_DIR: Path = BASE_DIR / "storage" / "catalog" / "images"
    COMPANY_DIR: Path = BASE_DIR / "storage" / "company"

    class Config:
        env_file = ".env"


settings = Settings()


def _enforce_profile(s: Settings) -> None:
    if s.CRM_ENV not in ("dev", "prod"):
        # Опечатка в профиле не должна молча отключать fail-fast (CRM_ENV=production).
        raise RuntimeError(f"CRM_ENV must be 'dev' or 'prod', got {s.CRM_ENV!r}")
    if s.CRM_ENV != "prod":
        return
    insecure = []
    if not s.SECRET_KEY.strip() or s.SECRET_KEY == DEV_DEFAULT_SECRET_KEY:
        insecure.append("SECRET_KEY")
    if not s.ADMIN_PASSWORD.strip() or s.ADMIN_PASSWORD == DEV_DEFAULT_ADMIN_PASSWORD:
        insecure.append("ADMIN_PASSWORD")
    if insecure:
        raise RuntimeError(
            f"CRM_ENV=prod запрещает dev-дефолты/пустые значения: {', '.join(insecure)}"
            " (RAI-OS-DIR-002). Задайте реальные значения в .env."
        )


_enforce_profile(settings)

# Ensure storage directory exists
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
(settings.STORAGE_DIR / "documents").mkdir(parents=True, exist_ok=True)
settings.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
settings.CATALOG_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
settings.COMPANY_DIR.mkdir(parents=True, exist_ok=True)
