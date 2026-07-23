#!/usr/bin/env python3
"""
MCP-сервер для CRM RAI TECH.
Подключается напрямую к SQLite БД CRM и предоставляет инструменты
для Hermes Agent: поиск лидов, управление задачами, воронка, документы.

Запуск: python3 mcp_server.py
Транспорт: stdio (Hermes запускает как subprocess)
"""

import json
import os
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get(
    "CRM_DB_PATH",
    str(Path(__file__).resolve().parent / "storage" / "crm.db"),
)

# DaData — для внешнего lookup'а компаний по ИНН (быстрый API, ~1с, не блокирует
# ботов — в отличие от браузера по сайтам-реестрам, который виснет по 60с).
# Ключи прокидываются через env MCP-сервера (см. config Hermes, mcp_servers).
DADATA_API_KEY = os.environ.get("DADATA_API_KEY", "")
DADATA_SECRET_KEY = os.environ.get("DADATA_SECRET_KEY", "")
DADATA_SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs"
DADATA_FIND_PARTY_URL = f"{DADATA_SUGGEST_URL}/findById/party"
DADATA_FIND_AFFILIATED_URL = f"{DADATA_SUGGEST_URL}/findAffiliated/party"

mcp = FastMCP(
    "crm-rai-tech",
    instructions=(
        "MCP-сервер CRM РАИ Технологии. "
        "Инструменты для работы с лидами, задачами, сделками, документами и воронкой продаж. "
        "Все инструменты работают напрямую с SQLite базой CRM."
    ),
)


def _get_conn() -> sqlite3.Connection:
    """Открыть соединение с БД CRM (read-only для безопасности)."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _get_conn_rw() -> sqlite3.Connection:
    """Открыть соединение с БД CRM (read-write)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


# ===========================================================================
# TOOLS: Leads
# ===========================================================================

