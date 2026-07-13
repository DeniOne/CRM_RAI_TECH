from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_session
from app.models import Task, User
from app.tz_utils import user_day_bounds

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

    Показывает только актуальные задачи текущих рабочих суток исполнителя
    (по его часовому поясу) + просроченные. Будущее отсекается.

    Менеджер: верхний ряд — задачи на сегодня (цвет по статусу); нижний ряд —
    просроченные (красные, крупнее). Задачи без срока считаются планом на
    сегодня и висят в верхнем ряду.
    Руководитель: один ряд — просроченные + сегодняшние задачи всех
    менеджеров (цвет = статус, красная подсветка если просрочена,
    в подписи — имя исполнителя).
    """
    from app.main import templates

    user = await get_current_user(request, session)

    if user.role.value == "manager":
        day_start, day_end = user_day_bounds(user)

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

        today_tasks, overdue_tasks = [], []
        for t in tasks:
            # Просрочена — дедлайн был до начала текущих суток исполнителя.
            t.is_overdue = bool(t.due_date and t.due_date < day_start)
            if t.is_overdue:
                overdue_tasks.append(t)
            elif t.due_date is None or day_start <= t.due_date <= day_end:
                # сегодня (включая без срока — они «висят» как план на сегодня).
                # Будущее (due_date > day_end) намеренно отсечено.
                today_tasks.append(t)

        return templates.TemplateResponse(
            request=request,
            name="partials/ticker.html",
            context={
                "current_user": user,
                "is_manager": True,
                "today_tasks": today_tasks,
                "overdue_tasks": overdue_tasks,
            },
        )

    # Руководитель / админ — просроченные + сегодняшние задачи всех менеджеров.
    # У каждого исполнителя своя TZ → своё «сегодня»; граница считается
    # индивидуально по assignee.timezone.
    result = await session.execute(
        select(Task, User.full_name, User.timezone)
        .join(User, Task.assigned_to == User.id)
        .where(Task.status.in_(ACTIVE_STATUSES))
        .options(selectinload(Task.lead))
        .order_by(Task.due_date.is_(None), Task.due_date)
    )
    all_tasks = []
    for t, assignee_name, assignee_tz in result.all():
        # Границы суток по TZ исполнителя задачи.
        assignee = _TzProxy(assignee_tz)
        day_start, day_end = user_day_bounds(assignee)
        t.assignee_name = assignee_name
        # В один ряд попадают просроченные + сегодняшние. Будущее отсечено.
        is_overdue = bool(t.due_date and t.due_date < day_start)
        is_today = t.due_date is None or day_start <= t.due_date <= day_end
        if not (is_overdue or is_today):
            continue
        t.is_overdue = is_overdue
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


class _TzProxy:
    """Минимальный заместитель User для user_day_bounds(): нужно только
    поле ``timezone``. Позволяет не загружать весь объект User ради одного
    поля при проходе по задачам руководителя."""

    __slots__ = ("timezone",)

    def __init__(self, timezone):
        self.timezone = timezone
