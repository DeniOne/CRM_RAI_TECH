from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_session
from app.models import Task, Lead, User
from app.routes.ticker import ACTIVE_STATUSES
from app.services.funnel_service import STAGE_LABELS
from app.tz_utils import user_day_bounds

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────


def _user_scope_filters(user):
    """Возвращает пару (task_filter, lead_filter) по роли."""
    if user.role.value == "manager":
        return (Task.assigned_to == user.id, Lead.assigned_manager_id == user.id)
    return (True, True)


async def _task_counts(session, user):
    """4 count-запроса для sidebar-счётчиков."""
    task_filter, lead_filter = _user_scope_filters(user)
    day_start, day_end = user_day_bounds(user)

    base = Task.status.in_(ACTIVE_STATUSES)

    total = await session.scalar(
        select(func.count(Task.id)).where(base, task_filter)
    )
    today = await session.scalar(
        select(func.count(Task.id)).where(
            base,
            task_filter,
            Task.due_date.is_(None) | ((Task.due_date >= day_start) & (Task.due_date <= day_end)),
        )
    )
    overdue = await session.scalar(
        select(func.count(Task.id)).where(
            base,
            task_filter,
            Task.due_date.is_not(None),
            Task.due_date < day_start,
        )
    )

    has_tasks = exists(select(Task.id).where(Task.lead_id == Lead.id))
    leads_without = await session.scalar(
        select(func.count(Lead.id)).where(
            lead_filter,
            Lead.stage != "lost",
            ~has_tasks,
        )
    )

    return {
        "total": total or 0,
        "today": today or 0,
        "overdue": overdue or 0,
        "leads_without_tasks": leads_without or 0,
    }


async def _query_leads_with_tasks(session, user, filter):
    """Лиды с задачами, отфильтрованными по filter."""
    _, lead_filter = _user_scope_filters(user)
    day_start, day_end = user_day_bounds(user)

    if filter == "no_tasks":
        has_tasks = exists(select(Task.id).where(Task.lead_id == Lead.id))
        result = await session.execute(
            select(Lead)
            .where(lead_filter, Lead.stage != "lost", ~has_tasks)
            .options(selectinload(Lead.assigned_manager))
            .order_by(Lead.name)
        )
        return result.scalars().all()

    # Фильтр для задач
    task_base = Task.status.in_(ACTIVE_STATUSES)
    if filter == "today":
        task_base = task_base & (
            Task.due_date.is_(None)
            | ((Task.due_date >= day_start) & (Task.due_date <= day_end))
        )
    elif filter == "overdue":
        task_base = task_base & Task.due_date.is_not(None) & (Task.due_date < day_start)

    # Задачи с eager-load лидов
    tasks_q = (
        select(Task)
        .where(task_base, Task.lead_id.is_not(None))
        .options(selectinload(Task.lead).selectinload(Lead.assigned_manager))
        .order_by(Task.due_date.is_(None), Task.due_date)
    )
    if user.role.value == "manager":
        tasks_q = tasks_q.where(Task.assigned_to == user.id)

    result = await session.execute(tasks_q)
    tasks = result.scalars().all()

    # Группировка по лидам
    seen = {}
    for t in tasks:
        if t.lead_id not in seen:
            t.lead._tasks = []
            seen[t.lead_id] = t.lead
        seen[t.lead_id]._tasks.append(t)
        t.is_overdue = bool(t.due_date and t.due_date < day_start)

    return list(seen.values())


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    status: str = "pending",
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    filters = [Task.assigned_to == user.id]
    if status != "all":
        filters.append(Task.status == status)

    result = await session.execute(
        select(Task).where(*filters).options(selectinload(Task.lead)).order_by(Task.due_date)
    )
    tasks = result.scalars().all()

    now = datetime.now()
    for t in tasks:
        t.is_overdue = (
            t.due_date and t.due_date < now and t.status in ("pending", "in_progress")
        )

    return templates.TemplateResponse(
        request=request,
        name="tasks.html",
        context={"current_user": user, "tasks": tasks, "status": status},
    )


