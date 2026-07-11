from datetime import datetime, time, timedelta

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_session
from app.models import Task, User

router = APIRouter()

# Статусы, считающиеся «активными» (не завершёнными).
# Та же формула, что в tasks.py/dashboard.py — не дублируем определение иначе.
ACTIVE_STATUSES = ("pending", "in_progress")


@router.get("/api/ticker", response_class=HTMLResponse)
async def ticker(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Бегущая строка задач внизу рабочего экрана.

    Менеджер: верхний ряд — задачи на сегодня (цвет по статусу) + задачи на
    завтра (чёрные); нижний ряд — просроченные (красные, крупнее).
    Руководитель: один ряд со всеми задачами всех менеджеров (цвет = статус,
    красная подсветка если просрочена, в подписи — имя исполнителя).
    """
    from app.main import templates

    user = await get_current_user(request, session)
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)

    if user.role.value == "manager":
        rows = await session.scalars(
            select(Task)
            .where(
                Task.assigned_to == user.id,
                Task.status.in_(ACTIVE_STATUSES),
            )
            .options(selectinload(Task.lead))
            .order_by(Task.due_date.is_(None), Task.due_date)
        )
        tasks = list(rows.all())

        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        tomorrow_start = datetime.combine(tomorrow, time.min)
        tomorrow_end = datetime.combine(tomorrow, time.max)

        today_tasks, tomorrow_tasks, overdue_tasks = [], [], []
        for t in tasks:
            t.is_overdue = bool(t.due_date and t.due_date < now)
            if t.is_overdue:
                overdue_tasks.append(t)
            elif t.due_date and tomorrow_start <= t.due_date <= tomorrow_end:
                tomorrow_tasks.append(t)
            else:
                # сегодня (включая без срока — они «висят» как план на сегодня)
                today_tasks.append(t)

        return templates.TemplateResponse(
            request=request,
            name="partials/ticker.html",
            context={
                "current_user": user,
                "is_manager": True,
                "today_tasks": today_tasks,
                "tomorrow_tasks": tomorrow_tasks,
                "overdue_tasks": overdue_tasks,
            },
        )

    # Руководитель / админ — все задачи всех менеджеров
    result = await session.execute(
        select(Task, User.full_name)
        .join(User, Task.assigned_to == User.id)
        .options(selectinload(Task.lead))
        .order_by(Task.due_date.is_(None), Task.due_date)
    )
    all_tasks = []
    for t, assignee_name in result.all():
        t.assignee_name = assignee_name
        t.is_overdue = bool(
            t.due_date and t.due_date < now and t.status in ACTIVE_STATUSES
        )
        all_tasks.append(t)

    return templates.TemplateResponse(
        request=request,
        name="partials/ticker.html",
        context={
            "current_user": user,
            "is_manager": False,
            "all_tasks": all_tasks,
        },
    )
