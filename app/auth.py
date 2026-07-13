import hashlib
import hmac
import os

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, Response, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import User, UserRole

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

SESSION_COOKIE = "session"
SESSION_MAX_AGE = 86400


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return salt.hex() + ":" + key.hex()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        salt_hex, key_hex = hashed.split(":")
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, 100000)
        return hmac.compare_digest(key, new_key)
    except Exception:
        return False


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user and verify_password(password, user.password_hash):
        return user
    return None


async def create_default_admin(session: AsyncSession):
    result = await session.execute(select(User).limit(1))
    if result.scalar_one_or_none() is not None:
        return
    admin = User(
        email=settings.ADMIN_EMAIL,
        password_hash=hash_password(settings.ADMIN_PASSWORD),
        full_name="Администратор",
        role=UserRole.admin,
        is_active=True,
    )
    session.add(admin)
    await session.commit()


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def read_session_token(token: str) -> dict | None:
    try:
        return serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def set_session(response: Response, user_id: int):
    token = create_session_token(user_id)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=SESSION_MAX_AGE, samesite="lax")


def clear_session(response: Response):
    response.delete_cookie(SESSION_COOKIE)


async def get_current_user(request: Request, session: AsyncSession) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    data = read_session_token(token)
    if not data:
        return None
    result = await session.execute(
        select(User).options(selectinload(User.regions)).where(User.id == data["user_id"])
    )
    user = result.scalar_one_or_none()
    if user and user.is_active:
        return user
    return None


def require_role(*roles: str):
    async def dependency(request: Request, session: AsyncSession):
        user = await get_current_user(request, session)
        if not user:
            raise HTTPException(status_code=401)
        if user.role.value not in roles:
            raise HTTPException(status_code=403)
        return user
    return dependency
