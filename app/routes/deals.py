from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_session
from app.models import Deal, Lead

router = APIRouter()


@router.get("/deals", response_class=HTMLResponse)
async def deals_page(
    request: Request,
    status: str = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    filters = []
    if status:
        filters.append(Deal.status == status)

    result = await session.execute(
        select(Deal).where(*filters).options(selectinload(Deal.lead)).order_by(Deal.created_at.desc())
    )
    deals = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="deals.html",
        context={"current_user": user, "deals": deals, "status": status},
    )


@router.get("/leads/{lead_id}/deals", response_class=HTMLResponse)
async def lead_deals(
    request: Request,
    lead_id: int,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    result = await session.execute(
        select(Deal).where(Deal.lead_id == lead_id).options(selectinload(Deal.lead)).order_by(Deal.created_at.desc())
    )
    deals = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="partials/deals_list.html",
        context={"current_user": user, "deals": deals, "lead_id": lead_id},
    )


@router.post("/leads/{lead_id}/deals", response_class=HTMLResponse)
async def create_deal(
    request: Request,
    lead_id: int,
    title: str = Form(...),
    amount: float = Form(None),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    deal = Deal(
        lead_id=lead_id,
        user_id=user.id,
        title=title,
        amount=amount,
        status="new",
    )
    session.add(deal)
    await session.commit()

    result = await session.execute(
        select(Deal).where(Deal.lead_id == lead_id).options(selectinload(Deal.lead)).order_by(Deal.created_at.desc())
    )
    deals = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="partials/deals_list.html",
        context={"current_user": user, "deals": deals, "lead_id": lead_id},
    )


@router.post("/deals/{deal_id}/status", response_class=HTMLResponse)
async def update_deal_status(
    request: Request,
    deal_id: int,
    status: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    result = await session.execute(
        select(Deal).where(Deal.id == deal_id).options(selectinload(Deal.lead))
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404)

    deal.status = status
    if status == "paid":
        deal.closed_at = datetime.now()

    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/deal_row.html",
        context={"current_user": user, "deal": deal},
    )
