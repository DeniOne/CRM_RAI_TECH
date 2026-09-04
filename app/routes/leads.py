import shutil
from datetime import datetime, date, timedelta
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, or_, delete, exists, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_session
from app.models import (Quote, Lead, Contact, ContactLog, Comment, Task, User, Region,
                       StageHistory, AgentMessage, Tag, LeadDirection, lead_tags,
                       COMPANY_TYPE_LABELS, PURCHASE_TYPE_LABELS, QUALIFICATION_LABELS,
                       DIRECTION_STATUS_LABELS)
from app.services import tags_service
from app.services.funnel_service import (
    STAGES, STAGE_LABELS, STAGE_COLORS, change_stage, validate_transition
)
from app.services.dadata_service import find_party_by_inn, suggest_party
from app.services.import_service import import_xlsx

router = APIRouter()


async def _regions_for_user(session: AsyncSession, user) -> list[Region]:
    """Регионы для дропдауна фильтра канбана и формы создания лида.

    Автоопределение: admin/supervisor видят все регионы; manager видит только
    те регионы, в которых у него есть лиды (lead.region_id). Ручная разметка
    не нужна — фильтр сам сужается до реальной работы менеджера.
    Если у менеджера нет лидов с регионом — fallback на все (чтобы фильтр не
    оказался пустым).
    """
    if user.role.value in ("admin", "supervisor"):
        result = await session.execute(select(Region).order_by(Region.name))
        return result.scalars().all()
    # manager: регионы, где есть хотя бы один его лид
    result = await session.execute(
        select(Region)
        .join(Lead, Lead.region_id == Region.id)
        .where(Lead.assigned_manager_id == user.id)
        .order_by(Region.name)
    )
    regions = result.scalars().unique().all()
    # fallback: нет лидов с регионом → показать все (не оставлять пустой фильтр)
    if not regions:
        all_result = await session.execute(select(Region).order_by(Region.name))
        return all_result.scalars().all()
    return regions


def build_kanban_query(region, level, priority, manager, assigned_manager, q=None, tag=None) -> str:
    """Готовит query-строку фильтров канбана для ссылок (вида '?region=3&level=A'
    или '', если фильтров нет). Единое место построения."""
    params = []
    if region:
        params.append(f"region={region}")
    if level:
        params.append(f"level={level}")
    if priority:
        params.append(f"priority={priority}")
    if manager:
        params.append(f"manager={manager}")
    if assigned_manager:
        params.append(f"assigned_manager={assigned_manager}")
    if q:
        params.append(f"q={q}")
    if tag:
        params.append(f"tag={tag}")
    return ("?" + "&".join(params)) if params else ""


