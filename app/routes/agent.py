import json

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import AgentMessage
from app.services.hermes_service import send_to_hermes

router = APIRouter()


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

    # Prefill из query-параметров (кнопка "Отправить в чат" из карточки лида)
    prefill_message = msg or ""
    prefill_lead_id = lead_id or ""

    return templates.TemplateResponse(
        request=request,
        name="agent_chat.html",
        context={
            "current_user": user,
            "messages": messages,
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
    await session.flush()

    result = await send_to_hermes(
        message=message,
        user_id=user.id,
        user_name=user.full_name,
        role=user.role.value,
        context_lead_id=context_lead_id,
        search_mode=search_mode,
    )

    assistant_msg = AgentMessage(
        user_id=user.id,
        role="assistant",
        content=result["reply"],
        context_lead_id=context_lead_id,
        actions=json.dumps(result["actions"], ensure_ascii=False) if result["actions"] else None,
    )
    session.add(assistant_msg)
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/agent_message_pair.html",
        context={
            "current_user": user,
            "user_message": message,
            "agent_reply": result["reply"],
            "agent_actions": result["actions"],
            "created_at": assistant_msg.created_at,
        },
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
