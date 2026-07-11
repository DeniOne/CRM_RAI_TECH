from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./storage/crm.db"
    SECRET_KEY: str = "dev-secret-change-in-production"
    ADMIN_EMAIL: str = "admin@crm.local"
    ADMIN_PASSWORD: str = "admin"

    HERMES_API_URL: str = "http://localhost:8080"
    HERMES_API_TOKEN: str = ""
    HERMES_TIMEOUT: int = 30
    HERMES_ENABLED: bool = True

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
