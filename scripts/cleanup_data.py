import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from app.database import init_db, async_session_maker
from app.models import Lead


async def cleanup():
    await init_db()
    async with async_session_maker() as session:
        # Fix ИНН with .0
        result = await session.execute(select(Lead.id, Lead.inn).where(Lead.inn.like("%.0")))
        inn_fixes = 0
        for row in result:
            new_inn = row.inn.rstrip("0").rstrip(".")
            if new_inn:
                await session.execute(update(Lead).where(Lead.id == row.id).values(inn=new_inn))
                inn_fixes += 1

        # Fix level not in A/B/C
        result = await session.execute(
            select(Lead.id, Lead.level).where(
                Lead.level.isnot(None), Lead.level.notin_(["A", "B", "C"])
            )
        )
        level_fixes = 0
        for row in result:
            await session.execute(update(Lead).where(Lead.id == row.id).values(level=None))
            level_fixes += 1

        await session.commit()
        print(f"Fixed {inn_fixes} ИНН records (.0 removed)")
        print(f"Fixed {level_fixes} level records (anomalous -> NULL)")


if __name__ == "__main__":
    asyncio.run(cleanup())
