from datetime import datetime

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Region, User, UserRole
from app.services.report_service import (
    get_funnel_by_region, get_funnel_totals, get_manager_kpi,
    get_funnel_bottlenecks, get_stage_history_stats,
    get_lost_leads, get_deals_pipeline,
)
from app.services.export_renderers import render_xlsx, render_docx

router = APIRouter()


@router.get("/reports", response_class=HTMLResponse)
async def supervisor_dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(status_code=403)

    funnel_totals = await get_funnel_totals(session)
    funnel_regions = await get_funnel_by_region(session)
    bottlenecks = await get_funnel_bottlenecks(session)
    history_stats = await get_stage_history_stats(session)

    return templates.TemplateResponse(
        request=request,
        name="supervisor_dashboard.html",
        context={
            "current_user": user,
            "funnel_totals": funnel_totals,
            "funnel_regions": funnel_regions[:10],
            "bottlenecks": bottlenecks,
            "history_stats": history_stats,
        },
    )


@router.get("/reports/funnel", response_class=HTMLResponse)
async def funnel_report(request: Request, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(status_code=403)

    funnel_regions = await get_funnel_by_region(session)
    funnel_totals = await get_funnel_totals(session)

    return templates.TemplateResponse(
        request=request,
        name="funnel_report.html",
        context={
            "current_user": user,
            "funnel_regions": funnel_regions,
            "funnel_totals": funnel_totals,
        },
    )


@router.get("/reports/managers", response_class=HTMLResponse)
async def managers_report(
    request: Request,
    date_from: str = None,
    date_to: str = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)
    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(status_code=403)

    df = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    dt = datetime.strptime(date_to, "%Y-%m-%d") if date_to else None

    kpi_list = await get_manager_kpi(session, df, dt)

    return templates.TemplateResponse(
        request=request,
        name="managers_report.html",
        context={
            "current_user": user,
            "kpi_list": kpi_list,
            "date_from": date_from or "",
            "date_to": date_to or "",
        },
    )


@router.get("/reports/center", response_class=HTMLResponse)
async def reports_center(request: Request, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(status_code=403)

    regions_result = await session.execute(select(Region).order_by(Region.name))
    regions = regions_result.scalars().all()

    managers_result = await session.execute(
        select(User).where(User.role == UserRole.manager).order_by(User.full_name)
    )
    managers = managers_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="reports_center.html",
        context={
            "current_user": user,
            "regions": regions,
            "managers": managers,
        },
    )


@router.get("/reports/download")
async def download_report(
    request: Request,
    report: str,
    format: str = "xlsx",
    date_from: str = None,
    date_to: str = None,
    region_id: int = None,
    manager_id: int = None,
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)
    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(status_code=403)

    df = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    dt = datetime.strptime(date_to, "%Y-%m-%d") if date_to else None

    if format not in ("xlsx", "docx"):
        raise HTTPException(status_code=400, detail="Неизвестный формат")

    # Dispatch по типу отчёта
    if report == "funnel":
        data = await get_funnel_totals(session, region_id, manager_id, df, dt)
        stages = data["stages"]
        if format == "xlsx":
            rows = [{"Стадия": s["label"], "Количество": s["count"], "Конверсия от входа %": s["conversion_pct"] or ""} for s in stages]
            return render_xlsx([("Воронка", rows)], "report_funnel.xlsx")
        else:
            headers = ["Стадия", "Количество", "Конверсия от входа %"]
            rows = [[s["label"], s["count"], s["conversion_pct"] or ""] for s in stages]
            period = _format_period(df, dt)
            return render_docx("Воронка продаж", period, headers, rows, "report_funnel.docx")

    elif report == "managers":
        kpi = await get_manager_kpi(session, df, dt, manager_id, region_id)
        if format == "xlsx":
            rows = [{
                "Менеджер": k["full_name"], "Роль": k["role"],
                "Лидов": k["total_leads"], "Звонков": k["calls_count"],
                "КП": k["kp_sent"], "Сделок": k["deals_count"],
                "Конверсия %": k["conversion_rate"],
            } for k in kpi]
            return render_xlsx([("KPI", rows)], "report_managers.xlsx")
        else:
            headers = ["Менеджер", "Роль", "Лидов", "Звонков", "КП", "Сделок", "Конверсия %"]
            rows = [[k["full_name"], k["role"], k["total_leads"], k["calls_count"], k["kp_sent"], k["deals_count"], k["conversion_rate"]] for k in kpi]
            period = _format_period(df, dt)
            return render_docx("KPI менеджеров", period, headers, rows, "report_managers.docx")

    elif report == "lost_leads":
        lost = await get_lost_leads(session, region_id, manager_id, df, dt)
        if format == "xlsx":
            rows = [{"Причина": l["reason"], "Количество": l["count"], "Примеры": l["examples"]} for l in lost]
            return render_xlsx([("Потерянные", rows)], "report_lost_leads.xlsx")
        else:
            headers = ["Причина", "Количество", "Примеры"]
            rows = [[l["reason"], l["count"], l["examples"]] for l in lost]
            period = _format_period(df, dt)
            return render_docx("Потерянные лиды", period, headers, rows, "report_lost_leads.docx")

    elif report == "deals_pipeline":
        pipeline = await get_deals_pipeline(session, region_id, manager_id, df, dt)
        if format == "xlsx":
            rows = [{"Статус": p["status_label"], "Количество": p["count"], "Сумма": p["total_amount"]} for p in pipeline]
            return render_xlsx([("Пайплайн", rows)], "report_deals_pipeline.xlsx")
        else:
            headers = ["Статус", "Количество", "Сумма"]
            rows = [[p["status_label"], p["count"], p["total_amount"]] for p in pipeline]
            period = _format_period(df, dt)
            return render_docx("Пайплайн сделок", period, headers, rows, "report_deals_pipeline.docx")

    else:
        raise HTTPException(status_code=400, detail="Неизвестный тип отчёта")


@router.get("/reports/export")
async def export_report_legacy(
    request: Request,
    report: str = "funnel",
    format: str = "xlsx",
    date_from: str = None,
    date_to: str = None,
    region_id: int = None,
    manager_id: int = None,
    session: AsyncSession = Depends(get_session),
):
    """Alias для обратной совместимости со старыми bookmark'ами."""
    return await download_report(
        request, report=report, format=format,
        date_from=date_from, date_to=date_to,
        region_id=region_id, manager_id=manager_id,
        session=session,
    )


def _format_period(df, dt) -> str:
    if df and dt:
        return f"{df.strftime('%d.%m.%Y')} — {dt.strftime('%d.%m.%Y')}"
    if df:
        return f"с {df.strftime('%d.%m.%Y')}"
    if dt:
        return f"по {dt.strftime('%d.%m.%Y')}"
    return "Весь период"
