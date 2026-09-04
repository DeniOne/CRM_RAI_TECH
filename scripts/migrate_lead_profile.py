"""Миграция данных на многопрофильную карточку (фаза 23). Одноразовый.

Что делает (идемпотентно — повторный прогон ничего не дублирует):
1. Рапсовые поля лида → направление «Рапс» (статус confirmed если verified)
   + перенос объёма/тайминга/описания.
2. qualification_status='confirmed' для лидов с rapeseed_verified (дублирует
   init_db-миграцию — здесь для dry-run-отчёта).
3. «Что сделано» → запись-комментарий в Журнал (префикс «Перенесено из карточки:»).
4. «Что нужно сделать» → задача «Следующий шаг» менеджеру лида (или админу).
5. #хэштэги из досье/сводок/рапс-инфо/комментариев → теги лида.

Запуск: python scripts/migrate_lead_profile.py           (dry-run, отчёт)
        python scripts/migrate_lead_profile.py --apply   (применить)
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import async_session_maker, init_db  # noqa: E402
from app.models import Comment, Lead, LeadDirection, Task, User  # noqa: E402
from app.services import tags_service  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402


async def migrate(apply: bool) -> dict:
    report = {
        "directions_created": 0, "directions_skipped": 0,
        "journal_entries": 0, "tasks_created": 0,
        "tags_linked": 0, "leads_scanned": 0,
    }
    async with async_session_maker() as session:
        admin = (
            await session.execute(select(User).where(User.role == "admin").limit(1))
        ).scalars().first()
        leads = (
            await session.execute(
                select(Lead).options(
                    selectinload(Lead.directions),
                    selectinload(Lead.comments),
                    selectinload(Lead.tasks),
                    selectinload(Lead.tags),
                )
            )
        ).scalars().all()
        report["leads_scanned"] = len(leads)

        for lead in leads:
            # 1. рапс → направление «Рапс»
            has_rapeseed = bool(
                lead.rapeseed_verified or lead.rapeseed_volume
                or lead.harvest_timing or lead.rapeseed_info
            )
            if has_rapeseed:
                existing = [d for d in lead.directions if d.name.lower() == "рапс"]
                if existing:
                    report["directions_skipped"] += 1
                else:
                    session.add(LeadDirection(
                        lead_id=lead.id,
                        name="Рапс",
                        status="confirmed" if lead.rapeseed_verified else "interest",
                        potential=lead.rapeseed_volume,
                        season=lead.harvest_timing,
                        note=lead.rapeseed_info,
                        manager_id=lead.assigned_manager_id,
                    ))
                    report["directions_created"] += 1

            # 3. «Что сделано» → журнал
            if lead.done_summary and lead.done_summary.strip():
                already = any(
                    c.body.startswith("Перенесено из карточки (что сделано):")
                    for c in lead.comments
                )
                if not already:
                    session.add(Comment(
                        lead_id=lead.id,
                        user_id=admin.id if admin else lead.assigned_manager_id,
                        body=f"Перенесено из карточки (что сделано): {lead.done_summary.strip()}",
                    ))
                    report["journal_entries"] += 1

            # 4. «Что нужно сделать» → задача
            if lead.todo_summary and lead.todo_summary.strip():
                already_task = any(
                    t.title.startswith("Следующий шаг (перенос):")
                    for t in lead.tasks
                )
                if not already_task:
                    session.add(Task(
                        lead_id=lead.id,
                        assigned_to=lead.assigned_manager_id or (admin.id if admin else 1),
                        title=f"Следующий шаг (перенос): {lead.todo_summary.strip()[:480]}",
                        due_date=datetime.now(),
                        priority=2,
                        status="pending",
                    ))
                    report["tasks_created"] += 1

            # 5. #хэштэги → теги
            names = tags_service.extract_hashtags(
                lead.general_comment, lead.done_summary, lead.todo_summary,
                lead.rapeseed_info, *(c.body for c in lead.comments),
            )
            for name in names:
                tag = await tags_service.get_or_create(session, name)
                if tag is None:
                    continue
                if tag not in lead.tags:
                    lead.tags.append(tag)
                    report["tags_linked"] += 1

        if apply:
            await session.commit()
        else:
            await session.rollback()
    return report


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="применить (без — dry-run)")
    args = parser.parse_args()

    await init_db()
    report = await migrate(apply=args.apply)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] лидов просканировано: {report['leads_scanned']}")
    print(f"  направлений «Рапс» создано: {report['directions_created']} (уже было: {report['directions_skipped']})")
    print(f"  записей журнала из «что сделано»: {report['journal_entries']}")
    print(f"  задач из «что нужно сделать»: {report['tasks_created']}")
    print(f"  тегов привязано: {report['tags_linked']}")


if __name__ == "__main__":
    asyncio.run(main())
