from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./storage/crm.db"
    SECRET_KEY: str = "dev-secret-change-in-production"
    ADMIN_EMAIL: str = "admin@crm.local"
    ADMIN_PASSWORD: str = "admin"

    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    TEMPLATES_DIR: Path = BASE_DIR / "app" / "templates"
    STATIC_DIR: Path = BASE_DIR / "app" / "static"
    DOCX_TEMPLATES_DIR: Path = BASE_DIR / "templates_docx"

    class Config:
        env_file = ".env"


settings = Settings()

# Ensure storage directory exists
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
(settings.STORAGE_DIR / "documents").mkdir(parents=True, exist_ok=True)
