from datetime import datetime, date
from io import BytesIO

from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File
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
from app.services.import_service import import_xlsx

router = APIRouter()


@router.get("/kanban", response_class=HTMLResponse)
async def kanban(
    request: Request,
    manager: str = None,
    region: int = None,
    level: str = None,
    priority: int = None,
    assigned_manager: int = None,
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
    if assigned_manager:
        filters.append(Lead.assigned_manager_id == assigned_manager)

    result = await session.execute(
        select(Lead).where(*filters).options(selectinload(Lead.region), selectinload(Lead.assigned_manager)).order_by(Lead.name)
    )
    leads = result.scalars().all()

    leads_by_stage = {s: [] for s in STAGES}
    for lead in leads:
        if lead.stage in leads_by_stage:
            leads_by_stage[lead.stage].append(lead)

    regions_result = await session.execute(select(Region).order_by(Region.name))
    regions = regions_result.scalars().all()

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
            context={"stages": stages_data},
        )

    return templates.TemplateResponse(
        request=request,
        name="kanban.html",
        context={
            "current_user": user,
            "stages": stages_data,
            "regions": regions,
            "users": users,
            "manager": manager,
            "level": level,
            "priority": priority,
            "region_id": region,
            "assigned_manager_id": assigned_manager,
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

    regions_result = await session.execute(select(Region).order_by(Region.name))
    regions = regions_result.scalars().all()

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
    region_id: int = Form(None),
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

    region = None
    if region_id:
        result = await session.execute(select(Region).where(Region.id == region_id))
        region = result.scalar_one_or_none()
    elif new_region.strip():
        region = await _get_or_create_region(session, new_region.strip())

    lead = Lead(
        name=clean_name,
        region_id=region.id if region else None,
        inn=inn.strip() or None,
        head_name=head_name.strip() or None,
        site=site.strip() or None,
        level=level if level in ("A", "B", "C") else None,
        priority=priority if priority in (1, 2, 3) else None,
        assigned_manager_id=assigned_manager_id or None,
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

    return templates.TemplateResponse(
        request=request,
        name="partials/import_form.html",
        context={"current_user": user},
    )


@router.post("/leads/import", response_class=HTMLResponse)
async def lead_import(
    request: Request,
    file: UploadFile = File(...),
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
        report = await import_xlsx(buf, session)
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
    notify_hermes: bool = Form(False),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    from app.services.hermes_service import send_to_hermes
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
        assigned_to=user.id,
        created_by=user.id,
        title=title,
        description=description or None,
        due_date=due_dt,
        priority=priority,
        status="pending",
    )
    session.add(task)
    await session.commit()

    # Уведомить Hermes о новой задаче
    if notify_hermes:
        hermes_msg = f"Создана задача: {title}"
        if due_dt:
            hermes_msg += f" (срок: {due_dt.strftime('%d.%m.%Y %H:%M')})"
        hermes_msg += f" для лида {lead.name}"
        await send_to_hermes(
            message=f"Напомни мне: {hermes_msg}",
            user_id=user.id,
            user_name=user.full_name,
            role=user.role.value,
            context_lead_id=lead_id,
        )

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
