from sqlalchemy import text as sqlalchemy_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30},
    pool_pre_ping=True,
)
async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session


async def init_db():
    from app.models import (  # noqa: F401
        User, Region, Lead, StageHistory, Contact, ContactLog, Comment, Task, Deal,
        Document, DocumentTemplate, Invite, LibraryFolder, LibraryFile,
    )

    # WAL mode для concurrent reads/writes — уменьшает "database is locked"
    async with async_engine.begin() as conn:
        await conn.execute(sqlalchemy_text("PRAGMA journal_mode=WAL"))

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Миграция: добавляем колонки реквизитов в существующую таблицу leads.
    # create_all не добавляет колонки к существующим таблицам, делаем ALTER вручную.
    # Idempotent: пропускаем уже существующие колонки.
    new_lead_columns = [
        ("ogrn", "VARCHAR(20)"),
        ("kpp", "VARCHAR(20)"),
        ("okpo", "VARCHAR(20)"),
        ("legal_address", "VARCHAR(500)"),
        ("postal_address", "VARCHAR(500)"),
        ("bank_name", "VARCHAR(255)"),
        ("bank_bic", "VARCHAR(20)"),
        ("bank_account", "VARCHAR(30)"),
        ("bank_corr_account", "VARCHAR(30)"),
    ]
    async with async_engine.begin() as conn:
        existing = await conn.execute(
            sqlalchemy_text("PRAGMA table_info(leads)")
        )
        existing_cols = {row[1] for row in existing.fetchall()}
        for col_name, col_type in new_lead_columns:
            if col_name not in existing_cols:
                await conn.execute(
                    sqlalchemy_text(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}")
                )

    # Миграция: колонки связи единого Журнала в contact_logs.
    # SET NULL на удаление связанного комментария/задачи — действие остаётся.
    new_contact_log_columns = [
        ("comment_id", "INTEGER"),
        ("task_id", "INTEGER"),
    ]
    async with async_engine.begin() as conn:
        existing = await conn.execute(
            sqlalchemy_text("PRAGMA table_info(contact_logs)")
        )
        existing_cols = {row[1] for row in existing.fetchall()}
        for col_name, col_type in new_contact_log_columns:
            if col_name not in existing_cols:
                await conn.execute(
                    sqlalchemy_text(f"ALTER TABLE contact_logs ADD COLUMN {col_name} {col_type}")
                )

    # Миграция: часовой пояс пользователя (IANA-имя). NULL → Europe/Moscow.
    async with async_engine.begin() as conn:
        existing = await conn.execute(
            sqlalchemy_text("PRAGMA table_info(users)")
        )
        existing_cols = {row[1] for row in existing.fetchall()}
        if "timezone" not in existing_cols:
            await conn.execute(
                sqlalchemy_text("ALTER TABLE users ADD COLUMN timezone VARCHAR(64)")
            )

    # Create default admin
    async with async_session_maker() as session:
        from app.auth import create_default_admin
        await create_default_admin(session)
