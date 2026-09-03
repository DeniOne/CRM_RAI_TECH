"""Настройки компании и тексты печатных форм (фаза 20).

Плейсхолдеры — кириллические токены {Менеджер}, {Клиент}... Рендер: экранируем
текст и значения, затем словарная замена. НЕ Jinja: пользовательский шаблон в
Jinja — это произвольный код на сервере.
"""

import html
import re
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CompanyProfile, Lead, PrintTemplate, Quote

PLACEHOLDER_RE = re.compile(r"\{[A-Za-zА-Яа-яЁё_]+\}")

# Токен → человекочитаемое описание (для шпаргалки на странице настроек)
PLACEHOLDER_DOCS = {
    "{Клиент}": "название клиента (из лида)",
    "{Менеджер}": "ФИО назначенного на лида менеджера (иначе — автор КП)",
    "{Автор}": "ФИО автора КП",
    "{Номер}": "номер КП",
    "{Дата}": "дата КП",
    "{Действует_до}": "дата окончания действия цен",
    "{Итого}": "сумма КП",
    "{Компания}": "название нашей компании",
}


async def get_profile(session: AsyncSession) -> CompanyProfile:
    profile = (await session.execute(select(CompanyProfile).limit(1))).scalar_one_or_none()
    if profile is None:
        profile = CompanyProfile()
        session.add(profile)
        await session.flush()
    return profile


async def get_template(session: AsyncSession, kind: str) -> PrintTemplate:
    tpl = (
        await session.execute(select(PrintTemplate).where(PrintTemplate.kind == kind))
    ).scalar_one_or_none()
    defaults = {
        "quote": PrintTemplate(
            kind="quote",
            intro="Просим рассмотреть коммерческое предложение на поставку:",
            conditions="Цены действительны до {Действует_до}.",
            signature="С уважением,\n{Менеджер}",
        ),
        "invoice": PrintTemplate(
            kind="invoice",
            intro="",
            conditions="Оплата в течение 5 банковских дней.",
            signature="",
        ),
    }
    if tpl is None:
        tpl = defaults.get(kind) or PrintTemplate(kind=kind)
        session.add(tpl)
        await session.flush()
    return tpl


def fmt_money(value: Decimal | float | None) -> str:
    d = Decimal(str(value or 0))
    s = f"{d:,.2f}".replace(",", " ").replace(".", ",")
    return s


def placeholder_values(profile: CompanyProfile, quote: Quote) -> dict[str, str]:
    """Значения плейсхолдеров для КП. Всё строкой, экранизация — в render_text."""
    manager = None
    if quote.lead.assigned_manager_id:
        manager = quote.lead.assigned_manager
    manager_name = (manager.full_name if manager else None) or quote.user.full_name
    return {
        "{Клиент}": quote.lead.name,
        "{Менеджер}": manager_name,
        "{Автор}": quote.user.full_name,
        "{Номер}": quote.number,
        "{Дата}": quote.created_at.strftime("%d.%m.%Y"),
        "{Действует_до}": quote.valid_until.strftime("%d.%m.%Y") if quote.valid_until else "",
        "{Итого}": fmt_money(quote.total),
        "{Компания}": profile.name,
    }


def render_text(template_text: str | None, values: dict[str, str]) -> str:
    """Словарная замена токенов на значения. Экранизацию делает Jinja
    (autoescape) при рендере шаблона — здесь текст сырой; двойное экранирование
    давало бы «&amp;amp;» на печати. Неизвестные токены остаются как есть."""
    if not template_text:
        return ""

    def _sub(match: re.Match) -> str:
        return values.get(match.group(0), match.group(0))

    return PLACEHOLDER_RE.sub(_sub, template_text)


def company_requisites_lines(profile: CompanyProfile) -> list[str]:
    """Строки реквизитов для подвала печатной формы."""
    lines = []
    if profile.name:
        lines.append(profile.name)
    part1 = ", ".join(
        x for x in (
            f"ИНН {profile.inn}" if profile.inn else "",
            f"КПП {profile.kpp}" if profile.kpp else "",
            f"ОГРН {profile.ogrn}" if profile.ogrn else "",
        ) if x
    )
    if part1:
        lines.append(part1)
    if profile.legal_address:
        lines.append(profile.legal_address)
    if profile.phone or profile.email or profile.site:
        lines.append(", ".join(x for x in (profile.phone, profile.email, profile.site) if x))
    bank = ", ".join(x for x in (
        profile.bank_name or "",
        f"р/с {profile.bank_account}" if profile.bank_account else "",
        f"к/с {profile.bank_corr_account}" if profile.bank_corr_account else "",
        f"БИК {profile.bank_bic}" if profile.bank_bic else "",
    ) if x)
    if bank:
        lines.append(bank)
    if profile.tax_note:
        lines.append(profile.tax_note)
    return lines
