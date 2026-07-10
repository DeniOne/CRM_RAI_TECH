import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.database import init_db, async_session_maker
from app.services.report_service import (
    get_funnel_by_region, get_manager_kpi, get_funnel_bottlenecks
)


async def main():
    await init_db()
    async with async_session_maker() as session:
        funnel = await get_funnel_by_region(session)
        kpi = await get_manager_kpi(session)
        bottlenecks = await get_funnel_bottlenecks(session)

        os.makedirs("storage/exports", exist_ok=True)
        output = f"storage/exports/report_{int(time.time())}.xlsx"

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(funnel).to_excel(writer, sheet_name="Воронка", index=False)
            pd.DataFrame(kpi).to_excel(writer, sheet_name="KPI менеджеров", index=False)
            pd.DataFrame(bottlenecks).to_excel(writer, sheet_name="Просадки", index=False)

        print(f"Отчёт сохранён: {output}")


if __name__ == "__main__":
    asyncio.run(main())