@router.get("/kanban", response_class=HTMLResponse)
async def kanban(
    request: Request,
    manager: str = None,
    region: str = None,
    level: str = None,
    priority: str = None,
    assigned_manager: str = None,
    q: str = None,
    tag: str = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    # HTML-форма шлёт пустые строки для невыбранных <select>; приводим к None.
    region = int(region) if region and region.isdigit() else None
    priority = int(priority) if priority and priority.isdigit() else None
    # level: однобуквенный A/B/C или пусто
    level = level.strip() if level else None
    q = (q or "").strip() or None
    tag = (tag or "").strip().lstrip("#").strip() or None

    if manager is None:
        manager = "my" if user.role.value == "manager" else "all"

    kanban_query = build_kanban_query(region, level, priority, manager, assigned_manager, q, tag)

    if manager == "my" and user.role.value == "manager":
        base_filter = Lead.assigned_manager_id == user.id
    else:
        base_filter = True

    filters = [base_filter]
    if region:
        filters.append(Lead.region_id == region)
    # С автоопределением регионов доска менеджера не требует доп. фильтра:
    # base_filter уже отсекает чужие лиды, а все свои лиды и так лежат в его
    # регионах (по определению автоопределения).
    if level:
        filters.append(Lead.level == level)
    if priority:
        filters.append(Lead.priority == priority)
    # Фильтр по конкретному менеджеру. "unassigned" → лиды без менеджера.
    if assigned_manager:
        if assigned_manager == "unassigned":
            filters.append(Lead.assigned_manager_id.is_(None))
        elif assigned_manager.isdigit():
            filters.append(Lead.assigned_manager_id == int(assigned_manager))

    if q:
        like = f"%{q.lower()}%"
        # фаза 23: поиск также по досье, тегам и комментариям журнала
        # (u_lower — SQLite LIKE не фолдит кириллицу)
        tag_match = exists(
            select(1).where(
                lead_tags.c.lead_id == Lead.id,
                Tag.id == lead_tags.c.tag_id,
                func.u_lower(Tag.name).like(like),
            )
        )
        comment_match = exists(
            select(1).where(
                Comment.lead_id == Lead.id,
                func.u_lower(Comment.body).like(like),
            )
        )
        filters.append(
            or_(
                func.u_lower(Lead.name).like(like),
                Lead.inn.ilike(f"%{q}%"),
                func.u_lower(Lead.head_name).like(like),
                Lead.site.ilike(f"%{q}%"),
                func.u_lower(Lead.settlement).like(like),
                func.u_lower(Lead.general_comment).like(like),
                tag_match,
                comment_match,
            )
        )

    if tag:
        filters.append(
            exists(
                select(1).where(
                    lead_tags.c.lead_id == Lead.id,
                    Tag.id == lead_tags.c.tag_id,
                    func.u_lower(Tag.name) == tag.lower(),
                )
            )
        )

    result = await session.execute(
        select(Lead).where(*filters).options(selectinload(Lead.region), selectinload(Lead.assigned_manager)).order_by(Lead.name)
    )
    leads = result.scalars().all()

    leads_by_stage = {s: [] for s in STAGES}
    for lead in leads:
        if lead.stage in leads_by_stage:
            leads_by_stage[lead.stage].append(lead)

    regions = await _regions_for_user(session, user)
    # Флаг: фильтр регионов сужен до тех, где у менеджера есть лиды (для метки
    # «Все мои регионы» вместо «Все регионы»). admin/supervisor никогда не scoped.
    regions_scoped = user.role.value == "manager" and len(regions) > 0

    users_result = await session.execute(select(User).where(User.is_active == True).order_by(User.full_name))
    users = users_result.scalars().all()

    stages_data = []
    for code in STAGES:
        stages_data.append({
            "code": code,
            "label": STAGE_LABELS[code],
            "color": STAGE_COLORS[code],
            "leads": leads_by_stage[code],
            "count": len(leads_by_stage[code]),
        })

    # HTMX запрос — возвращаем только фрагмент доски
    if request.headers.get("hx-request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/kanban_board.html",
            context={"stages": stages_data, "kanban_query": kanban_query},
        )

    all_tags = await tags_service.all_tags(session)
    return templates.TemplateResponse(
        request=request,
        name="kanban.html",
        context={
            "current_user": user,
            "stages": stages_data,
            "regions": regions,
            "regions_scoped": regions_scoped,
            "users": users,
            "manager": manager,
            "level": level,
            "priority": priority,
            "region_id": region,
            "assigned_manager_id": assigned_manager,
            "q": q,
            "tag": tag,
            "all_tags": all_tags,
            "kanban_query": kanban_query,
        },
    )


# ===========================================================================
# Создание лида + Импорт xlsx
# ВАЖНО: эти роуты — ДО /leads/{lead_id}, иначе FastCI матчит "form" как int
# ===========================================================================

async def _get_or_create_region(session: AsyncSession, name: str) -> Region:
    """Найти регион по имени или создать новый."""
    result = await session.execute(select(Region).where(Region.name == name))
    region = result.scalar_one_or_none()
    if not region:
        region = Region(name=name)
        session.add(region)
        await session.flush()
    return region


@router.get("/leads/form", response_class=HTMLResponse)
async def lead_create_form(request: Request, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)

    regions = await _regions_for_user(session, user)

    users_result = await session.execute(select(User).where(User.is_active == True))
    users = users_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="partials/lead_form.html",
        context={"current_user": user, "regions": regions, "users": users},
    )


@router.post("/leads/create")
async def lead_create(
    request: Request,
    name: str = Form(...),
    region_id: str = Form(""),
    new_region: str = Form(""),
    inn: str = Form(""),
    head_name: str = Form(""),
    site: str = Form(""),
    level: str = Form(""),
    priority: int = Form(None),
    assigned_manager_id: int = Form(None),
    general_comment: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="Название обязательно")

    # Менеджер обязателен. Если не передан — для роли manager подставляем себя,
    # для supervisor/admin — отказ (должны выбрать в форме).
    if not assigned_manager_id:
        if user.role.value == "manager":
            assigned_manager_id = user.id
        else:
            raise HTTPException(status_code=422, detail="Выберите менеджера")

    # Регион: new_region имеет приоритет (форма select 'new' + инпут названия).
    # region_id приходит строкой т.к. select может дать значение "new" (немчисловое) —
    # фильтруем такие/пустые и парсим int явно, чтобы не уронить FastAPI 422.
    region = None
    if new_region.strip():
        region = await _get_or_create_region(session, new_region.strip())
    elif region_id and region_id.lstrip("-").isdigit():
        rid = int(region_id)
        result = await session.execute(select(Region).where(Region.id == rid))
        region = result.scalar_one_or_none()

    lead = Lead(
        name=clean_name,
        region_id=region.id if region else None,
        inn=inn.strip() or None,
        head_name=head_name.strip() or None,
        site=site.strip() or None,
        level=level if level in ("A", "B", "C") else None,
        priority=priority if priority in (1, 2, 3) else None,
        assigned_manager_id=assigned_manager_id,
        general_comment=general_comment.strip() or None,
        stage="0",
    )
    session.add(lead)
    await session.commit()

    return {"ok": True, "lead_id": lead.id}


