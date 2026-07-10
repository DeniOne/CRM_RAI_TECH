import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_db, async_session_maker
from app.services.import_service import import_xlsx


async def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "Екатерина.xlsx"
    print(f"Импорт из: {path}")
    await init_db()
    async with async_session_maker() as session:
        report = await import_xlsx(path, session)
        await session.commit()
    print(f"Импорт завершён:")
    print(f"  Регионов: {report['regions']}")
    print(f"  Лидов: {report['leads']}")
    print(f"  Контактов: {report['contacts']}")
    print(f"  Записей журнала: {report['contact_logs']}")


if __name__ == "__main__":
    asyncio.run(main())
