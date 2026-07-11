from datetime import datetime, date

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_session
from app.models import Lead, Contact, ContactLog, Comment, Task, User, Region
from app.services.funnel_service import (
    STAGES, STAGE_LABELS, STAGE_COLORS, change_stage, validate_transition
)
from app.services.dadata_service import find_party_by_inn, suggest_party

router = APIRouter()


@router.get("/kanban", response_class=HTMLResponse)
async def kanban(
    request: Request,
    manager: str = None,
    region: int = None,
    level: str = None,
    priority: int = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    if manager is None:
        manager = "my" if user.role.value == "manager" else "all"

    if manager == "my" and user.role.value == "manager":
        base_filter = Lead.assigned_manager_id == user.id
    else:
        base_filter = True

    filters = [base_filter]
    if region:
        filters.append(Lead.region_id == region)
    if level:
        filters.append(Lead.level == level)
    if priority:
        filters.append(Lead.priority == priority)

    result = await session.execute(
        select(Lead).where(*filters).options(selectinload(Lead.region)).order_by(Lead.name)
    )
    leads = result.scalars().all()

    leads_by_stage = {s: [] for s in STAGES}
    for lead in leads:
        if lead.stage in leads_by_stage:
            leads_by_stage[lead.stage].append(lead)

    regions_result = await session.execute(select(Region).order_by(Region.name))
    regions = regions_result.scalars().all()

    stages_data = []
    for code in STAGES:
        stages_data.append({
            "code": code,
            "label": STAGE_LABELS[code],
            "color": STAGE_COLORS[code],
            "leads": leads_by_stage[code],
            "count": len(leads_by_stage[code]),
        })

    return templates.TemplateResponse(
        request=request,
        name="kanban.html",
        context={
            "current_user": user,
            "stages": stages_data,
            "regions": regions,
            "manager": manager,
            "level": level,
            "priority": priority,
            "region_id": region,
        },
    )


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
async def lead_card(request: Request, lead_id: int, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)

    result = await session.execute(
        select(Lead).where(Lead.id == lead_id).options(
            selectinload(Lead.contacts),
            selectinload(Lead.contact_logs),
            selectinload(Lead.comments),
            selectinload(Lead.tasks),
            selectinload(Lead.region),
            selectinload(Lead.documents),
            selectinload(Lead.deals),
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    users_result = await session.execute(select(User).where(User.is_active == True))
    users = users_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="lead_card.html",
        context={
            "current_user": user,
            "lead": lead,
            "stage_label": STAGE_LABELS.get(lead.stage, lead.stage),
            "users": users,
        },
    )


@router.post("/api/leads/{lead_id}/stage")
async def api_change_stage(
    request: Request,
    lead_id: int,
    stage: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)
    try:
        lead = await change_stage(session, lead_id, stage, user.id)
        await session.commit()
        return {"ok": True, "stage": lead.stage}
    except ValueError as e:
        errors = e.args[0] if isinstance(e.args[0], list) else [str(e)]
        raise HTTPException(status_code=422, detail={"errors": errors})


@router.post("/leads/{lead_id}/edit", response_class=HTMLResponse)
async def lead_edit(
    request: Request,
    lead_id: int,
    session: AsyncSession = Depends(get_session),
    rapeseed_verified: bool = Form(False),
    rapeseed_volume: str = Form(""),
    harvest_timing: str = Form(""),
    level: str = Form(""),
    priority: int = Form(None),
    inn: str = Form(""),
    head_name: str = Form(""),
    site: str = Form(""),
    general_comment: str = Form(""),
    done_summary: str = Form(""),
    todo_summary: str = Form(""),
    loss_reason: str = Form(""),
):
    from app.main import templates
    user = await get_current_user(request, session)

    result = await session.execute(
        select(Lead).where(Lead.id == lead_id).options(
            selectinload(Lead.contacts),
            selectinload(Lead.contact_logs),
            selectinload(Lead.comments),
            selectinload(Lead.tasks),
            selectinload(Lead.region),
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404)

    lead.rapeseed_verified = rapeseed_verified
    lead.rapeseed_volume = rapeseed_volume or None
    lead.harvest_timing = harvest_timing or None
    lead.level = level if level in ("A", "B", "C") else None
    lead.priority = priority
    lead.inn = inn or None
    lead.head_name = head_name or None
    lead.site = site or None
    lead.general_comment = general_comment or None
    lead.done_summary = done_summary or None
    lead.todo_summary = todo_summary or None
    if lead.stage == "lost":
        lead.loss_reason = loss_reason or None

    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/lead_info_form.html",
        context={"current_user": user, "lead": lead},
    )


@router.post("/leads/{lead_id}/contacts", response_class=HTMLResponse)
async def add_contact(
    request: Request,
    lead_id: int,
    name: str = Form(""),
    position: str = Form(""),
    phone: str = Form(...),
    email: str = Form(""),
    is_decision_maker: bool = Form(False),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    contact = Contact(
        lead_id=lead_id,
        name=name or None,
        position=position or None,
        phone=phone,
        email=email or None,
        is_decision_maker=is_decision_maker,
    )
    session.add(contact)
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/contact_row.html",
        context={"current_user": user, "contact": contact, "lead_id": lead_id},
    )


@router.post("/leads/{lead_id}/contacts/{contact_id}/toggle-dm", response_class=HTMLResponse)
async def toggle_dm(
    request: Request,
    lead_id: int,
    contact_id: int,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    result = await session.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404)

    contact.is_decision_maker = not contact.is_decision_maker
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/contact_row.html",
        context={"current_user": user, "contact": contact, "lead_id": lead_id},
    )


@router.post("/leads/{lead_id}/contact-log", response_class=HTMLResponse)
async def add_contact_log(
    request: Request,
    lead_id: int,
    contact_type: str = Form("call"),
    result: str = Form(...),
    outcome: str = Form(""),
    next_action_date: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    lead_result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead = lead_result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404)

    next_date = None
    if next_action_date:
        try:
            next_date = datetime.strptime(next_action_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    log = ContactLog(
        lead_id=lead_id,
        user_id=user.id,
        contact_type=contact_type,
        contact_date=datetime.now(),
        result=result,
        outcome=outcome or None,
        next_action_date=next_date,
    )
    session.add(log)

    if next_date:
        task = Task(
            lead_id=lead_id,
            assigned_to=user.id,
            created_by=user.id,
            title=f"Перезвонить: {lead.name}",
            due_date=datetime.combine(next_date, datetime.min.time()),
            priority=1,
            status="pending",
        )
        session.add(task)

    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/contact_log_row.html",
        context={"current_user": user, "log": log},
    )


@router.post("/leads/{lead_id}/comments", response_class=HTMLResponse)
async def add_comment(
    request: Request,
    lead_id: int,
    body: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    comment = Comment(
        lead_id=lead_id,
        user_id=user.id,
        body=body,
    )
    session.add(comment)
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/comment_row.html",
        context={"current_user": user, "comment": comment},
    )


@router.post("/leads/{lead_id}/assign", response_class=HTMLResponse)
async def assign_manager(
    request: Request,
    lead_id: int,
    manager_id: int = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(status_code=403)

    result = await session.execute(
        select(Lead).where(Lead.id == lead_id).options(
            selectinload(Lead.contacts),
            selectinload(Lead.contact_logs),
            selectinload(Lead.comments),
            selectinload(Lead.tasks),
            selectinload(Lead.region),
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404)

    lead.assigned_manager_id = manager_id
    await session.commit()

    users_result = await session.execute(select(User).where(User.is_active == True))
    users = users_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="partials/lead_info_form.html",
        context={"current_user": user, "lead": lead, "users": users},
    )


@router.get("/leads/{lead_id}/contacts/form", response_class=HTMLResponse)
async def contact_form(request: Request, lead_id: int, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    return templates.TemplateResponse(
        request=request,
        name="partials/contact_form.html",
        context={"current_user": user, "lead_id": lead_id},
    )


@router.get("/leads/{lead_id}/contact-log/form", response_class=HTMLResponse)
async def contact_log_form(request: Request, lead_id: int, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    return templates.TemplateResponse(
        request=request,
        name="partials/contact_log_form.html",
        context={"current_user": user, "lead_id": lead_id},
    )


@router.get("/leads/{lead_id}/comments/form", response_class=HTMLResponse)
async def comment_form(request: Request, lead_id: int, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    return templates.TemplateResponse(
        request=request,
        name="partials/comment_form.html",
        context={"current_user": user, "lead_id": lead_id},
    )


@router.get("/leads/{lead_id}/deals/form", response_class=HTMLResponse)
async def deal_form(request: Request, lead_id: int, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    return templates.TemplateResponse(
        request=request,
        name="partials/deal_form.html",
        context={"current_user": user, "lead_id": lead_id},
    )


@router.get("/api/leads/{lead_id}/dadata/search")
async def dadata_search(
    request: Request,
    lead_id: int,
    q: str = "",
    session: AsyncSession = Depends(get_session),
):
    """Поиск контрагента в DaData по названию или ИНН."""
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    query = q.strip()
    if not query:
        return {"results": [], "error": "Пустой запрос"}

    # Если запрос — число из 10/12 цифр, ищем по ИНН напрямую
    digits = query.replace(" ", "").replace("-", "")
    if digits.isdigit() and len(digits) in (10, 12):
        result = await find_party_by_inn(digits)
        if result["result"]:
            return {"results": [result["result"]], "error": None}
        return {"results": [], "error": result["error"]}

    result = await suggest_party(query)
    return {"results": result["results"], "error": result["error"]}


@router.post("/api/leads/{lead_id}/dadata/apply")
async def dadata_apply(
    request: Request,
    lead_id: int,
    inn: str = Form(""),
    head_name: str = Form(""),
    site: str = Form(""),
    address: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    """Применяет реквизиты из DaData к лиду (обновляет поля)."""
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    if inn:
        lead.inn = inn
    if head_name:
        lead.head_name = head_name
    if site:
        lead.site = site
    # Адрес подставляем в address, если поле пустое — не перезаписываем
    if address and not lead.address:
        lead.address = address

    await session.commit()
    return {"ok": True}