@router.get("/leads/import/form", response_class=HTMLResponse)
async def lead_import_form(request: Request, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(status_code=403)

    users_result = await session.execute(select(User).where(User.is_active == True).order_by(User.full_name))
    users = users_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="partials/import_form.html",
        context={"current_user": user, "users": users},
    )


@router.post("/leads/import", response_class=HTMLResponse)
async def lead_import(
    request: Request,
    file: UploadFile = File(...),
    default_manager_id: int = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)
    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(status_code=403)

    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=422, detail="Нужен файл .xlsx")

    content = await file.read()
    buf = BytesIO(content)

    try:
        report = await import_xlsx(buf, session, default_manager_id=default_manager_id)
        await session.commit()
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="partials/import_result.html",
            context={"current_user": user, "error": str(e), "report": None, "filename": file.filename},
        )

    return templates.TemplateResponse(
        request=request,
        name="partials/import_result.html",
        context={"current_user": user, "report": report, "error": None, "filename": file.filename},
    )


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
async def lead_card(
    request: Request,
    lead_id: int,
    region: str = None,
    level: str = None,
    priority: str = None,
    manager: str = None,
    assigned_manager: str = None,
    q: str = None,
    tag: str = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    region_n = int(region) if region and str(region).isdigit() else None
    priority_n = int(priority) if priority and str(priority).isdigit() else None
    level_n = level.strip() if level else None
    kanban_query = build_kanban_query(region_n, level_n, priority_n, manager, assigned_manager, q, tag)

    result = await session.execute(
        select(Lead).where(Lead.id == lead_id).options(
            selectinload(Lead.contacts),
            selectinload(Lead.contact_logs).selectinload(ContactLog.user),
            selectinload(Lead.contact_logs).selectinload(ContactLog.comment),
            selectinload(Lead.contact_logs).selectinload(ContactLog.task),
            selectinload(Lead.comments).selectinload(Comment.user),
            selectinload(Lead.tasks),
            selectinload(Lead.region),
            selectinload(Lead.documents),
            selectinload(Lead.deals),
            selectinload(Lead.directions).selectinload(LeadDirection.manager),
            selectinload(Lead.parent_lead),
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    users_result = await session.execute(select(User).where(User.is_active == True))
    users = users_result.scalars().all()

    regions_result = await session.execute(select(Region).order_by(Region.name))
    regions = regions_result.scalars().all()

    quotes_result = await session.execute(
        select(Quote).where(Quote.lead_id == lead_id)
        .options(selectinload(Quote.items))
        .order_by(Quote.id.desc())
    )
    quotes = quotes_result.scalars().unique().all()

    entries = _build_journal_entries(lead)

    # фаза 23: теги-справочник, лиды для селекта головной компании, активность
    all_tags = await tags_service.all_tags(session)
    parent_candidates = (
        await session.execute(select(Lead.id, Lead.name).where(Lead.id != lead.id).order_by(Lead.name))
    ).all()
    open_tasks = sorted(
        [t for t in lead.tasks if t.status == "pending" and t.due_date],
        key=lambda t: t.due_date,
    )
    next_task = open_tasks[0] if open_tasks else None
    last_activity = entries[0] if entries else None

    return templates.TemplateResponse(
        request=request,
        name="lead_card.html",
        context={
            "current_user": user,
            "lead": lead,
            "stage_label": STAGE_LABELS.get(lead.stage, lead.stage),
            "stages": [{"code": s, "label": STAGE_LABELS[s]} for s in STAGES],
            "users": users,
            "regions": regions,
            "entries": entries,
            "quotes": quotes,
            "all_tags": all_tags,
            "parent_candidates": parent_candidates,
            "next_task": next_task,
            "last_activity": last_activity,
            "company_type_labels": COMPANY_TYPE_LABELS,
            "purchase_type_labels": PURCHASE_TYPE_LABELS,
            "qualification_labels": QUALIFICATION_LABELS,
            "direction_status_labels": DIRECTION_STATUS_LABELS,
            "kanban_query": kanban_query,
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


@router.post("/api/leads/{lead_id}/rename")
async def api_rename_lead(
    request: Request,
    lead_id: int,
    name: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    """Переименование контрагента прямо в шапке карточки."""
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="Название не может быть пустым")

    result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    lead.name = clean_name
    await session.commit()
    return {"ok": True, "name": lead.name}


@router.post("/leads/{lead_id}/edit", response_class=HTMLResponse)
async def lead_edit(
    request: Request,
    lead_id: int,
    session: AsyncSession = Depends(get_session),
    level: str = Form(""),
    priority: int = Form(None),
    inn: str = Form(""),
    head_name: str = Form(""),
    site: str = Form(""),
    general_comment: str = Form(""),
    company_type: str = Form(""),
    purchase_type: str = Form(""),
    qualification_status: str = Form("none"),
    parent_lead_id: str = Form(""),
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
            selectinload(Lead.directions).selectinload(LeadDirection.manager),
            selectinload(Lead.parent_lead),
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404)

    lead.level = level if level in ("A", "B", "C") else None
    lead.priority = priority
    lead.inn = inn or None
    lead.head_name = head_name or None
    lead.site = site or None
    lead.general_comment = general_comment or None
    lead.company_type = company_type if company_type in ("holding", "farm", "dealer", "processor") else None
    lead.purchase_type = purchase_type if purchase_type in ("centralized", "local", "mixed") else None
    lead.qualification_status = qualification_status if qualification_status in ("none", "in_progress", "confirmed", "rejected") else "none"
    lead.parent_lead_id = int(parent_lead_id) if parent_lead_id and parent_lead_id.isdigit() and int(parent_lead_id) != lead.id else None
    if lead.stage == "lost":
        lead.loss_reason = loss_reason or None

    # фаза 23: #хэштэги из досье автоматически становятся тегами лида
    for tag_name in tags_service.extract_hashtags(general_comment):
        await tags_service.add_tag_to_lead(session, lead, tag_name)

    await session.commit()
    from app.models import (COMPANY_TYPE_LABELS as _CT, PURCHASE_TYPE_LABELS as _PT,
                            QUALIFICATION_LABELS as _QL, DIRECTION_STATUS_LABELS as _DS)
    all_tags = await tags_service.all_tags(session)
    parent_candidates = (
        await session.execute(select(Lead.id, Lead.name).where(Lead.id != lead.id).order_by(Lead.name))
    ).all()
    open_tasks = sorted(
        [t for t in lead.tasks if t.status == "pending" and t.due_date],
        key=lambda t: t.due_date,
    )
    return templates.TemplateResponse(
        request=request,
        name="partials/lead_info_form.html",
        context={"current_user": user, "lead": lead,
                 "all_tags": all_tags, "parent_candidates": parent_candidates,
                 "next_task": open_tasks[0] if open_tasks else None,
                 "last_activity": None,
                 "company_type_labels": _CT, "purchase_type_labels": _PT,
                 "qualification_labels": _QL, "direction_status_labels": _DS},
    )


@router.post("/leads/{lead_id}/requisites", response_class=HTMLResponse)
async def lead_edit_requisites(
    request: Request,
    lead_id: int,
    session: AsyncSession = Depends(get_session),
    inn: str = Form(""),
    ogrn: str = Form(""),
    kpp: str = Form(""),
    okpo: str = Form(""),
    legal_address: str = Form(""),
    postal_address: str = Form(""),
    bank_name: str = Form(""),
    bank_bic: str = Form(""),
    bank_account: str = Form(""),
    bank_corr_account: str = Form(""),
):
    """Сохранение реквизитов контрагента со вкладки «Реквизиты»."""
    from app.main import templates
    user = await get_current_user(request, session)

    result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404)

    lead.inn = inn.strip() or None
    lead.ogrn = ogrn.strip() or None
    lead.kpp = kpp.strip() or None
    lead.okpo = okpo.strip() or None
    lead.legal_address = legal_address.strip() or None
    lead.postal_address = postal_address.strip() or None
    lead.bank_name = bank_name.strip() or None
    lead.bank_bic = bank_bic.strip() or None
    lead.bank_account = bank_account.strip() or None
    lead.bank_corr_account = bank_corr_account.strip() or None

    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/lead_requisites_form.html",
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


@router.get("/leads/{lead_id}/contacts/{contact_id}/edit", response_class=HTMLResponse)
async def contact_edit_form(
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

    return templates.TemplateResponse(
        request=request,
        name="partials/contact_edit_form.html",
        context={"current_user": user, "contact": contact, "lead_id": lead_id},
    )


@router.put("/leads/{lead_id}/contacts/{contact_id}", response_class=HTMLResponse)
async def update_contact(
    request: Request,
    lead_id: int,
    contact_id: int,
    name: str = Form(""),
    position: str = Form(""),
    phone: str = Form(...),
    email: str = Form(""),
    is_decision_maker: bool = Form(False),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    result = await session.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404)

    contact.name = name or None
    contact.position = position or None
    contact.phone = phone
    contact.email = email or None
    contact.is_decision_maker = is_decision_maker

    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/contact_row.html",
        context={"current_user": user, "contact": contact, "lead_id": lead_id},
    )


@router.delete("/leads/{lead_id}/contacts/{contact_id}", response_class=HTMLResponse)
async def delete_contact(
    request: Request,
    lead_id: int,
    contact_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)

    result = await session.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404)

    await session.delete(contact)
    await session.commit()

    return HTMLResponse(content="")


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
            assigned_to=lead.assigned_manager_id or user.id,
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
    await session.flush()

    # фаза 23: #хэштэги комментария автоматически становятся тегами лида
    lead = await session.get(Lead, lead_id)
    for tag_name in tags_service.extract_hashtags(body):
        await tags_service.add_tag_to_lead(session, lead, tag_name)
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/comment_row.html",
        context={"current_user": user, "comment": comment},
    )


async def _render_journal(request, session: AsyncSession, lead_id: int, user):
    """Перерисовывает единый Журнал (HTMX-ответ после добавления записи).

    Собирает ленту из contact_logs (с привязанными comment/task) + свободных
    comment/task. Для сортировки и eager-load использует повторный запрос лида.
    """
    from app.main import templates

    result = await session.execute(
        select(Lead).where(Lead.id == lead_id).options(
            selectinload(Lead.contact_logs).selectinload(ContactLog.user),
            selectinload(Lead.contact_logs).selectinload(ContactLog.comment),
            selectinload(Lead.contact_logs).selectinload(ContactLog.task),
            selectinload(Lead.comments).selectinload(Comment.user),
            selectinload(Lead.tasks),
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404)

    entries = _build_journal_entries(lead)

    return templates.TemplateResponse(
        request=request,
        name="partials/journal_list.html",
        context={
            "current_user": user,
            "lead": lead,
            "entries": entries,
        },
    )


def _build_journal_entries(lead: Lead) -> list[dict]:
    """Строит единый список записей Журнала из contact_logs + свободных comment/task.

    Главная ось — ContactLog (действие). К нему привязываются comment/task если есть.
    Свободные Comment/Task (без привязки к ContactLog) показываются как отдельные блоки.
    Сортировка: новые сверху (по дате действия/создания).
    """
    # Собираем id, уже привязанных к действиям, чтобы исключить их из «свободных»
    bound_comment_ids = {
        log.comment_id for log in lead.contact_logs if log.comment_id is not None
    }
    bound_task_ids = {
        log.task_id for log in lead.contact_logs if log.task_id is not None
    }

    entries = []

    # 1. Действия (ContactLog) — основная ось
    for log in lead.contact_logs:
        entries.append({
            "kind": "action",
            "sort_key": log.contact_date,
            "log": log,
        })

    # 2. Свободные комментарии (не привязанные к действию)
    for comment in lead.comments:
        if comment.id in bound_comment_ids:
            continue
        entries.append({
            "kind": "comment",
            "sort_key": comment.created_at,
            "comment": comment,
        })

    # 3. Свободные задачи (не привязанные к действию)
    for task in lead.tasks:
        if task.id in bound_task_ids:
            continue
        entries.append({
            "kind": "task",
            "sort_key": task.created_at,
            "task": task,
        })

    # Сортировка: новые сверху; None (без даты) — в конце
    entries.sort(key=lambda e: e["sort_key"] or datetime.min, reverse=True)
    return entries


@router.post("/leads/{lead_id}/journal-entry", response_class=HTMLResponse)
async def add_journal_entry(
    request: Request,
    lead_id: int,
    # Действие (обязательно)
    action_date: str = Form(""),  # дата действия (date); пусто = сейчас
    contact_type: str = Form("call"),
    result: str = Form(...),  # основной текст — «комментарий» что было
    # Задача (опционально)
    task_title: str = Form(""),
    task_due_date: str = Form(""),
    task_priority: int = Form(2),
    session: AsyncSession = Depends(get_session),
):
    """Единая форма Журнала: создаёт действие + опционально задачу.

    Действие (ContactLog) обязательно. result — основной текст действия.
    Если заполнен task_title — создаётся Task и привязывается к ContactLog.task_id.
    """
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    lead_result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead = lead_result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404)

    result_text = result.strip()
    if not result_text:
        raise HTTPException(status_code=422, detail="Комментарий обязателен")

    # Дедупликация двойного клика: если этот же пользователь за последние 10 сек
    # уже создал запись с идентичным текстом на этот лид — не дублируем,
    # возвращаем текущую ленту (как при успехе, но без INSERT).
    dup_threshold = datetime.now() - timedelta(seconds=10)
    dup_q = await session.execute(
        select(ContactLog).where(
            ContactLog.lead_id == lead_id,
            ContactLog.user_id == user.id,
            ContactLog.result == result_text,
            ContactLog.created_at >= dup_threshold,
        )
    )
    if dup_q.scalar_one_or_none() is not None:
        return await _render_journal(request, session, lead_id, user)

    # Дата действия: из формы (дата) + текущее время системы.
    # <input type=date> отдаёт только YYYY-MM-DD — если поставить через
    # strptime("%Y-%m-%d"), время обнулится в 00:00 и все записи одного
    # дня будут одинаково датированы (ломает сортировку и отображение).
    now = datetime.now()
    if action_date:
        try:
            d = datetime.strptime(action_date, "%Y-%m-%d")
            when = d.replace(hour=now.hour, minute=now.minute, second=now.second)
        except ValueError:
            when = now
    else:
        when = now

    # Задача (если указан заголовок)
    new_task = None
    task_name = task_title.strip()
    if task_name:
        due_dt = None
        if task_due_date:
            try:
                due_dt = datetime.strptime(task_due_date, "%Y-%m-%dT%H:%M")
            except ValueError:
                due_dt = None

        new_task = Task(
            lead_id=lead_id,
            assigned_to=lead.assigned_manager_id or user.id,
            created_by=user.id,
            title=task_name,
            due_date=due_dt,
            priority=task_priority if task_priority in (1, 2, 3) else 2,
            status="pending",
        )
        session.add(new_task)
        await session.flush()

    # Действие (ContactLog) — главная ось, привязываем задачу если есть
    log = ContactLog(
        lead_id=lead_id,
        user_id=user.id,
        contact_type=contact_type,
        contact_date=when,
        result=result_text,
        outcome=None,
        next_action_date=None,
        comment_id=None,
        task_id=new_task.id if new_task else None,
    )
    session.add(log)
    await session.commit()

    return await _render_journal(request, session, lead_id, user)


@router.post("/api/leads/{lead_id}/assign")
async def assign_manager(
    request: Request,
    lead_id: int,
    manager_id: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    """Назначение/смена менеджера лида. JSON-API для inline-редактирования шапки.

    manager_id="" или невалидный → снимает менеджера (assigned_manager_id=None).
    Возвращает актуальные данные для обновления шапки без перезагрузки.
    """
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(status_code=403)

    result = await session.execute(
        select(Lead).where(Lead.id == lead_id).options(selectinload(Lead.assigned_manager))
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    # Пустая строка из <select> «Не назначен» → None. Иначе парсим int.
    mid = None
    if manager_id and str(manager_id).strip().isdigit():
        mid = int(manager_id)
        # Проверяем существование пользователя
        u = await session.execute(select(User).where(User.id == mid))
        if u.scalar_one_or_none() is None:
            raise HTTPException(status_code=422, detail="Менеджер не найден")

    lead.assigned_manager_id = mid
    await session.commit()
    await session.refresh(lead, ["assigned_manager"])

    return {
        "ok": True,
        "manager_id": lead.assigned_manager_id,
        "manager_name": lead.assigned_manager.full_name if lead.assigned_manager else None,
    }


@router.post("/api/leads/{lead_id}/region")
async def set_lead_region(
    request: Request,
    lead_id: int,
    region_id: str = Form(""),
    new_region: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    """Смена региона лида. JSON-API для inline-редактирования шапки.

    Приоритет: region_id (существующий) > new_region (создать новый).
    region_id="" и new_region="" → снимает регион (region_id=None).
    """
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    result = await session.execute(
        select(Lead).where(Lead.id == lead_id).options(selectinload(Lead.region))
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    region = None
    if region_id and str(region_id).strip().isdigit():
        rid = int(region_id)
        r = await session.execute(select(Region).where(Region.id == rid))
        region = r.scalar_one_or_none()
        if not region:
            raise HTTPException(status_code=422, detail="Регион не найден")
    elif new_region.strip():
        region = await _get_or_create_region(session, new_region.strip())

    lead.region_id = region.id if region else None
    await session.commit()
    await session.refresh(lead, ["region"])

    return {
        "ok": True,
        "region_id": lead.region_id,
        "region_name": lead.region.name if lead.region else None,
        # Все регионы — чтобы обновить dropdown в шапке (на случай создания нового)
        "regions": [{"id": r.id, "name": r.name} for r in (await session.execute(select(Region).order_by(Region.name))).scalars().all()],
    }


@router.delete("/leads/{lead_id}")
async def delete_lead(
    request: Request,
    lead_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    if user.role.value not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    try:
        await session.execute(
            delete(StageHistory).where(StageHistory.lead_id == lead_id)
        )
        await session.execute(
            delete(AgentMessage).where(AgentMessage.context_lead_id == lead_id)
        )

        docs_dir = Path("storage/documents") / str(lead_id)
        if docs_dir.exists():
            shutil.rmtree(docs_dir, ignore_errors=True)

        await session.delete(lead)
        await session.commit()
    except Exception:
        await session.rollback()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "detail": "Ошибка удаления лида"},
        )

    return JSONResponse(status_code=200, content={"ok": True})


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


@router.get("/leads/{lead_id}/journal/form", response_class=HTMLResponse)
async def journal_form(request: Request, lead_id: int, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    return templates.TemplateResponse(
        request=request,
        name="partials/journal_form.html",
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


@router.get("/leads/{lead_id}/tasks/form", response_class=HTMLResponse)
async def task_form(request: Request, lead_id: int, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    return templates.TemplateResponse(
        request=request,
        name="partials/task_form.html",
        context={"current_user": user, "lead_id": lead_id},
    )


@router.post("/leads/{lead_id}/tasks", response_class=HTMLResponse)
async def create_task(
    request: Request,
    lead_id: int,
    title: str = Form(...),
    description: str = Form(""),
    due_date: str = Form(""),
    priority: int = Form(2),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    lead_result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead = lead_result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404)

    due_dt = None
    if due_date:
        try:
            due_dt = datetime.strptime(due_date, "%Y-%m-%dT%H:%M")
        except ValueError:
            pass

    task = Task(
        lead_id=lead_id,
        assigned_to=lead.assigned_manager_id or user.id,
        created_by=user.id,
        title=title,
        description=description or None,
        due_date=due_dt,
        priority=priority,
        status="pending",
    )
    session.add(task)
    await session.commit()

    # Рассчитать is_overdue для новой задачи
    now = datetime.now()
    task.is_overdue = task.due_date and task.due_date < now and task.status in ("pending", "in_progress")
    task.lead = lead

    return templates.TemplateResponse(
        request=request,
        name="partials/task_row.html",
        context={"current_user": user, "task": task},
    )


def _clean_dadata_query(raw: str) -> str:
    """
    Очищает название контрагента из сырого лида перед отправкой в DaData.
    Убирает кавычки, организационно-правовые формы (ООО, АО, ПАО...),
    лишние пробелы и пунктуацию — оставляет «чистое» название для поиска.
    """
    import re
    q = raw.strip()

    # Убираем organizational-legal forms (ООО, АО, ПАО, ИП, ЗАО, ОАО, НКО и т.д.)
    opf_pattern = r'\b(ООО|ОАО|ЗАО|ПАО|АО|ИП|НКО|ОП|ФГУП|ГУП|МУП|ФГБОУ|ГБОУ|НО|АНО)\b'
    q = re.sub(opf_pattern, '', q, flags=re.IGNORECASE)

    # Убираем все виды кавычек
    q = re.sub(r'["\'«»„"‟‟”’"]', '', q)

    # Убираем лишнюю пунктуацию в начале/конце (но сохраняем дефисы и пробелы внутри)
    q = q.strip(' \t\-—–,.;:()[]{}|/\\')

    # Схлопываем множественные пробелы
    q = re.sub(r'\s+', ' ', q).strip()

    return q


# ===========================================================================
# Теги и направления (фаза 23: многопрофильная карточка лида)
# ===========================================================================

async def _lead_for_edit(session: AsyncSession, lead_id: int) -> Lead:
    result = await session.execute(
        select(Lead).where(Lead.id == lead_id).options(
            selectinload(Lead.directions).selectinload(LeadDirection.manager),
            selectinload(Lead.tasks),
            selectinload(Lead.contact_logs),
            selectinload(Lead.comments),
            selectinload(Lead.region),
            selectinload(Lead.contacts),
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")
    return lead


@router.post("/leads/{lead_id}/tags/add", response_class=HTMLResponse)
async def lead_tag_add(
    request: Request,
    lead_id: int,
    name: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    lead = await _lead_for_edit(session, lead_id)
    tag = await tags_service.add_tag_to_lead(session, lead, name)
    if tag is None:
        await session.rollback()
        from app.main import templates
        return templates.TemplateResponse(
            request=request, name="partials/lead_tags_block.html",
            context={"lead": await _lead_for_edit(session, lead_id), "tag_error": "Тег: 2–64 символа (буквы, цифры, пробел, дефис)"},
        )
    await session.commit()
    from app.main import templates
    return templates.TemplateResponse(
        request=request, name="partials/lead_tags_block.html",
        context={"lead": lead, "tag_error": None},
    )


@router.post("/leads/{lead_id}/tags/{tag_id}/remove", response_class=HTMLResponse)
async def lead_tag_remove(
    request: Request,
    lead_id: int,
    tag_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    lead = await _lead_for_edit(session, lead_id)
    await tags_service.remove_tag_from_lead(session, lead, tag_id)
    await session.commit()
    from app.main import templates
    return templates.TemplateResponse(
        request=request, name="partials/lead_tags_block.html",
        context={"lead": lead, "tag_error": None},
    )


def _direction_from_form(form, lead: Lead) -> LeadDirection:
    status = form.get("status") if form.get("status") in DIRECTION_STATUS_LABELS else "interest"
    manager_raw = form.get("manager_id") or ""
    return LeadDirection(
        lead_id=lead.id,
        name=(form.get("name") or "").strip()[:128] or "Направление",
        status=status,
        potential=(form.get("potential") or "").strip()[:100] or None,
        season=(form.get("season") or "").strip()[:100] or None,
        manager_id=int(manager_raw) if manager_raw.isdigit() else None,
        note=(form.get("note") or "").strip() or None,
    )


@router.post("/leads/{lead_id}/directions/add", response_class=HTMLResponse)
async def lead_direction_add(
    request: Request,
    lead_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    lead = await _lead_for_edit(session, lead_id)
    form = await request.form()
    direction = _direction_from_form(form, lead)
    if not (form.get("name") or "").strip():
        direction.name = "Направление"
    # append в загруженную коллекцию (не session.add): объект остаётся в
    # lead.directions и попадает в ответ без ре-фетча (identity-map отдаёт сталь)
    lead.directions.append(direction)
    await session.flush()
    await session.commit()
    from app.main import templates
    return templates.TemplateResponse(
        request=request, name="partials/lead_directions_block.html",
        context={"lead": lead,
                 "users": (await session.execute(select(User).where(User.is_active == True).order_by(User.full_name))).scalars().all(),
                 "direction_status_labels": DIRECTION_STATUS_LABELS},
    )


@router.post("/leads/{lead_id}/directions/{direction_id}/update", response_class=HTMLResponse)
async def lead_direction_update(
    request: Request,
    lead_id: int,
    direction_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    lead = await _lead_for_edit(session, lead_id)
    direction = next((d for d in lead.directions if d.id == direction_id), None)
    if direction is None:
        raise HTTPException(status_code=404, detail="Направление не найдено")
    form = await request.form()
    status = form.get("status") if form.get("status") in DIRECTION_STATUS_LABELS else direction.status
    manager_raw = form.get("manager_id") or ""
    direction.name = (form.get("name") or direction.name).strip()[:128]
    direction.status = status
    direction.potential = (form.get("potential") or "").strip()[:100] or None
    direction.season = (form.get("season") or "").strip()[:100] or None
    direction.manager_id = int(manager_raw) if manager_raw.isdigit() else None
    direction.note = (form.get("note") or "").strip() or None
    await session.commit()
    from app.main import templates
    return templates.TemplateResponse(
        request=request, name="partials/lead_directions_block.html",
        context={"lead": lead,
                 "users": (await session.execute(select(User).where(User.is_active == True).order_by(User.full_name))).scalars().all(),
                 "direction_status_labels": DIRECTION_STATUS_LABELS},
    )


@router.post("/leads/{lead_id}/directions/{direction_id}/delete", response_class=HTMLResponse)
async def lead_direction_delete(
    request: Request,
    lead_id: int,
    direction_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    lead = await _lead_for_edit(session, lead_id)
    direction = next((d for d in lead.directions if d.id == direction_id), None)
    if direction:
        lead.directions.remove(direction)
        await session.delete(direction)
        await session.commit()
    from app.main import templates
    return templates.TemplateResponse(
        request=request, name="partials/lead_directions_block.html",
        context={"lead": lead,
                 "users": (await session.execute(select(User).where(User.is_active == True).order_by(User.full_name))).scalars().all(),
                 "direction_status_labels": DIRECTION_STATUS_LABELS},
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

    raw = q.strip()
    if not raw:
        return {"results": [], "error": "Пустой запрос"}

    # Если запрос — число из 10/12 цифр, ищем по ИНН напрямую
    digits = raw.replace(" ", "").replace("-", "")
    if digits.isdigit() and len(digits) in (10, 12):
        result = await find_party_by_inn(digits)
        if result["result"]:
            return {"results": [result["result"]], "error": None}
        return {"results": [], "error": result["error"]}

    # Очищаем запрос от кавычек, ОПФ, мусора
    query = _clean_dadata_query(raw)
    if not query:
        return {"results": [], "error": "После очистки запрос пуст"}

    # Основной поиск по очищенному названию
    result = await suggest_party(query)
    if result["results"]:
        return {"results": result["results"], "error": None, "query": query}

    # Fallback: если ничего не нашлось — пробуем по первому слову
    # (помогает для "Грейнус Агро" → найти по "Грейнус")
    parts = query.split()
    if len(parts) > 1 and len(parts[0]) >= 4:
        result_fw = await suggest_party(parts[0])
        if result_fw["results"]:
            return {"results": result_fw["results"], "error": None, "query": query}

    return {"results": [], "error": result["error"], "query": query}


@router.post("/api/leads/{lead_id}/dadata/apply")
async def dadata_apply(
    request: Request,
    lead_id: int,
    inn: str = Form(""),
    head_name: str = Form(""),
    site: str = Form(""),
    address: str = Form(""),
    ogrn: str = Form(""),
    kpp: str = Form(""),
    okpo: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    """Применяет реквизиты из DaData к лиду (обновляет поля на обеих вкладках).

    Заполняет: ИНН, руководитель, сайт (вкладка «Информация»);
    ОГРН, КПП, ОКПО, юридический адрес (вкладка «Реквизиты»).
    Существующие значения не перезаписываются — только пустые поля.
    """
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    # Вкладка «Информация»
    if inn:
        lead.inn = inn
    if head_name:
        lead.head_name = head_name
    if site:
        lead.site = site
    # Адрес (сырой) — в старое поле address, если пустое
    if address and not lead.address:
        lead.address = address

    # Вкладка «Реквизиты» — не перезаписываем уже заполненные поля
    if ogrn and not lead.ogrn:
        lead.ogrn = ogrn
    if kpp and not lead.kpp:
        lead.kpp = kpp
    if okpo and not lead.okpo:
        lead.okpo = okpo
    # Юридический адрес — отдельно, т.к. DaData отдаёт именно зарегистрированный (юридический)
    if address and not lead.legal_address:
        lead.legal_address = address

    await session.commit()
    return {"ok": True}
