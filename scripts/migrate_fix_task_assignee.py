"""Одноразовая миграция: восстановить инвариант Task.assigned_to == Lead.assigned_manager_id.

Запуск: python scripts/migrate_fix_task_assignee.py
Безопасен для повторного запуска (идемпотентный).

Контекст: до фикса задачи, созданные supervisor/admin в чужих лидах,
получали assigned_to=creator_id вместо assigned_to=lead.assigned_manager_id.
Этот скрипт исправляет исторические данные.
"""
import asyncio
import sys
from pathlib import Path

# Подключить корень проекта для импорта app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import update, select
from app.database import engine
from app.models import Task, Lead
from sqlalchemy.ext.asyncio import AsyncSession


async def main():
    async with AsyncSession(engine) as session:
        # Найти задачи, у которых assigned_to НЕ совпадает с владельцем лида
        stmt = (
            select(Task.id, Task.assigned_to, Lead.assigned_manager_id, Lead.id)
            .join(Lead, Task.lead_id == Lead.id)
            .where(Task.assigned_to != Lead.assigned_manager_id)
            .where(Lead.assigned_manager_id.is_not(None))
        )
        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            print("✓ Нет задач для миграции. БД уже согласована.")
            return

        print(f"Найдено задач с рассинхроном: {len(rows)}")
        for tid, cur, new, lid in rows:
            print(f"  task #{tid}: assigned_to {cur} → {new} (lead_id={lid})")

        # Построчное обновление (SQLite + aiosqlite не поддерживает UPDATE ... FROM)
        for tid, cur, new, lid in rows:
            await session.execute(
                update(Task).where(Task.id == tid).values(assigned_to=new)
            )
        await session.commit()
        print(f"✓ Обновлено строк: {len(rows)}")


if __name__ == "__main__":
    asyncio.run(main())
