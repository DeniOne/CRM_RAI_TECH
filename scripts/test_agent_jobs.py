"""Фаза 28: персистентная очередь прогонов агента (agent_jobs).

Проверяет: восстановление pending/running задач при старте через реальный
lifespan (симуляция «рестарт потерял прогон»), создание задачи в /agent/send,
серверный маркер незавершённых задач в поллинге, отмену задачи при «Очистить
историю». Прог-БД не трогается: локальная копия (профиль dev), тест чистит
только свои строки. Запуск: python scripts/test_agent_jobs.py
"""
import asyncio
import sqlite3
import sys
import time

sys.path.insert(0, ".")

import app.routes.agent as agent_module
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

DB_PATH = str(settings.STORAGE_DIR / "crm.db")

FAKE_REPLY = "ТЕСТ-ОЧЕРЕДЬ-28"
FAKE_SLOW_REPLY = "ТЕСТ-ОЧЕРЕДЬ-28-SLOW"


async def fake_agent_fast(*args, **kwargs):
    await asyncio.sleep(0.5)
    return {"reply": FAKE_REPLY, "actions": [], "error": None}


async def fake_agent_slow(*args, **kwargs):
    await asyncio.sleep(4.0)
    return {"reply": FAKE_SLOW_REPLY, "actions": [], "error": None}


def _q(sql, params=(), fetch=True):
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall() if fetch else None
        conn.commit()
        return rows
    finally:
        conn.close()


def _admin_id() -> int:
    rows = _q("SELECT id FROM users WHERE email = 'admin@crm.local' LIMIT 1")
    if not rows:
        raise SystemExit("admin@crm.local не найден в локальной БД — прогони verify.py")
    return rows[0][0]


