"""Теги лида (многопрофильность v2.0): свободные метки с автосозданием.

Плейсхолдеры старого мира — рапсовые поля — остались в БД (rapeseed_*),
интерфейс их переименовал; профиль направления (рапс/премиксы/оборудование)
живёт в тегах. #хэштэги в текстах автоматически превращаются в теги.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, Tag, lead_tags

HASHTAG_RE = re.compile(r"#([0-9A-Za-zА-Яа-яЁё_\-]{2,64})")
NAME_RE = re.compile(r"^[0-9A-Za-zА-Яа-яЁё_\- ]{2,64}$")


def normalize_name(raw: str) -> str | None:
    """Нормализация имени тега: трим, схлопывание пробелов; валидация."""
    name = re.sub(r"\s+", " ", (raw or "").strip().lstrip("#").strip())
    if not name:
        return None
    if not NAME_RE.match(name):
        return None
    return name


def extract_hashtags(*texts: str | None) -> list[str]:
    """Уникальные #хэштэги из текстов (в порядке появления, сохраняя регистр)."""
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in HASHTAG_RE.finditer(text):
            name = match.group(1)
            if name.lower() not in seen:
                seen.add(name.lower())
                found.append(name)
    return found


async def find_by_name(session: AsyncSession, name: str) -> Tag | None:
    """Тег по имени без учёта регистра (u_lower — кириллица)."""
    return (
        await session.execute(
            select(Tag).where(func.u_lower(Tag.name) == name.lower())
        )
    ).scalar_one_or_none()


async def get_or_create(session: AsyncSession, name: str) -> Tag | None:
    name = normalize_name(name)
    if not name:
        return None
    tag = await find_by_name(session, name)
    if tag is None:
        tag = Tag(name=name)
        session.add(tag)
        await session.flush()
    return tag


async def add_tag_to_lead(session: AsyncSession, lead: Lead, name: str) -> Tag | None:
    tag = await get_or_create(session, name)
    if tag is None:
        return None
    if tag not in lead.tags:
        lead.tags.append(tag)
        await session.flush()
    return tag


async def remove_tag_from_lead(session: AsyncSession, lead: Lead, tag_id: int) -> bool:
    tag = next((t for t in lead.tags if t.id == tag_id), None)
    if tag is None:
        return False
    lead.tags.remove(tag)
    await session.flush()
    return True


async def all_tags(session: AsyncSession) -> list[Tag]:
    return list(
        (await session.execute(select(Tag).order_by(Tag.name))).scalars().all()
    )
