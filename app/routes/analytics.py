"""Аналитика продаж (фаза 22): воронка КП, факт оплат, ABC-анализ по выручке /
количеству / прибыли, разрезы по категориям и менеджерам. Supervisor/admin.
"""

import io
from datetime import datetime

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_session
from app.models import User
from app.services import analytics_service as ans

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _parse_date(raw: str | None):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


async def _guard(request: Request, session: AsyncSession):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    await require_role("supervisor", "admin")(request, session)
    return user


async def _context(session, date_from, date_to, manager_id):
    data = await ans.sales_analytics(session, date_from, date_to, manager_id)
    users = (await session.execute(select(User).where(User.is_active == True).order_by(User.full_name))).scalars().all()  # noqa: E712
    return {**data, "users": users}


@router.get("")
async def analytics_page(
    request: Request,
    date_from: str = None,
    date_to: str = None,
    manager_id: str = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates

    user = await _guard(request, session)
    ctx = await _context(session, _parse_date(date_from), _parse_date(date_to),
                         int(manager_id) if manager_id and manager_id.isdigit() else None)
    return templates.TemplateResponse(
        request=request, name="analytics.html",
        context={"current_user": user, "date_from": date_from or "", "date_to": date_to or "",
                 "manager_id": manager_id or "", **ctx},
    )


@router.get("/export")
async def analytics_export(
    request: Request,
    date_from: str = None,
    date_to: str = None,
    manager_id: str = None,
    session: AsyncSession = Depends(get_session),
):
    await _guard(request, session)
    data = await ans.sales_analytics(session, _parse_date(date_from), _parse_date(date_to),
                                     int(manager_id) if manager_id and manager_id.isdigit() else None)

    wb = openpyxl.Workbook()

    def sheet(title: str, header: list[str], rows: list[list]) -> None:
        ws = wb.create_sheet(title[:31])
        ws.append(header)
        for r in rows:
            ws.append(r)

    def abc_rows(items: list[dict], measure_col: str):
        return [[r["name"], round(r["qty"], 2), round(r["revenue"], 2),
                 round(r["profit"], 2) if r["profit"] is not None and r["has_profit"] else "",
                 round(r["share"], 1), round(r["cum"], 1), r["abc"]] for r in items]

    header = ["Товар", "Кол-во", "Выручка с НДС", "Прибыль", "Доля %", "Кумулятивно %", "ABC"]
    sheet("ABC выручка", header, abc_rows(data["abc_revenue"], "revenue"))
    sheet("ABC количество", header, abc_rows(data["abc_qty"], "qty"))
    sheet("ABC прибыль", header, abc_rows(data["abc_profit"], "profit"))
    sheet("Категории", ["Категория", "Кол-во", "Выручка с НДС", "Прибыль"],
          [[c["name"], round(c["qty"], 2), round(c["revenue"], 2),
            round(c["profit"], 2) if c["has_profit"] else ""] for c in data["categories"]])
    sheet("Менеджеры", ["Менеджер", "Кол-во", "Выручка с НДС", "Прибыль"],
          [[m["name"], round(m["qty"], 2), round(m["revenue"], 2),
            round(m["profit"], 2) if m["has_profit"] else ""] for m in data["managers"]])
    del wb["Sheet"]

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sales_analytics.xlsx"},
    )