def main() -> int:
    # Таблица agent_jobs создаётся create_all при старте приложения; тест
    # обращается к ней раньше — поднимаем схему до TestClient (свободный loop).
    from app.database import init_db

    asyncio.run(init_db())

    admin_id = _admin_id()

    (max_msg_id,) = _q("SELECT COALESCE(MAX(id), 0) FROM agent_messages")[0]
    (max_job_id,) = _q("SELECT COALESCE(MAX(id), 0) FROM agent_jobs")[0]

    failures = []

    # Подменяем агента ДО клиента (agent.py держит имя у себя в namespace).
    agent_module.send_to_hermes = fake_agent_fast

    # Симуляция «рестарт потерял прогон»: две незавершённые задачи до старта
    # приложения. with-блок запускает lifespan → recovery обязана их подхватить.
    _q(
        """INSERT INTO agent_jobs
           (user_id, user_name, role, message, search_mode, status, created_at, updated_at)
           VALUES
           (?, 'Admin', 'admin', 'тест-восстановление-28-А', 'crm', 'running', datetime('now'), datetime('now')),
           (?, 'Admin', 'admin', 'тест-восстановление-28-Б', 'internet', 'pending', datetime('now'), datetime('now'))""",
        (admin_id, admin_id),
        fetch=False,
    )
    stuck_ids = [
        r[0]
        for r in _q(
            "SELECT id FROM agent_jobs WHERE user_id = ? AND status IN ('pending','running')",
            (admin_id,),
        )
    ]
    if len(stuck_ids) < 2:
        print(f"note: восстановление подхватит {len(stuck_ids)} задач(и) (ожидалось 2)")

    with TestClient(app) as client:
        r = client.post("/login", data={"email": "admin@crm.local", "password": "admin"})
        assert r.status_code in (200, 303), f"login failed: {r.status_code}"

        # ── 1. Recovery через реальный lifespan ──
        deadline = time.monotonic() + 15
        recovered = 0
        while time.monotonic() < deadline:
            r = client.get("/agent/updates?after_id=0")
            recovered = r.text.count(FAKE_REPLY)
            if recovered >= len(stuck_ids):
                break
            time.sleep(0.5)
        if recovered < len(stuck_ids):
            failures.append(
                f"recovery: в чат пришло {recovered} из {len(stuck_ids)} ответов"
            )
        else:
            print(f"OK: recovery дописала {len(stuck_ids)} потерянных ответа в чат")

        statuses = dict(
            (r[0], r[1])
            for r in _q(
                f"SELECT id, status FROM agent_jobs WHERE id IN ({','.join('?' * len(stuck_ids))})",
                stuck_ids,
            )
        )
        bad = [i for i, s in statuses.items() if s not in ("done", "failed")]
        if bad:
            failures.append(f"recovery: задачи не закрыты, статусы {statuses}")
        else:
            print(f"OK: восстановленные задачи закрыты ({list(statuses.values())})")

        # ── 2. /agent/send создаёт задачу, ответ приходит, задача закрывается ──
        r = client.post(
            "/agent/send",
            data={"message": "тест-очередь-28-send", "search_mode": "crm"},
        )
        if r.status_code != 200:
            failures.append(f"send: HTTP {r.status_code}")
        user_msg_id = int(r.text.split('data-msg-id="')[1].split('"')[0])
        (job_id,) = _q(
            "SELECT id FROM agent_jobs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (admin_id,),
        )[0]
        deadline = time.monotonic() + 10
        status = None
        while time.monotonic() < deadline:
            rows = _q(
                "SELECT status, agent_message_id FROM agent_jobs WHERE id = ?", (job_id,)
            )
            status, msg_id = rows[0]
            if status in ("done", "failed"):
                break
            time.sleep(0.3)
        if status not in ("done", "failed"):
            failures.append(f"send: задача не закрылась (статус {status})")
        elif not msg_id:
            failures.append("send: задача закрыта без agent_message_id")
        else:
            print(f"OK: send создал задачу #{job_id}, ответ дописан, статус {status}")

        # ── 3. Маркер незавершённых задач в поллинге (серверная истина) ──
        agent_module.send_to_hermes = fake_agent_slow
        r = client.post(
            "/agent/send",
            data={"message": "тест-очередь-28-маркер", "search_mode": "crm"},
        )
        slow_msg_id = int(r.text.split('data-msg-id="')[1].split('"')[0])
        r = client.get(f"/agent/updates?after_id={slow_msg_id}")
        if "agent-jobs-marker" not in r.text:
            failures.append("updates: нет маркера незавершённой задачи")
        else:
            print("OK: поллинг отдаёт маркер незавершённых задач")
        deadline = time.monotonic() + 12
        got_slow = False
        while time.monotonic() < deadline:
            time.sleep(0.5)
            r = client.get(f"/agent/updates?after_id={slow_msg_id}")
            if FAKE_SLOW_REPLY in r.text:
                got_slow = True
                break
        if not got_slow:
            failures.append("медленный ответ не дошёл поллингом")
        else:
            print("OK: медленный прогон дошёл поллингом")

        # ── 4. «Очистить историю» отменяет задачу — фантомного ответа нет ──
        r = client.post(
            "/agent/send",
            data={"message": "тест-очередь-28-отмена", "search_mode": "crm"},
        )
        cancel_msg_id = int(r.text.split('data-msg-id="')[1].split('"')[0])
        r = client.post("/agent/clear", follow_redirects=False)
        if r.status_code != 303:
            failures.append(f"clear: HTTP {r.status_code}")
        time.sleep(6)  # медленный фейк успевает вернуться
        rows = _q(
            "SELECT status FROM agent_jobs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (admin_id,),
        )
        if not rows or rows[0][0] != "cancelled":
            failures.append(f"clear: задача не отменена ({rows})")
        phantom = _q(
            "SELECT COUNT(*) FROM agent_messages WHERE user_id = ? AND content LIKE ?",
            (admin_id, f"%{FAKE_SLOW_REPLY}%"),
        )[0][0]
        if phantom:
            failures.append("clear: фантомный ответ дописан после очистки")
        if not failures:
            print("OK: очистка чата отменила задачу, фантомного ответа нет")

    # ── Уборка: только созданные тестом строки ──
    _q(
        "DELETE FROM agent_messages WHERE user_id = ? AND id > ?",
        (admin_id, max_msg_id),
        fetch=False,
    )
    _q(
        "DELETE FROM agent_jobs WHERE user_id = ? AND id > ?",
        (admin_id, max_job_id),
        fetch=False,
    )

    print()
    if failures:
        print("FAIL:")
        for f in failures:
            print(" -", f)
        return 1
    print("PASS: персистентная очередь работает end-to-end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