@mcp.tool()
def search_leads(
    query: Optional[str] = None,
    region_id: Optional[int] = None,
    stage: Optional[str] = None,
    level: Optional[str] = None,
    priority: Optional[int] = None,
    manager_id: Optional[int] = None,
    limit: int = 20,
) -> str:
    """
    Поиск лидов (компаний) в CRM.
    
    Args:
        query: Поиск по названию компании, ИНН или адресу (подстрока)
        region_id: Фильтр по ID региона
        stage: Фильтр по стадии воронки (0-7, lost)
        level: Фильтр по уровню (A, B, C)
        priority: Фильтр по приоритету (1, 2, 3)
        manager_id: Фильтр по ID менеджера
        limit: Максимум результатов (по умолчанию 20)
    
    Returns:
        JSON-массив лидов с основными полями
    """
    conn = _get_conn()
    try:
        conditions = []
        params = []

        if query:
            conditions.append("(l.name LIKE ? OR l.inn LIKE ? OR l.address LIKE ?)")
            q = f"%{query}%"
            params.extend([q, q, q])
        if region_id is not None:
            conditions.append("l.region_id = ?")
            params.append(region_id)
        if stage:
            conditions.append("l.stage = ?")
            params.append(stage)
        if level:
            conditions.append("l.level = ?")
            params.append(level)
        if priority is not None:
            conditions.append("l.priority = ?")
            params.append(priority)
        if manager_id is not None:
            conditions.append("l.assigned_manager_id = ?")
            params.append(manager_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT l.id, l.name, l.inn, l.stage, l.level, l.priority,
                   l.district, l.settlement, l.address,
                   r.name AS region_name,
                   u.full_name AS manager_name,
                   l.general_comment, l.todo_summary,
                   l.created_at, l.updated_at
            FROM leads l
            LEFT JOIN regions r ON r.id = l.region_id
            LEFT JOIN users u ON u.id = l.assigned_manager_id
            {where}
            ORDER BY l.updated_at DESC
            LIMIT ?
        """
        rows = conn.execute(sql, params).fetchall()
        result = _rows_to_dicts(rows)
        return json.dumps(result, ensure_ascii=False, default=str)
    finally:
        conn.close()


@mcp.tool()
def get_lead_details(lead_id: int) -> str:
    """
    Получить полную информацию о лиде (компании) по ID.
    Включает контакты, историю звонков, комментарии, задачи, сделки, документы.
    
    Args:
        lead_id: ID лида
    
    Returns:
        JSON с полной информацией о лиде
    """
    conn = _get_conn()
    try:
        lead = conn.execute(
            """SELECT l.*, r.name AS region_name, u.full_name AS manager_name
               FROM leads l
               LEFT JOIN regions r ON r.id = l.region_id
               LEFT JOIN users u ON u.id = l.assigned_manager_id
               WHERE l.id = ?""",
            (lead_id,),
        ).fetchone()

        if not lead:
            return json.dumps({"error": f"Лид с ID {lead_id} не найден"}, ensure_ascii=False)

        lead_dict = dict(lead)

        # Контакты
        contacts = conn.execute(
            "SELECT * FROM contacts WHERE lead_id = ?", (lead_id,)
        ).fetchall()
        lead_dict["contacts"] = _rows_to_dicts(contacts)

        # История звонков/контактов
        logs = conn.execute(
            """SELECT cl.*, u.full_name AS user_name
               FROM contact_logs cl
               LEFT JOIN users u ON u.id = cl.user_id
               WHERE cl.lead_id = ?
               ORDER BY cl.contact_date DESC
               LIMIT 20""",
            (lead_id,),
        ).fetchall()
        lead_dict["contact_logs"] = _rows_to_dicts(logs)

        # Комментарии
        comments = conn.execute(
            """SELECT c.*, u.full_name AS user_name
               FROM comments c
               LEFT JOIN users u ON u.id = c.user_id
               WHERE c.lead_id = ?
               ORDER BY c.created_at DESC
               LIMIT 20""",
            (lead_id,),
        ).fetchall()
        lead_dict["comments"] = _rows_to_dicts(comments)

        # Задачи
        tasks = conn.execute(
            "SELECT * FROM tasks WHERE lead_id = ? ORDER BY due_date", (lead_id,)
        ).fetchall()
        lead_dict["tasks"] = _rows_to_dicts(tasks)

        # Сделки
        deals = conn.execute(
            "SELECT * FROM deals WHERE lead_id = ? ORDER BY created_at DESC", (lead_id,)
        ).fetchall()
        lead_dict["deals"] = _rows_to_dicts(deals)

        # Документы
        docs = conn.execute(
            "SELECT * FROM documents WHERE lead_id = ? ORDER BY created_at DESC", (lead_id,)
        ).fetchall()
        lead_dict["documents"] = _rows_to_dicts(docs)

        return json.dumps(lead_dict, ensure_ascii=False, default=str)
    finally:
        conn.close()


# ===========================================================================
# TOOLS: Funnel / Воронка
# ===========================================================================

STAGE_LABELS = {
    "0": "Новый",
    "1": "Квалификация",
    "2": "Презентация",
    "3": "Тестирование",
    "4": "Торги",
    "5": "Согласование",
    "6": "Выиграли",
    "7": "Выполнено",
    "lost": "Проиграли",
}


@mcp.tool()
def get_funnel(manager_id: Optional[int] = None) -> str:
    """
    Получить воронку продаж — количество лидов по стадиям.
    
    Args:
        manager_id: Фильтр по менеджеру (опционально)
    
    Returns:
        JSON с воронкой: стадия → количество лидов
    """
    conn = _get_conn()
    try:
        where = ""
        params = []
        if manager_id is not None:
            where = "WHERE assigned_manager_id = ?"
            params = [manager_id]

        rows = conn.execute(
            f"SELECT stage, COUNT(*) as count FROM leads {where} GROUP BY stage ORDER BY stage",
            params,
        ).fetchall()

        funnel = {}
        for r in rows:
            stage = r["stage"]
            label = STAGE_LABELS.get(stage, stage)
            funnel[label] = {"stage_code": stage, "count": r["count"]}

        return json.dumps(funnel, ensure_ascii=False)
    finally:
        conn.close()


# ===========================================================================
# TOOLS: Tasks
# ===========================================================================

@mcp.tool()
def search_tasks(
    status: Optional[str] = None,
    manager_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    overdue_only: bool = False,
    limit: int = 20,
) -> str:
    """
    Поиск задач.
    
    Args:
        status: Фильтр по статусу (pending, in_progress, done)
        manager_id: Фильтр по ответственному
        lead_id: Фильтр по лиду
        overdue_only: Только просроченные задачи
        limit: Максимум результатов
    
    Returns:
        JSON-массив задач
    """
    conn = _get_conn()
    try:
        conditions = []
        params = []

        if status:
            conditions.append("t.status = ?")
            params.append(status)
        if manager_id is not None:
            conditions.append("t.assigned_to = ?")
            params.append(manager_id)
        if lead_id is not None:
            conditions.append("t.lead_id = ?")
            params.append(lead_id)
        if overdue_only:
            conditions.append("t.due_date < datetime('now')")
            conditions.append("t.status IN ('pending', 'in_progress')")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT t.*, l.name AS lead_name, u.full_name AS assigned_to_name
            FROM tasks t
            LEFT JOIN leads l ON l.id = t.lead_id
            LEFT JOIN users u ON u.id = t.assigned_to
            {where}
            ORDER BY t.due_date
            LIMIT ?
        """
        rows = conn.execute(sql, params).fetchall()
        return json.dumps(_rows_to_dicts(rows), ensure_ascii=False, default=str)
    finally:
        conn.close()


@mcp.tool()
def create_task(
    title: str,
    assigned_to: int,
    lead_id: Optional[int] = None,
    description: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: int = 2,
) -> str:
    """
    Создать задачу в CRM.
    
    Args:
        title: Название задачи
        assigned_to: ID ответственного (пользователя)
        lead_id: ID привязанного лида (опционально)
        description: Описание задачи
        due_date: Дата дедлайна (формат YYYY-MM-DD)
        priority: Приоритет 1-3 (1=высокий)
    
    Returns:
        JSON с ID созданной задачи
    """
    conn = _get_conn_rw()
    try:
        cursor = conn.execute(
            """INSERT INTO tasks (title, assigned_to, lead_id, description, due_date, priority, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (title, assigned_to, lead_id, description, due_date, priority),
        )
        conn.commit()
        return json.dumps({"ok": True, "task_id": cursor.lastrowid}, ensure_ascii=False)
    finally:
        conn.close()


@mcp.tool()
def update_task_status(task_id: int, status: str) -> str:
    """
    Обновить статус задачи.
    
    Args:
        task_id: ID задачи
        status: Новый статус (pending, in_progress, done)
    
    Returns:
        JSON с результатом
    """
    conn = _get_conn_rw()
    try:
        completed_at = datetime.now().isoformat() if status == "done" else None
        conn.execute(
            "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
            (status, completed_at, task_id),
        )
        conn.commit()
        return json.dumps({"ok": True, "task_id": task_id, "status": status}, ensure_ascii=False)
    finally:
        conn.close()


# ===========================================================================
# TOOLS: Deals / Сделки
# ===========================================================================

@mcp.tool()
def search_deals(
    status: Optional[str] = None,
    lead_id: Optional[int] = None,
    limit: int = 20,
) -> str:
    """
    Поиск сделок.
    
    Args:
        status: Фильтр по статусу (new, in_progress, won, lost, paid)
        lead_id: Фильтр по лиду
        limit: Максимум результатов
    
    Returns:
        JSON-массив сделок
    """
    conn = _get_conn()
    try:
        conditions = []
        params = []

        if status:
            conditions.append("d.status = ?")
            params.append(status)
        if lead_id is not None:
            conditions.append("d.lead_id = ?")
            params.append(lead_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT d.*, l.name AS lead_name
            FROM deals d
            LEFT JOIN leads l ON l.id = d.lead_id
            {where}
            ORDER BY d.created_at DESC
            LIMIT ?
        """
        rows = conn.execute(sql, params).fetchall()
        return json.dumps(_rows_to_dicts(rows), ensure_ascii=False, default=str)
    finally:
        conn.close()


@mcp.tool()
def create_deal(
    lead_id: int,
    user_id: int,
    title: str,
    amount: Optional[float] = None,
) -> str:
    """
    Создать сделку для лида.
    
    Args:
        lead_id: ID лида
        user_id: ID создающего пользователя
        title: Название сделки
        amount: Сумма сделки
    
    Returns:
        JSON с ID созданной сделки
    """
    conn = _get_conn_rw()
    try:
        cursor = conn.execute(
            """INSERT INTO deals (lead_id, user_id, title, amount, status)
               VALUES (?, ?, ?, ?, 'new')""",
            (lead_id, user_id, title, amount),
        )
        conn.commit()
        return json.dumps({"ok": True, "deal_id": cursor.lastrowid}, ensure_ascii=False)
    finally:
        conn.close()


@mcp.tool()
def update_deal_status(deal_id: int, status: str) -> str:
    """
    Обновить статус сделки.
    
    Args:
        deal_id: ID сделки
        status: Новый статус (new, in_progress, won, lost, paid)
    
    Returns:
        JSON с результатом
    """
    conn = _get_conn_rw()
    try:
        closed_at = datetime.now().isoformat() if status == "paid" else None
        conn.execute(
            "UPDATE deals SET status = ?, closed_at = ? WHERE id = ?",
            (status, closed_at, deal_id),
        )
        conn.commit()
        return json.dumps({"ok": True, "deal_id": deal_id, "status": status}, ensure_ascii=False)
    finally:
        conn.close()


# ===========================================================================
# TOOLS: Comments & Contact Logs
# ===========================================================================

@mcp.tool()
def add_comment(lead_id: int, user_id: int, body: str) -> str:
    """
    Добавить комментарий к лиду (после звонка/встречи).
    
    Args:
        lead_id: ID лида
        user_id: ID автора комментария
        body: Текст комментария
    
    Returns:
        JSON с ID комментария
    """
    conn = _get_conn_rw()
    try:
        cursor = conn.execute(
            "INSERT INTO comments (lead_id, user_id, body) VALUES (?, ?, ?)",
            (lead_id, user_id, body),
        )
        conn.commit()
        return json.dumps({"ok": True, "comment_id": cursor.lastrowid}, ensure_ascii=False)
    finally:
        conn.close()


@mcp.tool()
def add_contact_log(
    lead_id: int,
    user_id: int,
    result: str,
    contact_type: str = "call",
    outcome: Optional[str] = None,
    next_action_date: Optional[str] = None,
) -> str:
    """
    Записать контакт (звонок/встречу) с лидом.
    
    Args:
        lead_id: ID лида
        user_id: ID менеджера
        result: Результат контакта (текст)
        contact_type: Тип контакта (call, meeting, email, other)
        outcome: Исход (interested, not_interested, callback, no_answer, etc.)
        next_action_date: Дата следующего действия (YYYY-MM-DD)
    
    Returns:
        JSON с ID записи
    """
    conn = _get_conn_rw()
    try:
        cursor = conn.execute(
            """INSERT INTO contact_logs (lead_id, user_id, contact_type, contact_date, result, outcome, next_action_date)
               VALUES (?, ?, ?, datetime('now'), ?, ?, ?)""",
            (lead_id, user_id, contact_type, result, outcome, next_action_date),
        )
        # Автоматическая задача на перезвон
        if next_action_date:
            conn.execute(
                """INSERT INTO tasks (lead_id, assigned_to, created_by, title, due_date, priority, status)
                   VALUES (?, ?, ?, ?, ?, 1, 'pending')""",
                (lead_id, user_id, user_id, f"Перезвонить по лиду #{lead_id}", next_action_date),
            )
        conn.commit()
        return json.dumps({"ok": True, "log_id": cursor.lastrowid}, ensure_ascii=False)
    finally:
        conn.close()


@mcp.tool()
def add_contact(
    lead_id: int,
    phone: str,
    name: Optional[str] = None,
    position: Optional[str] = None,
    email: Optional[str] = None,
    is_decision_maker: bool = False,
    note: Optional[str] = None,
) -> str:
    """
    Добавить контактное лицо в карточку лида.

    Args:
        lead_id: ID лида
        phone: Телефон контакта (обязательно)
        name: Имя контактного лица
        position: Должность (например: Руководитель, Главный агроном)
        email: Email контакта
        is_decision_maker: Лицо принимает решения (True/False)
        note: Заметка о контакте

    Returns:
        JSON с ID созданного контакта
    """
    conn = _get_conn_rw()
    try:
        cursor = conn.execute(
            """INSERT INTO contacts (lead_id, name, position, phone, email, is_decision_maker, note)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (lead_id, name, position, phone, email, is_decision_maker, note),
        )
        conn.commit()
        return json.dumps({"ok": True, "contact_id": cursor.lastrowid}, ensure_ascii=False)
    finally:
        conn.close()


# ===========================================================================
# TOOLS: Documents
# ===========================================================================

@mcp.tool()
def get_lead_documents(lead_id: int) -> str:
    """
    Получить список документов лида.
    
    Args:
        lead_id: ID лида
    
    Returns:
        JSON-массив документов (договоры, счета, УПД и т.д.)
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM documents WHERE lead_id = ? ORDER BY created_at DESC",
            (lead_id,),
        ).fetchall()
        return json.dumps(_rows_to_dicts(rows), ensure_ascii=False, default=str)
    finally:
        conn.close()


@mcp.tool()
def get_templates() -> str:
    """
    Получить список доступных шаблонов документов.
    
    Returns:
        JSON-массив шаблонов
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, doc_type, placeholders, is_active FROM document_templates WHERE is_active = 1"
        ).fetchall()
        return json.dumps(_rows_to_dicts(rows), ensure_ascii=False, default=str)
    finally:
        conn.close()


# ===========================================================================
# TOOLS: Users
# ===========================================================================

@mcp.tool()
def list_users() -> str:
    """
    Получить список пользователей CRM (менеджеры и супервайзеры).
    
    Returns:
        JSON-массив пользователей
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, email, full_name, role, is_active FROM users WHERE is_active = 1"
        ).fetchall()
        return json.dumps(_rows_to_dicts(rows), ensure_ascii=False)
    finally:
        conn.close()


@mcp.tool()
def list_regions() -> str:
    """
    Получить список регионов.
    
    Returns:
        JSON-массив регионов
    """
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT id, name FROM regions ORDER BY name").fetchall()
        return json.dumps(_rows_to_dicts(rows), ensure_ascii=False)
    finally:
        conn.close()


# ===========================================================================
# TOOLS: Stage change
# ===========================================================================

@mcp.tool()
def change_lead_stage(lead_id: int, new_stage: str, user_id: int, note: Optional[str] = None) -> str:
    """
    Сменить стадию лида в воронке.
    
    Args:
        lead_id: ID лида
        new_stage: Новая стадия (0-7, lost)
        user_id: ID пользователя, инициировавшего смену
        note: Комментарий к смене стадии
    
    Returns:
        JSON с результатом
    """
    conn = _get_conn_rw()
    try:
        lead = conn.execute("SELECT stage FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not lead:
            return json.dumps({"error": f"Лид {lead_id} не найден"}, ensure_ascii=False)

        old_stage = lead["stage"]
        conn.execute(
            "UPDATE leads SET stage = ?, stage_changed_at = datetime('now') WHERE id = ?",
            (new_stage, lead_id),
        )
        conn.execute(
            """INSERT INTO stage_history (lead_id, from_stage, to_stage, changed_by, note)
               VALUES (?, ?, ?, ?, ?)""",
            (lead_id, old_stage, new_stage, user_id, note),
        )
        conn.commit()
        return json.dumps({
            "ok": True,
            "lead_id": lead_id,
            "from": old_stage,
            "to": new_stage,
        }, ensure_ascii=False)
    finally:
        conn.close()


# ===========================================================================
# TOOLS: DaData (внешний lookup компаний по ИНН)
# ===========================================================================
#
# Назначение: быстрые (~1с) запросы к DaData по ИНН — профиль компании и
# связанные юрлица. Альтернатива веб-поиску/браузеру по сайтам-реестрам,
# который виснет по 60с на антиспам-защите и разгоняет агента до 504.
# Кейс: «ООО Бугров, ИНН 2263023530 — это холдинг или нет?» → профиль +
# affiliated (0 связанных = не холдинг) за секунды вместо минут.

import urllib.request
import urllib.error


def _dadata_request(url: str, payload: dict) -> dict:
    """POST JSON к DaData. Возвращает распарсенный ответ или {error: ...}."""
    if not DADATA_API_KEY:
        return {"error": "DaData API key не настроен (DADATA_API_KEY пуст)"}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Token {DADATA_API_KEY}",
    }
    if DADATA_SECRET_KEY:
        headers["X-Secret"] = DADATA_SECRET_KEY
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"DaData HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"DaData недоступна: {e.reason}"}
    except Exception as e:
        return {"error": f"DaData: {e}"}


def _extract_party(suggestion: dict) -> dict:
    """Базовые реквизиты из одного suggestion DaData."""
    data = suggestion.get("data", {}) or {}
    mgmt = data.get("management", {}) or {}
    state = data.get("state", {}) or {}
    founders = data.get("founders", []) or []
    return {
        "inn": data.get("inn", ""),
        "ogrn": data.get("ogrn", ""),
        "kpp": data.get("kpp", ""),
        "name": (suggestion.get("value") or "").strip(),
        "full_name": (data.get("name", {}) or {}).get("full_with_opf", ""),
        "address": (data.get("address", {}) or {}).get("value", ""),
        "head_name": (mgmt.get("name") or "").strip(),
        "head_post": (mgmt.get("post") or "").strip(),
        "status": state.get("status", ""),
        "status_text": state.get("actuality_status", ""),
        "okved": data.get("okved", ""),
        "okved_name": data.get("okved_type", ""),
        "founders_count": len(founders),
        "founders": _extract_founders(founders),
        "branches_count": len(data.get("branches", []) or []),
    }


def _extract_founders(founders: list) -> list:
    """Первые 5 учредителей (имя/ИНН/доля)."""
    out = []
    for f in founders[:5]:
        if not isinstance(f, dict):
            continue
        name = f.get("name") or f.get("fio") or ""
        out.append({
            "name": (name or "").strip(),
            "inn": f.get("inn", ""),
            "share": _share_text(f),
        })
    return out


def _share_text(founder: dict) -> str:
    share = founder.get("share") or {}
    if not isinstance(share, dict):
        return ""
    pct = share.get("percent")
    if pct is not None:
        return f"{pct}%"
    return ""


@mcp.tool()
def lookup_company_by_inn(inn: str) -> str:
    """
    Профиль компании по ИНН/ОГРН через DaData (быстрый API, ~1с).
    Возвращает реквизиты: название, ОГРН, КПП, адрес, руководитель, статус,
    ОКВЭД, учредители. Используй для запросов «что за компания по ИНН»,
    «проверь контрагента», «найди реквизиты». Работает намного быстрее и
    надёжнее веб-поиска/браузера по сайтам-реестрам.

    Args:
        inn: ИНН (10 цифр для юрлица) или ОГРН компании.
    """
    payload = {"query": str(inn).strip(), "branch_type": "MAIN", "count": 1}
    resp = _dadata_request(DADATA_FIND_PARTY_URL, payload)
    if "error" in resp:
        return json.dumps(resp, ensure_ascii=False)
    suggestions = resp.get("suggestions", [])
    if not suggestions:
        return json.dumps(
            {"found": False, "message": f"Компания по ИНН {inn} не найдена"},
            ensure_ascii=False,
        )
    return json.dumps(
        {"found": True, "company": _extract_party(suggestions[0])},
        ensure_ascii=False,
    )


@mcp.tool()
def find_affiliated_companies(inn: str) -> str:
    """
    Связанные (аффилированные) компании по ИНН через DaData.
    Показывает юрлица с общими учредителями/руководителями — это позволяет
    ответить на вопрос «это холдинг или нет?»: если affiliated пусто — компания
    самостоятельная, не холдинг; если есть список — входит в группу.

    Args:
        inn: ИНН компании-ячейки (10 цифр).
    """
    payload = {"query": str(inn).strip(), "count": 20}
    resp = _dadata_request(DADATA_FIND_AFFILIATED_URL, payload)
    if "error" in resp:
        return json.dumps(resp, ensure_ascii=False)
    suggestions = resp.get("suggestions", [])
    affiliated = [_extract_party(s) for s in suggestions]
    return json.dumps({
        "inn": str(inn).strip(),
        "is_holding": len(affiliated) > 0,
        "affiliated_count": len(affiliated),
        "affiliated": affiliated,
    }, ensure_ascii=False)


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
