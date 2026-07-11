import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, require_role, hash_password
from app.config import settings
from app.database import get_session
from app.models import (
    User, UserRole, Invite, InvitePurpose,
    Lead, Task, Comment, ContactLog, Deal, Document, AgentMessage,
)

router = APIRouter()

INVITE_TTL_DAYS = 7
RESET_TTL_HOURS = 1

# Роли для отображения в UI
ROLE_LABELS = {
    "manager": "Менеджер",
    "supervisor": "Руководитель",
    "admin": "Админ",
}


def _build_invite_url(token: str) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/invite/{token}"


async def _count_user_dependencies(session: AsyncSession, user_id: int) -> dict:
    """Возвращает словарь {таблица: количество} зависимостей пользователя."""
    deps = {}

    r = await session.execute(select(func.count()).select_from(Lead).where(Lead.assigned_manager_id == user_id))
    if (cnt := r.scalar()) > 0:
        deps["Лиды (назначенные)"] = cnt

    r = await session.execute(select(func.count()).select_from(Task).where(
        (Task.assigned_to == user_id) | (Task.created_by == user_id)
    ))
    if (cnt := r.scalar()) > 0:
        deps["Задачи"] = cnt

    r = await session.execute(select(func.count()).select_from(Comment).where(Comment.user_id == user_id))
    if (cnt := r.scalar()) > 0:
        deps["Комментарии"] = cnt

    r = await session.execute(select(func.count()).select_from(ContactLog).where(ContactLog.user_id == user_id))
    if (cnt := r.scalar()) > 0:
        deps["Журнал контактов"] = cnt

    r = await session.execute(select(func.count()).select_from(Deal).where(Deal.user_id == user_id))
    if (cnt := r.scalar()) > 0:
        deps["Сделки"] = cnt

    r = await session.execute(select(func.count()).select_from(Document).where(Document.user_id == user_id))
    if (cnt := r.scalar()) > 0:
        deps["Документы"] = cnt

    r = await session.execute(select(func.count()).select_from(AgentMessage).where(AgentMessage.user_id == user_id))
    if (cnt := r.scalar()) > 0:
        deps["Сообщения агента"] = cnt

    return deps


# ─── Страница управления ────────────────────────────────────────────

@router.get("/admin/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await require_role("admin")(request, session)

    users_result = await session.execute(select(User).order_by(User.created_at))
    users = users_result.scalars().all()

    invites_result = await session.execute(
        select(Invite).order_by(Invite.created_at.desc()).limit(20)
    )
    invites = invites_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context={
            "current_user": user,
            "users": users,
            "invites": invites,
            "role_labels": ROLE_LABELS,
            "base_url": settings.APP_BASE_URL.rstrip("/"),
            "now": datetime.now(),
        },
    )


@router.get("/admin/users/invite/form", response_class=HTMLResponse)
async def invite_form(request: Request, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await require_role("admin")(request, session)
    return templates.TemplateResponse(
        request=request,
        name="partials/invite_form.html",
        context={"current_user": user},
    )


# ─── Приглашение нового пользователя ────────────────────────────────

@router.post("/admin/users/invite", response_class=HTMLResponse)
async def create_invite(
    request: Request,
    email: str = Form(...),
    role: str = Form("manager"),
    full_name: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await require_role("admin")(request, session)

    email = email.strip().lower()
    if role not in ("manager", "supervisor", "admin"):
        raise HTTPException(status_code=422, detail="Недопустимая роль")

    # Проверка: не приглашаем уже существующего email
    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")

    token = secrets.token_urlsafe(32)
    invite = Invite(
        token=token,
        email=email,
        role=UserRole(role),
        purpose=InvitePurpose.invite,
        created_by=user.id,
        expires_at=datetime.now() + timedelta(days=INVITE_TTL_DAYS),
    )
    session.add(invite)
    await session.commit()

    invite_url = _build_invite_url(token)

    return templates.TemplateResponse(
        request=request,
        name="partials/invite_link.html",
        context={
            "current_user": user,
            "invite": invite,
            "invite_url": invite_url,
            "full_name": full_name.strip(),
            "role_labels": ROLE_LABELS,
        },
    )


# ─── Деактивация / активация ────────────────────────────────────────

@router.post("/admin/users/{user_id}/toggle-active", response_class=HTMLResponse)
async def toggle_active(
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await require_role("admin")(request, session)

    if user_id == user.id:
        raise HTTPException(status_code=422, detail="Нельзя деактивировать самого себя")

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404)

    # Нельзя деактивировать последнего админа
    if target.role == UserRole.admin and target.is_active:
        active_admins = await session.execute(
            select(func.count()).select_from(User).where(User.role == UserRole.admin, User.is_active == True)
        )
        if active_admins.scalar() <= 1:
            raise HTTPException(status_code=422, detail="Нельзя деактивировать последнего администратора")

    target.is_active = not target.is_active
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/user_row.html",
        context={"current_user": user, "u": target, "role_labels": ROLE_LABELS},
    )


# ─── Смена роли ─────────────────────────────────────────────────────

@router.post("/admin/users/{user_id}/role", response_class=HTMLResponse)
async def change_role(
    request: Request,
    user_id: int,
    role: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await require_role("admin")(request, session)

    if role not in ("manager", "supervisor", "admin"):
        raise HTTPException(status_code=422, detail="Недопустимая роль")

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404)

    # Нельзя понизить последнего админа
    if target.role == UserRole.admin and role != "admin":
        active_admins = await session.execute(
            select(func.count()).select_from(User).where(User.role == UserRole.admin, User.is_active == True)
        )
        if active_admins.scalar() <= 1:
            raise HTTPException(status_code=422, detail="Нельзя понизить последнего администратора")

    target.role = UserRole(role)
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/user_row.html",
        context={"current_user": user, "u": target, "role_labels": ROLE_LABELS},
    )


# ─── Сброс пароля ───────────────────────────────────────────────────

@router.post("/admin/users/{user_id}/reset-password", response_class=HTMLResponse)
async def reset_password(
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await require_role("admin")(request, session)

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404)

    token = secrets.token_urlsafe(32)
    invite = Invite(
        token=token,
        email=target.email,
        role=target.role,
        purpose=InvitePurpose.reset,
        created_by=user.id,
        expires_at=datetime.now() + timedelta(hours=RESET_TTL_HOURS),
    )
    session.add(invite)
    await session.commit()

    invite_url = _build_invite_url(token)

    return templates.TemplateResponse(
        request=request,
        name="partials/invite_link.html",
        context={
            "current_user": user,
            "invite": invite,
            "invite_url": invite_url,
            "role_labels": ROLE_LABELS,
        },
    )


# ─── Удаление ───────────────────────────────────────────────────────

@router.post("/admin/users/{user_id}/delete")
async def delete_user(
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await require_role("admin")(request, session)

    if user_id == user.id:
        raise HTTPException(status_code=422, detail="Нельзя удалить самого себя")

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404)

    if target.role == UserRole.admin:
        active_admins = await session.execute(
            select(func.count()).select_from(User).where(User.role == UserRole.admin, User.is_active == True)
        )
        if active_admins.scalar() <= 1:
            raise HTTPException(status_code=422, detail="Нельзя удалить последнего администратора")

    deps = await _count_user_dependencies(session, user_id)
    if deps:
        dep_text = ", ".join(f"{k}: {v}" for k, v in deps.items())
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя удалить: у пользователя есть связанные данные ({dep_text}). Деактивируйте вместо удаления.",
        )

    await session.delete(target)
    await session.commit()
    return {"ok": True}
