"""Часовые пояса пользователей.

Конвенция проекта: ``Task.due_date`` хранится как naive datetime (без tzinfo),
исторически сравнивается с ``datetime.now()`` — то есть неявно в серверном
времени. Мы сохраняем эту конвенцию и здесь: границы суток тоже считаются
naive, но вычисляются в зоне пользователя. Семантически это корректно —
дедлайн ставится «в 17:00 у меня», в локальном времени исполнителя.

Без новых зависимостей: только stdlib ``zoneinfo``.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Tuple
from zoneinfo import ZoneInfo

# Дефолт для записей с timezone IS NULL (мигрировавшие пользователи).
DEFAULT_TZ = "Europe/Moscow"


def _zone(user) -> ZoneInfo:
    """ZoneInfo для пользователя (с дефолтом и защитой от мусора)."""
    name = getattr(user, "timezone", None) or DEFAULT_TZ
    try:
        return ZoneInfo(name)
    except Exception:
        # Неверное/неразборчивое имя — откатываемся к дефолту.
        return ZoneInfo(DEFAULT_TZ)


def user_now(user) -> datetime:
    """Текущее локальное время пользователя (naive).

    Возвращает naive datetime, чтобы его можно было напрямую сравнивать
    с ``Task.due_date`` без конфликтов tzinfo.
    """
    return datetime.now(_zone(user)).replace(tzinfo=None)


def user_day_bounds(user) -> Tuple[datetime, datetime]:
    """Границы текущих рабочих суток пользователя [00:00:00, 23:59:59.999999].

    Используется тикером для отсечения будущего: задача попадает в ленту,
    только если ``due_date IS NULL`` ИЛИ ``start <= due_date <= end``.
    Просроченными считаются те, у кого ``due_date < start``.
    """
    now = user_now(user)
    start = datetime.combine(now.date(), time.min)
    end = datetime.combine(now.date(), time.max)
    return start, end
