"""Сравнение row-counts между самым старым бэкапом и текущей БД.

Цель: проверить, не потерялись ли данные за всё время моего вмешательства.
"""
import sqlite3
import sys

TABLES = [
    "users", "leads", "tasks", "contact_logs", "comments", "contacts",
    "stage_history", "agent_messages", "regions", "deals", "documents",
    "invites", "library_files", "library_folders", "document_templates",
]


def counts(db_path):
    db = sqlite3.connect(db_path)
    r = {}
    for t in TABLES:
        try:
            r[t] = db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            r[t] = None  # таблицы нет
    db.close()
    return r


def main():
    old_path = sys.argv[1] if len(sys.argv) > 1 else "/data/crm.db.bak_20260713_100944"
    new_path = sys.argv[2] if len(sys.argv) > 2 else "/data/crm.db"
    old = counts(old_path)
    new = counts(new_path)

    print(f"{'table':<20} {'13июл(до)':>12} {'сейчас':>10} {'дельта':>10}")
    print("-" * 56)
    for t in TABLES:
        o, n = old[t], new[t]
        if o is None and n is None:
            continue
        if o is None:
            print(f"{t:<20} {'(нет)':>12} {n:>10}")
            continue
        if n is None:
            print(f"{t:<20} {o:>12} {'(нет)':>10}  ⚠ ПОТЕРЯ ТАБЛИЦЫ")
            continue
        d = n - o
        mark = "  ⚠ ПОТЕРЯ ДАННЫХ" if d < 0 else ""
        print(f"{t:<20} {o:>12} {n:>10} {d:>+10}{mark}")


if __name__ == "__main__":
    main()
