"""
Одноразовый скрипт: слияние дубля лида «СПК колхоз «Плельский»».

lead 95 (drop, ИНН пустой) → lead 79 (keep, ИНН 4331000136).
Переносим все дочерние сущности (контакты, логи, комментарии, задачи,
сделки, документы, историю стадий, agent_messages) на lead 79, затем
удаляем дубль id=95.

Безопасность:
- всё в одной транзакции (BEGIN/COMMIT), откат при ошибке;
- бэкап БД делается отдельно перед запуском (см. инструкции в коммите);
- покрывает ВСЕ 8 дочерних таблиц, включая StageHistory и AgentMessage,
  которые не попадают в ORM-cascade Lead.relationship().

Запуск на сервере:
  docker cp scripts/merge_plessky.py crm-rai-dev:/app/scripts/merge_plessky.py
  docker exec crm-rai-dev python scripts/merge_plessky.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = "/app/storage/crm.db"
KEEP_ID = 79   # каноничная запись с ИНН 4331000136
DROP_ID = 95   # дубль без ИНН

# Дочерние таблицы с FK на leads.id.
# (таблица, колонка) — все, кроме leads, кто ссылается на leads.id.
# StageHistory и AgentMessage вне ORM-cascade — обязательны к ручному переносу.
CHILD_TABLES = [
    ("contacts", "lead_id"),
    ("contact_logs", "lead_id"),
    ("comments", "lead_id"),
    ("tasks", "lead_id"),
    ("deals", "lead_id"),
    ("documents", "lead_id"),
    ("stage_history", "lead_id"),
    ("agent_messages", "context_lead_id"),
]


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Предпроверка: оба лида существуют и это действительно дубль.
    keep = cur.execute(
        "SELECT id, name, inn, assigned_manager_id FROM leads WHERE id=?", (KEEP_ID,)
    ).fetchone()
    drop = cur.execute(
        "SELECT id, name, inn, assigned_manager_id FROM leads WHERE id=?", (DROP_ID,)
    ).fetchone()
    if not keep:
        print(f"ОШИБКА: keep-лид id={KEEP_ID} не найден. Отмена.")
        return 1
    if not drop:
        print(f"ОШИБКА: drop-лид id={DROP_ID} не найден. Отмена.")
        return 1
    print(f"KEEP id={KEEP_ID}: name={keep['name']!r} inn={keep['inn']!r} mgr={keep['assigned_manager_id']}")
    print(f"DROP id={DROP_ID}: name={drop['name']!r} inn={drop['inn']!r} mgr={drop['assigned_manager_id']}")
    if keep["name"] != drop["name"]:
        print("ВНИМАНИЕ: названия различаются — это может быть не дубль. Продолжаем, но проверь.")

    # Считаем дочерние строки до переноса (для отчёта).
    before_counts = {}
    for table, col in CHILD_TABLES:
        n = cur.execute(f"SELECT count(*) FROM {table} WHERE {col}=?", (DROP_ID,)).fetchone()[0]
        before_counts[f"{table}.{col}"] = n

    try:
        cur.execute("BEGIN")

        # 1. Перенос дочерних строк: lead_id/context_lead_id 95 → 79.
        moved = {}
        for table, col in CHILD_TABLES:
            n = cur.execute(
                f"UPDATE {table} SET {col}=? WHERE {col}=?", (KEEP_ID, DROP_ID)
            ).rowcount
            moved[f"{table}.{col}"] = n

        # 2. Field-merge: заполняем пустые поля keep из drop (только где у keep NULL).
        # head_name у keep уже чище («Язынин Игорь Александрович» без префикса «Председатель:»),
        # district у keep тоже лучше — поэтому field-merge НЕ делаем, keep выигрывает полностью.
        # Поле inn у keep заполнено — не трогаем.
        # (Оставлено место для будущего field-merge, если потребуется.)

        # 3. Удаление дубля.
        cur.execute("DELETE FROM leads WHERE id=?", (DROP_ID,))
        deleted = cur.rowcount

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"ОШИБКА при слиянии, транзакция откачена: {e}")
        return 1
    finally:
        conn.close()

    # Отчёт.
    print("\n=== Слияние выполнено ===")
    print(f"Перенесено дочерних строк (95 → 79):")
    for k, n in moved.items():
        marker = " ←" if n else ""
        print(f"  {k}: {n}{marker}")
    print(f"Удалено лидов: {deleted} (id={DROP_ID})")

    # Постпроверка через свежее подключение.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    exists = cur.execute("SELECT count(*) FROM leads WHERE id=?", (DROP_ID,)).fetchone()[0]
    contacts_keep = cur.execute(
        "SELECT count(*) FROM contacts WHERE lead_id=?", (KEEP_ID,)
    ).fetchone()[0]
    keep_now = cur.execute(
        "SELECT id, name, inn, assigned_manager_id FROM leads WHERE id=?", (KEEP_ID,)
    ).fetchone()
    print("\n=== Постпроверка ===")
    print(f"Лид id={DROP_ID} существует: {exists} (должно быть 0)")
    print(f"Контактов у id={KEEP_ID}: {contacts_keep} (было 2, +1 перенесён = 3)")
    print(f"keep: id={keep_now['id']} inn={keep_now['inn']!r} mgr={keep_now['assigned_manager_id']} (mgr должен остаться 4)")
    conn.close()

    # Проверка, что у drop не осталось orphaned-ссылок ни в одной дочерней таблице.
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    orphans = 0
    for table, col in CHILD_TABLES:
        n = cur.execute(f"SELECT count(*) FROM {table} WHERE {col}=?", (DROP_ID,)).fetchone()[0]
        if n:
            print(f"  ВНИМАНИЕ: orphaned {table}.{col}={DROP_ID}: {n} строк!")
            orphans += n
    conn.close()
    if orphans:
        print(f"\nОШИБКА: {orphans} orphaned-строк осталось. Проверь вручную.")
        return 2
    print("\nОрфанных ссылок нет. Слияние чистое.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
