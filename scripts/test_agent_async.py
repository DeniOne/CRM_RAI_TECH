"""Фаза 27: асинхронный чат агента.

Проверяет: /agent/send отвечает сразу (не ждёт прогон агента), ответ агента
дописывается в agent_messages фоновой задачей и отдаётся поллингом
/agent/updates, ошибки агента тоже попадают в чат. Прог-БД не трогается:
тест крутится на локальной копии (профиль dev) и чистит за собой только
созданные им строки. Запуск: python scripts/test_agent_async.py
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

FAKE_REPLY = "ТЕСТОВЫЙ-ОТВЕТ-27"
FAKE_ERROR_REPLY = "ТЕСТОВЫЙ-ОТВЕТ-27-ОШИБКА"
DB_PATH = str(settings.STORAGE_DIR / "crm.db")
_max_job_id_at_start = 0


async def fake_agent_ok(*args, **kwargs):
    # Имитируем долгого агента: дольше HTTP-запроса send, короче ожиданий теста.
    await asyncio.sleep(1.5)
    return {"reply": FAKE_REPLY, "actions": [], "error": None}


async def fake_agent_error(*args, **kwargs):
    return {"reply": FAKE_ERROR_REPLY, "actions": [], "error": "timeout"}


def _admin_id() -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = 'admin@crm.local' LIMIT 1"
        ).fetchone()
        if not row:
            raise SystemExit("admin@crm.local не найден в локальной БД — прогони verify.py")
        return row[0]
    finally:
        conn.close()


def _cleanup(user_id: int, min_id: int) -> None:
    """Удаляет только строки, созданные тестом (сообщения id >= min_id, все
    задачи, созданные после старта теста)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "DELETE FROM agent_messages WHERE user_id = ? AND id >= ?",
            (user_id, min_id),
        )
        conn.execute(
            "DELETE FROM agent_jobs WHERE user_id = ? AND id > ?",
            (user_id, _max_job_id_at_start),
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    # Подменяем агента ДО клиента: agent.py импортировал имя к себе в namespace.
    agent_module.send_to_hermes = fake_agent_ok

    admin_id = _admin_id()
    global _max_job_id_at_start
    conn = sqlite3.connect(DB_PATH)
    try:
        _max_job_id_at_start = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM agent_jobs"
        ).fetchone()[0]
    finally:
        conn.close()
    failures = []

    # with-контекст обязателен: он держит ОДИН event loop на все запросы.
    # Без него TestClient закрывает loop после каждого запроса и фоновая
    # задача прогона умирает вместе с ним (в проде uvicorn живёт постоянно).
    with TestClient(app) as client:
        r = client.post("/login", data={"email": "admin@crm.local", "password": "admin"})
        assert r.status_code in (200, 303), f"login failed: {r.status_code}"

        # ── 1. /agent/send отвечает сразу, ответа агента в ответе нет ──
        t0 = time.monotonic()
        r = client.post(
            "/agent/send",
            data={"message": "тест-27-синхронность", "search_mode": "crm"},
        )
        elapsed = time.monotonic() - t0
        if r.status_code != 200:
            failures.append(f"send: HTTP {r.status_code}")
        if elapsed > 1.0:
            failures.append(f"send ждал агента: {elapsed:.2f}s (ожидался мгновенный ответ)")
        if FAKE_REPLY in r.text:
            failures.append("send вернул ответ агента — должен отвечать сразу")
        if "data-msg-id" not in r.text:
            failures.append("send не вернул data-msg-id (курсор поллинга сломан)")

        new_user_msg_id = int(r.text.split('data-msg-id="')[1].split('"')[0])
        print(f"OK: send мгновенный ({elapsed:.2f}s), user msg id={new_user_msg_id}")

        # ── 2. Поллинг по курсору до готовности — только сообщение пользователя ──
        r = client.get(f"/agent/updates?after_id={new_user_msg_id - 1}")
        if FAKE_REPLY in r.text:
            failures.append("ответ появился раньше фонового прогона")
        if f'data-msg-id="{new_user_msg_id}"' not in r.text:
            failures.append("updates не отдал сообщение пользователя по after_id")

        # ── 3. Ответ агента дописан фоном и забирается поллингом ──
        deadline = time.monotonic() + 10
        got_reply = False
        while time.monotonic() < deadline:
            time.sleep(0.5)
            r = client.get(f"/agent/updates?after_id={new_user_msg_id}")
            if FAKE_REPLY in r.text:
                got_reply = True
                break
        if not got_reply:
            failures.append("ответ агента не пришёл поллингом за 10с")
        else:
            print("OK: фоновый ответ дописан и отдаётся /agent/updates")

        # ── 4. Ошибка агента тоже попадает в чат ──
        agent_module.send_to_hermes = fake_agent_error
        r = client.post(
            "/agent/send",
            data={"message": "тест-27-ошибка", "search_mode": "internet"},
        )
        if r.status_code != 200:
            failures.append(f"send (error path): HTTP {r.status_code}")
        err_msg_id = int(r.text.split('data-msg-id="')[1].split('"')[0])
        deadline = time.monotonic() + 10
        got_err = False
        while time.monotonic() < deadline:
            time.sleep(0.5)
            r = client.get(f"/agent/updates?after_id={err_msg_id}")
            if FAKE_ERROR_REPLY in r.text:
                got_err = True
                break
        if not got_err:
            failures.append("ошибка агента не дописана в чат (молчаливое пропадание)")
        else:
            print("OK: ошибка агента дописана в чат как сообщение ассистента")

        # ── 5. Страница чата рендерится с курсором и без гонки таймаутов ──
        r = client.get("/agent")
        if r.status_code != 200:
            failures.append(f"GET /agent: HTTP {r.status_code}")
        if "data-last-msg-id" not in r.text:
            failures.append("нет data-last-msg-id на #chat-history")
        if "CLIENT_TIMEOUT_MS" in r.text or "AbortController" in r.text:
            failures.append("в шаблоне остался мёртвый AbortController/CLIENT_TIMEOUT")
        if "/agent/updates" not in r.text:
            failures.append("в шаблоне нет поллинга /agent/updates")
        if not failures:
            print("OK: страница чата — поллинг на месте, таймаут-гонка убрана")

    # ── Уборка: только созданные тестом строки ──
    _cleanup(admin_id, new_user_msg_id)

    print()
    if failures:
        print("FAIL:")
        for f in failures:
            print(" -", f)
        return 1
    print("PASS: асинхронный чат работает end-to-end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
