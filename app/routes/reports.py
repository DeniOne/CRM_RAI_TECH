import os
import tempfile
import time
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.services.report_service import (
    get_funnel_by_region, get_funnel_totals, get_manager_kpi,
    get_funnel_bottlenecks, get_stage_history_stats
)

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


@router.get("/reports/export")
async def export_report(request: Request, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request, session)
    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(status_code=403)

    funnel_regions = await get_funnel_by_region(session)
    kpi_list = await get_manager_kpi(session)
    bottlenecks = await get_funnel_bottlenecks(session)

    df_funnel = pd.DataFrame(funnel_regions)
    df_kpi = pd.DataFrame(kpi_list)
    df_bottlenecks = pd.DataFrame(bottlenecks)

    output_path = os.path.join(tempfile.gettempdir(), f"crm_report_{int(time.time())}.xlsx")
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_funnel.to_excel(writer, sheet_name="Воронка", index=False)
        df_kpi.to_excel(writer, sheet_name="KPI менеджеров", index=False)
        df_bottlenecks.to_excel(writer, sheet_name="Просадки", index=False)

    return FileResponse(output_path, filename="crm_report.xlsx")
