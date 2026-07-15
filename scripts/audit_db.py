"""Полный аудит целостности БД CRM_RAI.

Проверяет: orphan FK-ссылки по всем таблицам, аномалии, integrity_check.
Read-only — ничего не меняет.
"""
import sqlite3
import sys

DB = "/app/storage/crm.db"


def main():
    db = sqlite3.connect(DB)

    def chk(label, sql):
        n = db.execute(sql).fetchone()[0]
        flag = "❌" if n > 0 else "✅"
        print(f"{flag} {label}: {n}")

    print("===== USERS (id 1-6) =====")
    chk("users total", "SELECT count(*) FROM users")
    print("  список:", db.execute("SELECT id,email,full_name,role FROM users ORDER BY id").fetchall())

    print("\n===== LEADS =====")
    chk("leads total", "SELECT count(*) FROM leads")
    chk("assigned_manager_id -> users (orphan)",
        "SELECT count(*) FROM leads l LEFT JOIN users u ON l.assigned_manager_id=u.id "
        "WHERE l.assigned_manager_id IS NOT NULL AND u.id IS NULL")
    chk("assigned_manager_id NULL", "SELECT count(*) FROM leads WHERE assigned_manager_id IS NULL")
    chk("region_id -> regions (orphan)",
        "SELECT count(*) FROM leads l LEFT JOIN regions r ON l.region_id=r.id WHERE r.id IS NULL")
    chk("stage NOT in валидных",
        "SELECT count(*) FROM leads WHERE stage NOT IN ('0','1','2','3','4','5','6','7','lost')")
    print("  by stage:", dict(db.execute("SELECT stage,count(*) FROM leads GROUP BY stage").fetchall()))
    print("  by assigned_manager:", dict(
        db.execute("SELECT assigned_manager_id,count(*) FROM leads GROUP BY assigned_manager_id").fetchall()))

    print("\n===== TASKS =====")
    chk("tasks total", "SELECT count(*) FROM tasks")
    chk("lead_id -> leads (orphan)",
        "SELECT count(*) FROM tasks t LEFT JOIN leads l ON t.lead_id=l.id WHERE l.id IS NULL")
    chk("assigned_to -> users (orphan)",
        "SELECT count(*) FROM tasks t LEFT JOIN users u ON t.assigned_to=u.id WHERE u.id IS NULL")
    chk("created_by -> users (orphan)",
        "SELECT count(*) FROM tasks t LEFT JOIN users u ON t.created_by=u.id WHERE u.id IS NULL")
    chk("status NOT in валидных",
        "SELECT count(*) FROM tasks WHERE status NOT IN ('pending','in_progress','done','cancelled')")
    print("  by status:", dict(db.execute("SELECT status,count(*) FROM tasks GROUP BY status").fetchall()))
    print("  by assigned_to:", dict(db.execute("SELECT assigned_to,count(*) FROM tasks GROUP BY assigned_to").fetchall()))

    print("\n===== CONTACT_LOGS =====")
    chk("contact_logs total", "SELECT count(*) FROM contact_logs")
    chk("lead_id -> leads (orphan)",
        "SELECT count(*) FROM contact_logs c LEFT JOIN leads l ON c.lead_id=l.id WHERE l.id IS NULL")
    chk("user_id -> users (orphan)",
        "SELECT count(*) FROM contact_logs c LEFT JOIN users u ON c.user_id=u.id "
        "WHERE c.user_id IS NOT NULL AND u.id IS NULL")
    chk("user_id NULL", "SELECT count(*) FROM contact_logs WHERE user_id IS NULL")
    chk("comment_id -> comments (orphan)",
        "SELECT count(*) FROM contact_logs c LEFT JOIN comments cm ON c.comment_id=cm.id "
        "WHERE c.comment_id IS NOT NULL AND cm.id IS NULL")
    chk("task_id -> tasks (orphan)",
        "SELECT count(*) FROM contact_logs c LEFT JOIN tasks t ON c.task_id=t.id "
        "WHERE c.task_id IS NOT NULL AND t.id IS NULL")
    print("  user_id distribution:", dict(
        db.execute("SELECT user_id,count(*) FROM contact_logs GROUP BY user_id").fetchall()))

    print("\n===== COMMENTS =====")
    chk("comments total", "SELECT count(*) FROM comments")
    chk("lead_id -> leads (orphan)",
        "SELECT count(*) FROM comments c LEFT JOIN leads l ON c.lead_id=l.id WHERE l.id IS NULL")
    chk("user_id -> users (orphan)",
        "SELECT count(*) FROM comments c LEFT JOIN users u ON c.user_id=u.id WHERE u.id IS NULL")

    print("\n===== CONTACTS (телефоны/emails) =====")
    chk("contacts total", "SELECT count(*) FROM contacts")
    chk("lead_id -> leads (orphan)",
        "SELECT count(*) FROM contacts c LEFT JOIN leads l ON c.lead_id=l.id WHERE l.id IS NULL")

    print("\n===== STAGE_HISTORY =====")
    chk("stage_history total", "SELECT count(*) FROM stage_history")
    chk("lead_id -> leads (orphan)",
        "SELECT count(*) FROM stage_history s LEFT JOIN leads l ON s.lead_id=l.id WHERE l.id IS NULL")
    chk("changed_by -> users (orphan)",
        "SELECT count(*) FROM stage_history s LEFT JOIN users u ON s.changed_by=u.id "
        "WHERE s.changed_by IS NOT NULL AND u.id IS NULL")

    print("\n===== AGENT_MESSAGES =====")
    chk("agent_messages total", "SELECT count(*) FROM agent_messages")
    chk("user_id -> users (orphan)",
        "SELECT count(*) FROM agent_messages a LEFT JOIN users u ON a.user_id=u.id WHERE u.id IS NULL")

    print("\n===== REGIONS =====")
    chk("regions total", "SELECT count(*) FROM regions")

    print("\n===== INTEGRITY =====")
    print("  integrity_check:", db.execute("PRAGMA integrity_check").fetchone()[0])
    print("  foreign_key_check:", db.execute("PRAGMA foreign_key_check").fetchall() or "none")

    db.close()


if __name__ == "__main__":
    main()
