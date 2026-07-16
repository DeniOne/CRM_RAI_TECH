"""Одноразовая миграция стадий воронки (фаза 11).

Перенос кодов:
  6 «Счёт выставлен» → 5 «Договор + Счёт» (merge с существующим кодом 5)
  7 «Оплачено»      → 6 «Оплачено» (сдвиг)

Коды 0,1,2,3,4,lost — unchanged. postponed, новый код 7 — без данных.

Запуск: ОДИН РАЗ на целевой БД. Перед запуском делает бэкап.
"""
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB = Path("storage/crm.db")


def main():
    if not DB.exists():
        print(f"БД не найдена: {DB}")
        sys.exit(1)

    # 1. БЭКАП (обязательно)
    bak = DB.with_name(f"crm.db.before-migrate-v11-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(DB, bak)
    print(f"Бэкап: {bak}")

    con = sqlite3.connect(DB)
    cur = con.cursor()

    # Контрольный снимок «до»
    before = dict(cur.execute("SELECT stage, COUNT(*) FROM leads GROUP BY stage").fetchall())
    print("До:", before)

    # 2. Сдвиг 7 → 6 через временный маркер (коллизия: 6 валиден до миграции)
    #    Порядок: 7 → _tmp_paid → (5,6 → 5) → _tmp_paid → 6
    cur.execute("UPDATE leads SET stage='_tmp_paid' WHERE stage='7'")
    cur.execute("UPDATE stage_history SET from_stage='_tmp_paid' WHERE from_stage='7'")
    cur.execute("UPDATE stage_history SET to_stage='_tmp_paid' WHERE to_stage='7'")

    # 3. Merge 5,6 → 5 (бывшие «Договор» и «Счёт выставлен» → «Договор + Счёт»)
    cur.execute("UPDATE leads SET stage='5' WHERE stage IN ('5','6')")
    cur.execute("UPDATE stage_history SET from_stage='5' WHERE from_stage IN ('5','6')")
    cur.execute("UPDATE stage_history SET to_stage='5' WHERE to_stage IN ('5','6')")

    # 4. Финал: _tmp_paid → 6 («Оплачено»)
    cur.execute("UPDATE leads SET stage='6' WHERE stage='_tmp_paid'")
    cur.execute("UPDATE stage_history SET from_stage='6' WHERE from_stage='_tmp_paid'")
    cur.execute("UPDATE stage_history SET to_stage='6' WHERE to_stage='_tmp_paid'")

    con.commit()

    # Контрольный снимок «после»
    after = dict(cur.execute("SELECT stage, COUNT(*) FROM leads GROUP BY stage").fetchall())
    print("После:", after)

    # Санитарные проверки
    tmp = cur.execute("SELECT COUNT(*) FROM leads WHERE stage='_tmp_paid'").fetchone()[0]
    assert tmp == 0, f"Остались _tmp_paid записи: {tmp}"
    htmp = cur.execute(
        "SELECT COUNT(*) FROM stage_history WHERE from_stage='_tmp_paid' OR to_stage='_tmp_paid'"
    ).fetchone()[0]
    assert htmp == 0, f"Остались _tmp_paid в history: {htmp}"

    con.close()
    print("OK. Миграция применена. Суммы лидов до/после должны совпасть по затронутым кодам.")


if __name__ == "__main__":
    main()
