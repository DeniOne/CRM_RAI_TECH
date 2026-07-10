from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_session
from app.models import Task

router = APIRouter()


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    status: str = "pending",
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

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
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    result = await session.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.lead))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404)

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

    return templates.TemplateResponse(
        request=request,
        name="partials/task_row.html",
        context={"current_user": user, "task": task},
    )
