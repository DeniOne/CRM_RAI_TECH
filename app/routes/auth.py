from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import authenticate_user, set_session, clear_session, hash_password
from app.database import get_session
from app.models import User, UserRole, Invite, InvitePurpose

router = APIRouter()


@router.get("/login")
async def login_page(request: Request):
    from app.main import templates
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await authenticate_user(session, email, password)
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Неверный email или пароль"})
    response = RedirectResponse("/", status_code=303)
    set_session(response, user.id)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    clear_session(response)
    return response


# ─── Регистрация / сброс пароля по приглашению ──────────────────────

ROLE_LABELS = {
    "manager": "Менеджер",
    "supervisor": "Руководитель",
    "admin": "Админ",
}


async def _validate_invite(session: AsyncSession, token: str) -> Invite:
    """Загружает приглашение по токену и проверяет валидность."""
    result = await session.execute(select(Invite).where(Invite.token == token))
    invite = result.scalar_one_or_none()
    if not invite:
        raise ValueError("Ссылка недействительна или не существует")
    if invite.used_at is not None:
        raise ValueError("Эта ссылка уже использована")
    if invite.expires_at and invite.expires_at < datetime.now():
        raise ValueError("Срок действия ссылки истёк")
    return invite


@router.get("/invite/{token}")
async def invite_accept_page(request: Request, token: str, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    try:
        invite = await _validate_invite(session, token)
    except ValueError as e:
        return templates.TemplateResponse(
            request=request,
            name="invite_accept.html",
            context={"error": str(e), "invite": None, "role_label": ""},
        )

    return templates.TemplateResponse(
        request=request,
        name="invite_accept.html",
        context={
            "error": None,
            "invite": invite,
            "role_label": ROLE_LABELS.get(invite.role.value, invite.role.value),
        },
    )


@router.post("/invite/{token}")
async def invite_accept_submit(
    request: Request,
    token: str,
    full_name: str = Form(""),
    password: str = Form(...),
    password_confirm: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates

    try:
        invite = await _validate_invite(session, token)
    except ValueError as e:
        return templates.TemplateResponse(
            request=request,
            name="invite_accept.html",
            context={"error": str(e), "invite": None, "role_label": ""},
        )

    if password != password_confirm:
        return templates.TemplateResponse(
            request=request,
            name="invite_accept.html",
            context={
                "error": "Пароли не совпадают",
                "invite": invite,
                "role_label": ROLE_LABELS.get(invite.role.value, invite.role.value),
            },
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            request=request,
            name="invite_accept.html",
            context={
                "error": "Пароль должен быть не короче 6 символов",
                "invite": invite,
                "role_label": ROLE_LABELS.get(invite.role.value, invite.role.value),
            },
        )

    if invite.purpose == InvitePurpose.invite:
        # Проверка: не зарегистрирован ли уже
        existing = await session.execute(select(User).where(User.email == invite.email))
        if existing.scalar_one_or_none():
            return templates.TemplateResponse(
                request=request,
                name="invite_accept.html",
                context={
                    "error": "Пользователь с таким email уже зарегистрирован",
                    "invite": invite,
                    "role_label": ROLE_LABELS.get(invite.role.value, invite.role.value),
                },
            )

        user = User(
            email=invite.email,
            password_hash=hash_password(password),
            full_name=full_name.strip() or invite.email.split("@")[0],
            role=invite.role,
            is_active=True,
        )
        session.add(user)

    else:  # reset
        result = await session.execute(select(User).where(User.email == invite.email))
        user = result.scalar_one_or_none()
        if not user:
            return templates.TemplateResponse(
                request=request,
                name="invite_accept.html",
                context={
                    "error": "Пользователь не найден",
                    "invite": invite,
                    "role_label": ROLE_LABELS.get(invite.role.value, invite.role.value),
                },
            )
        user.password_hash = hash_password(password)
        user.is_active = True

    invite.used_at = datetime.now()
    await session.flush()
    await session.commit()

    # Автоматический вход
    response = RedirectResponse("/", status_code=303)
    set_session(response, user.id)
    return response
