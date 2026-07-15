"""
Разовая миграция: leads.todo_summary -> формальные задачи (tasks).

Для каждого лида с непустым todo_summary (кроме stage='lost'):
  1. Отправляет текст в Hermes (OpenAI-совместимый /v1/chat/completions)
     с инструкцией извлечь задачи как строгий JSON.
  2. Парсит результат: {title, due_date ('YYYY-MM-DD HH:MM' | null), done (bool)}.
  3. Создаёт Task (assigned_to = assigned_manager_id, created_by = он же).
  4. Автостатус: если есть свежий contact_log после due_date -> done,
     иначе pending (overdue считается на лету в ticker/tasks/dashboard —
     в БД не пишется).

Дубли разрешены (разовое действие). Idempotency-маркера нет.

Использование:
  python scripts/migrate_todo_to_tasks.py --lead-id 318 --dry-run   # один лид
  python scripts/migrate_todo_to_tasks.py --dry-run                 # все лиды
  python scripts/migrate_todo_to_tasks.py --apply                   # запись в БД
  python scripts/migrate_todo_to_tasks.py --limit 10 --dry-run      # первые N

На сервере:
  docker cp scripts/migrate_todo_to_tasks.py crm-rai-dev:/app/scripts/migrate_todo_to_tasks.py
  docker exec crm-rai-dev python scripts/migrate_todo_to_tasks.py --dry-run
"""
import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import init_db, async_session_maker
from app.models import Lead, Task, ContactLog

HERMES_URL = f"{settings.HERMES_API_URL.rstrip('/')}/v1/chat/completions"
MODEL = "hermes-agent"
CONCURRENCY = 3            # одновременных Hermes-запросов
REQUEST_TIMEOUT = settings.HERMES_TIMEOUT
EXPORTS_DIR = settings.STORAGE_DIR / "exports"

SYSTEM_PROMPT = (
    "Ты извлекаешь задачи из коротких рабочих заметок менеджера CRM. "
    "Верни СТРОГО JSON-объект вида {\"tasks\": [...]}. "
    "Каждый элемент — {\"title\": str, \"due_date\": str|null, \"done\": bool}. "
    "Правила:\n"
    "1. title — краткое название задачи ЧТО СДЕЛАТЬ (позвонить, набрать, отправить КП, "
    "уточнить), без даты. 1-12 слов. Если заметка — просто факт/инфо без действия, "
    "всё равно сформулируй как задачу (например 'уточнить X').\n"
    "2. due_date — 'YYYY-MM-DD HH:MM' (24ч). Время из текста если есть, иначе 00:00. "
    "Год: если в тексте DD.MM без года — бери текущий 2026; если полученная дата уже "
    "прошла относительно сегодня (2026-07-14) — оставь как есть (это просрочка). "
    "Диапазоны ('май-июнь 2027') -> первая дата. Если даты нет вовсе — null.\n"
    "3. done=true если по тексту действие УЖЕ выполнено ('позвонил','отправил',"
    "'договорились','оплатили'), иначе false.\n"
    "4. Несколько дат/действий в тексте (через перенос строки или ';') — несколько "
    "элементов массива, по одному на дату+действие.\n"
    "5. Никаких пояснений, markdown — только JSON. Сегодня = 2026-07-14."
)


def parse_llm_json(raw: str) -> list:
    """Извлекает массив tasks из ответа Hermes (с защитой от мусора)."""
    if not raw:
        return []
    # Попытка 1: строгий JSON целиком.
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "tasks" in data:
            return data["tasks"]
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    # Попытка 2: найти первый {...} блок и взять tasks.
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict) and "tasks" in data:
                return data["tasks"]
        except json.JSONDecodeError:
            pass
    # Попытка 3: найти массив [...] напрямую.
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return []


def normalize_due(due_str):
    """'YYYY-MM-DD HH:MM' | None -> naive datetime | None."""
    if due_str is None or due_str == "":
        return None
    if isinstance(due_str, str):
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(due_str.strip(), fmt)
            except ValueError:
                continue
    return None


