from fastapi import APIRouter, Request, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Lead, Region

router = APIRouter()


@router.get("/")
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    from app.main import templates

    user = await get_current_user(request, session)

    total_leads = await session.scalar(select(func.count(Lead.id)))

    stage_rows = await session.execute(
        select(Lead.stage, func.count(Lead.id)).group_by(Lead.stage)
    )
    by_stage = {row[0]: row[1] for row in stage_rows}

    region_rows = await session.execute(
        select(Region.name, func.count(Lead.id))
        .join(Lead, Lead.region_id == Region.id)
        .group_by(Region.name)
        .order_by(func.count(Lead.id).desc())
    )
    by_region = [{"name": row[0], "total": row[1]} for row in region_rows]

    level_rows = await session.execute(
        select(Lead.level, func.count(Lead.id)).group_by(Lead.level)
    )
    by_level = {row[0] or "—": row[1] for row in level_rows}

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "current_user": user,
            "total_leads": total_leads,
            "by_stage": by_stage,
            "by_region": by_region,
            "by_level": by_level,
        },
    )
