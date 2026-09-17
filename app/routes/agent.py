import asyncio
import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import async_session_maker, get_session
from app.models import AgentJob, AgentMessage
from app.services.hermes_service import send_to_hermes

logger = logging.getLogger(__name__)

router = APIRouter()

# Живые ссылки на фоновые прогоны: event loop держит задачу, только пока на неё
# есть внешняя ссылка, иначе GC может собрать её до завершения.
_background_runs: set[asyncio.Task] = set()

# Прогон, висящий дольше бюджета + запас, считается потерянным (процесс убит
# без шанса на recovery) — чат получает честную ошибку, задача закрывается.
_JOB_STALE_MARGIN_S = 900


async def _process_job(job_id: int) -> None:
    """Обработка задачи прогона (фаза 28): прогон → ответ в agent_messages.

    Задача персистентна (agent_jobs): переживает рестарт контейнера — при
    старте recover_stuck_agent_jobs() перезапускает pending/running. Сессии
    своя на каждый шаг: между ними — долгое ожидание агента. Если задачу
    отменили («Очистить историю»), ответ не пишется.
    """
    try:
        async with async_session_maker() as session:
            job = await session.get(AgentJob, job_id)
            if job is None or job.status not in ("pending", "running"):
                return  # отменена или уже обработана
            job.status = "running"
            job.updated_at = datetime.utcnow()
            await session.commit()
            params = {
                "user_id": job.user_id,
                "user_name": job.user_name,
                "role": job.role,
                "message": job.message,
                "context_lead_id": job.context_lead_id,
                "search_mode": job.search_mode or "crm",
            }

        result = await send_to_hermes(
            idempotency_key=f"crm-job-{job_id}",
            **params,
        )

        async with async_session_maker() as session:
            job = await session.get(AgentJob, job_id)
            if job is None or job.status == "cancelled":
                return
            msg = AgentMessage(
                user_id=params["user_id"],
                role="assistant",
                content=result["reply"],
                context_lead_id=params["context_lead_id"],
                actions=json.dumps(result["actions"], ensure_ascii=False)
                if result["actions"]
                else None,
            )
            session.add(msg)
            await session.flush()  # msg.id для связи
            job.status = "done" if result["error"] is None else "failed"
            job.agent_message_id = msg.id
            job.error = result["error"]
            job.updated_at = datetime.utcnow()
            await session.commit()
    except Exception:  # noqa: BLE001 — молча потерять прогон нельзя
        logger.exception("Agent job %s crashed", job_id)
        try:
            async with async_session_maker() as session:
                job = await session.get(AgentJob, job_id)
                if job is None or job.status in ("done", "failed", "cancelled"):
                    return
                msg = AgentMessage(
                    user_id=job.user_id,
                    role="assistant",
                    content="Произошла внутренняя ошибка при обработке запроса агентом.",
                    context_lead_id=job.context_lead_id,
                )
                session.add(msg)
                await session.flush()
                job.status = "failed"
                job.agent_message_id = msg.id
                job.error = "internal"
                job.updated_at = datetime.utcnow()
                await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Agent job %s: failed to record failure", job_id)


