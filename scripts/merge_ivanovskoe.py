"""
Одноразовый скрипт: слияние дубля лида «Ивановское» (Новосибирская обл., Баганский р-н).

lead 554 «АО «Ивановское»» (drop, 16/32 полей, 4 контакта, реквизитов нет)
  → lead 559 «ЗАО «Ивановское»» (keep, 21/32 полей, 1 контакт, есть ogrn/kpp/okpo/
  legal_address/head_name — заполнены при обогащении DaData).

У обоих ИНН 5417100350, обе назначены на Веронику (mgr=5). Переносим 4 контакта
из 554 в 559 (там будут 1+4=5 контактов), остальные 7 дочерних таблиц пусты у обеих.
Field-merge не нужен — keep (559) по всем полям богаче или равен drop.

Безопасность: всё в одной транзакции, покрывает все 8 дочерних таблиц (включая
StageHistory и AgentMessage вне ORM-cascade), бэкап БД делается отдельно.
"""
import sqlite3
import sys

DB_PATH = "/app/storage/crm.db"
KEEP_ID = 559   # богаче: реквизиты заполнены при обогащении
DROP_ID = 554   # 4 контакта переносим, остальное пусто

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

    keep = cur.execute(
        "SELECT id, name, inn, assigned_manager_id FROM leads WHERE id=?", (KEEP_ID,)
    ).fetchone()
    drop = cur.execute(
        "SELECT id, name, inn, assigned_manager_id FROM leads WHERE id=?", (DROP_ID,)
    ).fetchone()
    if not keep:
        print(f"ОШИБКА: keep-лид id={KEEP_ID} не найден. Отмена."); return 1
    if not drop:
        print(f"ОШИБКА: drop-лид id={DROP_ID} не найден. Отмена."); return 1
    print(f"KEEP id={KEEP_ID}: name={keep['name']!r} inn={keep['inn']!r} mgr={keep['assigned_manager_id']}")
    print(f"DROP id={DROP_ID}: name={drop['name']!r} inn={drop['inn']!r} mgr={drop['assigned_manager_id']}")

    contacts_drop_before = cur.execute(
        "SELECT count(*) FROM contacts WHERE lead_id=?", (DROP_ID,)
    ).fetchone()[0]
    contacts_keep_before = cur.execute(
        "SELECT count(*) FROM contacts WHERE lead_id=?", (KEEP_ID,)
    ).fetchone()[0]
    print(f"Контактов до: keep={contacts_keep_before}, drop={contacts_drop_before}")

    try:
        cur.execute("BEGIN")
        moved = {}
        for table, col in CHILD_TABLES:
            n = cur.execute(
                f"UPDATE {table} SET {col}=? WHERE {col}=?", (KEEP_ID, DROP_ID)
            ).rowcount
            moved[f"{table}.{col}"] = n
        cur.execute("DELETE FROM leads WHERE id=?", (DROP_ID,))
        deleted = cur.rowcount
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"ОШИБКА при слиянии, транзакция откачена: {e}"); return 1
    finally:
        conn.close()

    print("\n=== Слияние выполнено ===")
    for k, n in moved.items():
        marker = "  ←" if n else ""
        print(f"  {k}: {n}{marker}")
    print(f"Удалено лидов: {deleted} (id={DROP_ID})")

    # Постпроверка.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    exists = cur.execute("SELECT count(*) FROM leads WHERE id=?", (DROP_ID,)).fetchone()[0]
    contacts_keep_after = cur.execute(
        "SELECT count(*) FROM contacts WHERE lead_id=?", (KEEP_ID,)
    ).fetchone()[0]
    keep_now = cur.execute(
        "SELECT id, name, inn, assigned_manager_id FROM leads WHERE id=?", (KEEP_ID,)
    ).fetchone()
    print("\n=== Постпроверка ===")
    print(f"Лид id={DROP_ID} существует: {exists} (должно быть 0)")
    print(f"Контактов у id={KEEP_ID}: {contacts_keep_after} (было {contacts_keep_before}, +{contacts_drop_before} перенесено)")
    print(f"keep: id={keep_now['id']} inn={keep_now['inn']!r} mgr={keep_now['assigned_manager_id']} (mgr должен остаться 5)")
    orphans = 0
    for table, col in CHILD_TABLES:
        n = cur.execute(f"SELECT count(*) FROM {table} WHERE {col}=?", (DROP_ID,)).fetchone()[0]
        if n:
            print(f"  ВНИМАНИЕ: orphaned {table}.{col}={DROP_ID}: {n}"); orphans += n
    conn.close()
    if orphans:
        print(f"\nОШИБКА: {orphans} orphaned-строк."); return 2
    print("Орфанных ссылок нет. Слияние чистое.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