async def ask_hermes(client: httpx.AsyncClient, sem: asyncio.Semaphore,
                     text: str) -> list:
    """Один вызов Hermes. Возвращает список задач (dict)."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Заметка: \"{text}\""},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if settings.HERMES_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.HERMES_API_TOKEN}"
    async with sem:
        resp = await client.post(HERMES_URL, json=payload, headers=headers,
                                 timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("choices", [{}])[0]
                   .get("message", {}).get("content", ""))
    return parse_llm_json(content)


async def _process(lead, client, sem, now, write_db: bool):
    """Обработка одного лида. write_db=True — открывает собственную сессию
    для записи и коммитит самостоятельно (aiosqlite не терпит конкурентный
    доступ к одной сессии из параллельных корутин)."""
    text = (lead.todo_summary or "").strip()
    rec = {"lead_id": lead.id, "name": lead.name,
           "todo_summary": text, "tasks": [], "error": None}
    try:
        items = await ask_hermes(client, sem, text)
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
        return rec

    # Своя read-сессия для contact_logs (короткая, закрывается сразу).
    contact_dates = []
    async with async_session_maker() as rs:
        cl_rows = await rs.scalars(
            select(ContactLog.contact_date)
            .where(ContactLog.lead_id == lead.id)
            .order_by(ContactLog.contact_date.desc())
        )
        contact_dates = [d for d in cl_rows.all() if d is not None]

    # Собираем задачи в список, потом пишем всё в одной сессии одним коммитом.
    to_create = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = (it.get("title") or "").strip()
        if not title:
            continue
        due = normalize_due(it.get("due_date"))
        is_done = bool(it.get("done"))
        status = "pending"
        completed_at = None
        if is_done:
            status = "done"
            completed_at = now
        elif due is not None:
            fresh = [d for d in contact_dates if d >= due]
            if fresh:
                status = "done"
                completed_at = max(fresh)
        rec["tasks"].append({
            "title": title[:500],
            "due_date": due.strftime("%Y-%m-%d %H:%M") if due else None,
            "status": status,
            "completed_at": completed_at.strftime("%Y-%m-%d %H:%M")
                            if completed_at else None,
        })
        if lead.assigned_manager_id:
            to_create.append(Task(
                lead_id=lead.id,
                assigned_to=lead.assigned_manager_id,
                created_by=lead.assigned_manager_id,
                title=title[:500],
                due_date=due,
                priority=2,
                status=status,
                completed_at=completed_at,
            ))

    if write_db and to_create:
        async with async_session_maker() as ws:
            ws.add_all(to_create)
            await ws.commit()
    return rec


async def main():
    ap = argparse.ArgumentParser(description="Миграция todo_summary -> tasks")
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="Без записи в БД (по умолчанию).")
    ap.add_argument("--apply", action="store_true",
                    help="Записать задачи в БД.")
    ap.add_argument("--lead-id", type=int, default=None,
                    help="Только один лид (для отладки).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Только первые N лидов.")
    args = ap.parse_args()
    write_db = bool(args.apply)

    await init_db()
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    async with async_session_maker() as session:
        q = (select(Lead)
             .where(Lead.todo_summary.isnot(None))
             .where(Lead.todo_summary != ""))
        if args.lead_id is not None:
            q = q.where(Lead.id == args.lead_id)
        else:
            q = q.where(Lead.stage != "lost")
        if args.limit:
            q = q.limit(args.limit)
        leads = list((await session.scalars(q)).all())

    print(f"Лидов к обработке: {len(leads)}")
    print(f"Режим: {'APPLY (запись в БД)' if write_db else 'DRY-RUN (без записи)'}")
    if not leads:
        return

    sem = asyncio.Semaphore(CONCURRENCY)
    now = datetime.now()

    async with httpx.AsyncClient() as client:
        async def run(lead):
            return await _process(lead, client, sem, now, write_db)

        results = await asyncio.gather(*(run(l) for l in leads),
                                       return_exceptions=True)

    ok = [r for r in results if isinstance(r, dict) and not r.get("error")]
    err = [r for r in results if isinstance(r, dict) and r.get("error")]
    exc = [r for r in results if isinstance(r, Exception)]
    total_tasks = sum(len(r.get("tasks", [])) for r in ok)
    with_due = sum(1 for r in ok for t in r["tasks"] if t["due_date"])
    no_due = total_tasks - with_due
    auto_done = sum(1 for r in ok for t in r["tasks"] if t["status"] == "done")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "generated_at": datetime.now().isoformat(),
        "mode": "apply" if write_db else "dry-run",
        "leads_total": len(leads),
        "leads_ok": len(ok),
        "leads_with_error": len(err),
        "exceptions": [repr(e) for e in exc],
        "tasks_total": total_tasks,
        "tasks_with_due_date": with_due,
        "tasks_no_due_date": no_due,
        "tasks_auto_done": auto_done,
        "leads": ok + err,
    }
    out = EXPORTS_DIR / f"migrate_todo_report_{ts}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    print("\n=== СВОДКА ===")
    print(f"Лидов обработано: {len(ok)} | с ошибкой: {len(err)} | исключений: {len(exc)}")
    print(f"Задач создано: {total_tasks} (с датой: {with_due}, без даты: {no_due}, авто-done: {auto_done})")
    print(f"Отчёт: {out}")
    if err:
        print("\nОшибки Hermes:")
        for r in err[:10]:
            print(f"  lead {r['lead_id']} ({r['name'][:30]}): {r['error']}")
    if exc:
        print("\nНеперехваченные исключения:")
        for e in exc[:5]:
            print(f"  {repr(e)}")


if __name__ == "__main__":
    asyncio.run(main())