async def recover_stuck_agent_jobs() -> int:
    """Перезапуск незавершённых прогонов после рестарта процесса (фаза 28).

    Вызывается из lifespan при старте: задачи в статусах pending/running
    пережили предыдущий процесс и перезапускаются. Ответы допишутся в чат
    фоном; повторному запросу присвоен тот же Idempotency-Key — шлюз может
    вернуть результат ещё живого оригинала вместо второго полного прогона.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(AgentJob.id).where(AgentJob.status.in_(["pending", "running"]))
        )
        job_ids = list(result.scalars().all())
    for job_id in job_ids:
        task = asyncio.create_task(_process_job(job_id))
        _background_runs.add(task)
        task.add_done_callback(_background_runs.discard)
    if job_ids:
        logger.warning("Agent jobs recovered after restart: %s", job_ids)
    return len(job_ids)


@router.get("/agent", response_class=HTMLResponse)
async def agent_chat_page(
    request: Request,
    lead_id: int = None,
    msg: str = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        return RedirectResponse("/login", status_code=303)

    result = await session.execute(
        select(AgentMessage)
        .where(AgentMessage.user_id == user.id)
        .order_by(AgentMessage.created_at.desc())
        .limit(50)
    )
    messages = list(result.scalars().all())
    messages.reverse()

    # Незавершённые прогоны — серверная истина для поллинга: страница,
    # открытая заново после рестарта сервера, продолжает ждать ответ.
    jobs_result = await session.execute(
        select(func.count())
        .select_from(AgentJob)
        .where(AgentJob.user_id == user.id, AgentJob.status.in_(["pending", "running"]))
    )
    pending_jobs = jobs_result.scalar() or 0

    # Prefill из query-параметров (кнопка "Отправить в чат" из карточки лида)
    prefill_message = msg or ""
    prefill_lead_id = lead_id or ""

    return templates.TemplateResponse(
        request=request,
        name="agent_chat.html",
        context={
            "current_user": user,
            "messages": messages,
            "last_message_id": messages[-1].id if messages else 0,
            "pending_jobs": pending_jobs,
            "prefill_message": prefill_message,
            "prefill_lead_id": prefill_lead_id,
        },
    )


@router.post("/agent/send", response_class=HTMLResponse)
async def agent_send(
    request: Request,
    message: str = Form(...),
    context_lead_id: int = Form(None),
    search_mode: str = Form("crm"),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    # Защита от некорректных значений — только два режима.
    if search_mode not in ("crm", "internet"):
        search_mode = "crm"

    user_msg = AgentMessage(
        user_id=user.id,
        role="user",
        content=message,
        context_lead_id=context_lead_id,
    )
    job = AgentJob(
        user_id=user.id,
        user_name=user.full_name,
        role=user.role.value,
        message=message,
        context_lead_id=context_lead_id,
        search_mode=search_mode,
    )
    session.add(user_msg)
    session.add(job)
    # Коммитим ДО запуска фонового прогона: (а) INSERT не держит write-транзакцию
    # SQLite на время ожидания агента («database is locked»), (б) задача уже
    # видна recovery при падении процесса между ответом и стартом прогона.
    await session.commit()

    # Асинхронный прогон (фазы 27–28): ответ допишется в agent_messages фоном,
    # чат заберёт его поллингом /agent/updates. Примитивы (не ORM-объекты) —
    # сессия запроса закроется вместе с HTTP-ответом.
    task = asyncio.create_task(_process_job(job.id))
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)

    return templates.TemplateResponse(
        request=request,
        name="partials/agent_message.html",
        context={"msg": user_msg},
    )


@router.get("/agent/updates", response_class=HTMLResponse)
async def agent_updates(
    request: Request,
    after_id: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """Поллинг новых сообщений чата — «подписка» на ответы агента.

    Возвращает partial со всеми сообщениями пользователя с id > after_id.
    Если у пользователя есть незавершённые прогоны, ответ помечается маркером
    agent-jobs-marker (серверная истина для клиента: ждать или признать потерю).
    Здесь же самолечение: прогон, висящий дольше бюджета + запаса, закрывается
    с честной ошибкой в чате (процесс убит, recovery не успеет).
    """
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    if after_id < 0:
        after_id = 0

    stale_before = datetime.utcnow() - timedelta(
        seconds=settings.HERMES_TIMEOUT + _JOB_STALE_MARGIN_S
    )
    stale_result = await session.execute(
        select(AgentJob)
        .where(
            AgentJob.user_id == user.id,
            AgentJob.status.in_(["pending", "running"]),
            AgentJob.updated_at < stale_before,
        )
    )
    stale_jobs = list(stale_result.scalars().all())
    for job in stale_jobs:
        job.status = "failed"
        job.error = "lost"
        job.updated_at = datetime.utcnow()
        msg = AgentMessage(
            user_id=user.id,
            role="assistant",
            content=(
                "Запрос агента потерян: сервер перезапускался, а восстановить "
                "прогон не удалось. Отправьте запрос повторно."
            ),
            context_lead_id=job.context_lead_id,
        )
        session.add(msg)
        await session.flush()
        job.agent_message_id = msg.id
    if stale_jobs:
        await session.commit()

    result = await session.execute(
        select(AgentMessage)
        .where(AgentMessage.user_id == user.id, AgentMessage.id > after_id)
        .order_by(AgentMessage.id.asc())
        .limit(50)
    )
    messages = list(result.scalars().all())

    jobs_result = await session.execute(
        select(func.count())
        .select_from(AgentJob)
        .where(AgentJob.user_id == user.id, AgentJob.status.in_(["pending", "running"]))
    )
    pending_jobs = jobs_result.scalar() or 0

    return templates.TemplateResponse(
        request=request,
        name="partials/agent_messages.html",
        context={"messages": messages, "pending_jobs": pending_jobs},
    )


@router.post("/agent/clear")
async def agent_clear(request: Request, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    await session.execute(
        delete(AgentMessage).where(AgentMessage.user_id == user.id)
    )
    # Отменяем незавершённые прогоны: иначе «очистка» оставила бы фантомные
    # ответы, которые допишутся в пустой чат позже. Текущий прогон завершится,
    # но ответ не запишет (см. _process_job).
    jobs_result = await session.execute(
        select(AgentJob).where(
            AgentJob.user_id == user.id, AgentJob.status.in_(["pending", "running"])
        )
    )
    for job in jobs_result.scalars().all():
        job.status = "cancelled"
        job.updated_at = datetime.utcnow()
    await session.commit()
    return RedirectResponse("/agent", status_code=303)
