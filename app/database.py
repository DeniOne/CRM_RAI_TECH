from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

async_engine = create_async_engine(settings.DATABASE_URL, echo=False)
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

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create default admin
    async with async_session_maker() as session:
        from app.auth import create_default_admin
        await create_default_admin(session)