@router.post("/api/tasks/{task_id}/status", response_class=HTMLResponse)
async def update_task_status(
    request: Request,
    task_id: int,
    status: str = Form(...),
    source: str = Form("tasks"),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    result = await session.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.lead))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404)

    if status == "cancelled" and user.role.value == "manager":
        raise HTTPException(status_code=403, detail="Менеджер не может отменять задачи")

    task.status = status
    if status == "done":
        task.completed_at = datetime.now()
    else:
        task.completed_at = None

    await session.commit()

    now = datetime.now()
    task.is_overdue = (
        task.due_date and task.due_date < now and task.status in ("pending", "in_progress")
    )

    # source=journal → журнальная карточка (task_card.html),
    # иначе — строка страницы /tasks (task_row.html).
    partial = "partials/task_card.html" if source == "journal" else "partials/task_row.html"
    return templates.TemplateResponse(
        request=request,
        name=partial,
        context={"current_user": user, "task": task},
    )


@router.get("/api/tasks/{task_id}/edit", response_class=HTMLResponse)
async def task_edit_form(
    request: Request,
    task_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Форма редактирования задачи (открывается в drawer).

    Доступ: admin/supervisor — любые задачи; manager — только свои
    (assigned_to == user.id).
    """
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404)

    if user.role.value == "manager" and task.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Можно редактировать только свои задачи")

    return templates.TemplateResponse(
        request=request,
        name="partials/task_edit_form.html",
        context={"current_user": user, "task": task},
    )


@router.put("/api/tasks/{task_id}", response_class=HTMLResponse)
async def update_task(
    request: Request,
    task_id: int,
    title: str = Form(...),
    description: str = Form(""),
    due_date: str = Form(""),
    priority: int = Form(2),
    session: AsyncSession = Depends(get_session),
):
    """Обновление задачи. Возвращает обновлённую журнальную карточку (task_card.html).

    Доступ: admin/supervisor — любые; manager — только свои. Поля: title,
    description, due_date (datetime-local), priority (1/2/3). Статус тут не
    меняется — у него отдельный эндпоинт (update_task_status).
    """
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404)

    if user.role.value == "manager" and task.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Можно редактировать только свои задачи")

    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(status_code=422, detail="Название обязательно")
    if priority not in (1, 2, 3):
        priority = 2

    due_dt = None
    if due_date:
        try:
            due_dt = datetime.strptime(due_date, "%Y-%m-%dT%H:%M")
        except ValueError:
            pass  # некорректная дата — оставляем без срока

    task.title = clean_title
    task.description = description.strip() or None
    task.due_date = due_dt
    task.priority = priority
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/task_card.html",
        context={"current_user": user, "task": task},
    )


@router.delete("/api/tasks/{task_id}", response_class=HTMLResponse)
async def delete_task(
    request: Request,
    task_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    if user.role.value == "manager":
        raise HTTPException(status_code=403, detail="Менеджер не может удалять задачи")

    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404)

    await session.delete(task)
    await session.commit()

    return HTMLResponse(content="")


# ── sidebar counts + leads list ─────────────────────────────────────────────


@router.get("/api/tasks/sidebar", response_class=HTMLResponse)
async def sidebar_counts(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates

    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    counts = await _task_counts(session, user)
    return templates.TemplateResponse(
        request=request,
        name="partials/sidebar_tasks_menu.html",
        context={"current_user": user, "counts": counts},
    )


@router.get("/tasks/leads", response_class=HTMLResponse)
async def tasks_leads_page(
    request: Request,
    filter: str = "total",
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates

    if filter not in ("total", "today", "overdue", "no_tasks"):
        raise HTTPException(status_code=422, detail="Недопустимый filter")

    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    leads = await _query_leads_with_tasks(session, user, filter)

    titles = {
        "total": "Все задачи",
        "today": "Задачи на сегодня",
        "overdue": "Просроченные задачи",
        "no_tasks": "Лиды без задач",
    }

    return templates.TemplateResponse(
        request=request,
        name="tasks_leads.html",
        context={
            "current_user": user,
            "leads": leads,
            "filter": filter,
            "page_title": titles[filter],
            "stage_labels": STAGE_LABELS,
        },
    )
