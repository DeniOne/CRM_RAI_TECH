import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import async_session_maker, get_session
from app.models import AgentMessage
from app.services.hermes_service import send_to_hermes

logger = logging.getLogger(__name__)

router = APIRouter()

# Живые ссылки на фоновые прогоны: event loop держит задачу, только пока на неё
# есть внешняя ссылка, иначе GC может собрать её до завершения.
_background_runs: set[asyncio.Task] = set()


async def _agent_run_and_store(
    user_id: int,
    user_name: str,
    role: str,
    message: str,
    context_lead_id: int | None,
) -> None:
    """Фоновый прогон агента (фаза 27).

    Ответ (или честная ошибка) дописывается в agent_messages, когда готов, —
    независимо от того, открыт ли браузер. Сессия своя: сессия запроса закрыта
    вместе с HTTP-ответом. send_to_hermes возвращает dict при любых сетевых
    исходах; внешний try страхует сам механизм доставки — молчаливо потерять
    ответ нельзя.
    """
    try:
        result = await send_to_hermes(
            message=message,
            user_id=user_id,
            user_name=user_name,
            role=role,
            context_lead_id=context_lead_id,
        )
    except Exception as e:  # noqa: BLE001 — см. докстринг
        logger.exception("Agent background run failed for user %s", user_id)
        result = {
            "reply": f"Произошла внутренняя ошибка при обращении к агенту: {e}",
            "actions": [],
            "error": "internal",
        }

    try:
        async with async_session_maker() as session:
            session.add(
                AgentMessage(
                    user_id=user_id,
                    role="assistant",
                    content=result["reply"],
                    context_lead_id=context_lead_id,
                    actions=json.dumps(result["actions"], ensure_ascii=False)
                    if result["actions"]
                    else None,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to store agent reply for user %s — ответ потерян", user_id
        )


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

    # Поллинг стартует, если последнее сообщение — от пользователя (запрос ещё
    # в работе или ответ потерян при перезапуске сервера). Возраст сообщения
    # нужен клиенту, чтобы не считать «висяком» свежий запрос.
    last_message_id = messages[-1].id if messages else 0
    pending_age = None
    if messages and messages[-1].role == "user":
        created = messages[-1].created_at
        if created is not None:
            pending_age = max(0, int((datetime.utcnow() - created).total_seconds()))

    # Prefill из query-параметров (кнопка "Отправить в чат" из карточки лида)
    prefill_message = msg or ""
    prefill_lead_id = lead_id or ""

    return templates.TemplateResponse(
        request=request,
        name="agent_chat.html",
        context={
            "current_user": user,
            "messages": messages,
            "last_message_id": last_message_id,
            "pending_age": pending_age,
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
    session.add(user_msg)
    # Коммитим сообщение пользователя ДО запуска фонового прогона. Иначе INSERT
    # (flush выше) открывает write-транзакцию SQLite, конкурирующую с записью
    # ответа из фоновой задачи и другими записями в CRM → «database is locked».
    await session.commit()

    # Асинхронный прогон (фаза 27): ответ допишется в agent_messages фоном,
    # чат заберёт его поллингом /agent/updates. Раньше HTTP-запрос блокировался
    # до конца прогона — долгие internet-поиски теряли ответ вместе с оборванным
    # соединением. Примитивы (не ORM-объекты) — сессия запроса закроется.
    task = asyncio.create_task(
        _agent_run_and_store(
            user_id=user.id,
            user_name=user.full_name,
            role=user.role.value,
            message=message,
            context_lead_id=context_lead_id,
        )
    )
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
    """Поллинг новых сообщений чата (фаза 27) — «подписка» на ответы агента.

    Возвращает partial со всеми сообщениями пользователя с id > after_id.
    """
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    if after_id < 0:
        after_id = 0

    result = await session.execute(
        select(AgentMessage)
        .where(AgentMessage.user_id == user.id, AgentMessage.id > after_id)
        .order_by(AgentMessage.id.asc())
        .limit(50)
    )
    messages = list(result.scalars().all())

    return templates.TemplateResponse(
        request=request,
        name="partials/agent_messages.html",
        context={"messages": messages},
    )


@router.post("/agent/clear")
async def agent_clear(request: Request, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    await session.execute(
        delete(AgentMessage).where(AgentMessage.user_id == user.id)
    )
    await session.commit()
    return RedirectResponse("/agent", status_code=303)
