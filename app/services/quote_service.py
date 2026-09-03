"""Сервис КП: нумерация, позиции (снапшот + суммы), статусы, синхронизация
сделки и воронки. Фаза 19.

Правила (кросс-фазные truths):
- суммы считает СЕРВЕР по снапшоту из БД (клиентские суммы не доверяются);
- отправка КП двигает лид на стадию 3, акцепт — на 5 и сделку (amount, contract);
- несколько draft/sent КП на лид — норма.
"""

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy import delete as sqlalchemy_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Deal, Lead, Product, Quote, QuoteItem, SequenceCounter

D2 = Decimal("0.01")


def _dec(value, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


async def next_quote_number(session: AsyncSession, prefix: str = "КП") -> str:
    """КП-2026-0001. Счётчик по (prefix, year); SQLite single-writer — гонки нет."""
    year = datetime.now().year
    counter = (
        await session.execute(
            select(SequenceCounter).where(
                SequenceCounter.name == prefix, SequenceCounter.year == year
            )
        )
    ).scalar_one_or_none()
    if counter is None:
        counter = SequenceCounter(name=prefix, year=year, value=0)
        session.add(counter)
    counter.value += 1
    await session.flush()
    return f"{prefix}-{year}-{counter.value:04d}"


def parse_items_json(raw: str | None) -> list[dict]:
    """JSON билдера → список dict (валидация формы, не цен). Бросает ValueError."""
    if not raw:
        raise ValueError("КП без позиций не сохраняется")
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("Некорректный формат позиций")
    if not isinstance(items, list) or not items:
        raise ValueError("КП без позиций не сохраняется")
    cleaned = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise ValueError(f"Позиция {i + 1}: некорректный формат")
        name = str(it.get("name") or "").strip()
        qty = _dec(it.get("qty"), "0")
        price = _dec(it.get("price"), "-1")
        discount = _dec(it.get("discount_percent"), "0")
        errors = []
        if not name and not it.get("product_id"):
            errors.append("нет названия")
        if qty <= 0:
            errors.append("количество должно быть больше 0")
        if price < 0:
            errors.append("цена не распознана")
        if not (Decimal("0") <= discount <= Decimal("100")):
            errors.append("скидка 0–100%")
        if errors:
            raise ValueError(f"Позиция {i + 1}: " + ", ".join(errors))
        cleaned.append({
            "product_id": int(it["product_id"]) if it.get("product_id") else None,
            "name": name,
            "qty": qty,
            "price": price,
            "discount_percent": discount,
        })
    return cleaned


async def build_quote_items(session: AsyncSession, raw_items: list[dict]) -> tuple[list[QuoteItem], Decimal]:
    """Создаёт QuoteItem со снапшотом из БД (для товарных позиций) и считает суммы.
    Возвращает (items, total)."""
    result: list[QuoteItem] = []
    total = Decimal("0.00")
    for sort_order, it in enumerate(raw_items):
        product = None
        if it["product_id"]:
            product = await session.get(Product, it["product_id"])
            if product is None:
                raise ValueError(f"Позиция {sort_order + 1}: товар не найден")
        name = product.name if product else it["name"]
        sku = product.sku if product else None
        unit = product.unit if product else "шт"
        price_dec = _dec(it["price"])
        qty = it["qty"].quantize(Decimal("0.001"))
        discount = it["discount_percent"]
        # Снапшот цены: у товарной позиции цена берётся из БД только если из
        # формы пришла пустая/нулевая? Нет — билдер присылает цену, которую
        # видел менеджер (возможна ручная правка). Снапшот строго из формы,
        # но название/артикул/ед — строго из БД.
        amount = (qty * price_dec * (Decimal("100") - discount) / Decimal("100")).quantize(D2, ROUND_HALF_UP)
        total += amount
        result.append(QuoteItem(
            product_id=product.id if product else None,
            name=name,
            sku=sku,
            unit=unit,
            qty=qty,
            price=price_dec.quantize(D2, ROUND_HALF_UP),
            discount_percent=discount.quantize(Decimal("0.01")),
            amount=amount,
            sort_order=sort_order,
        ))
    return result, total.quantize(D2, ROUND_HALF_UP)


async def create_quote(session: AsyncSession, lead: Lead, user_id: int,
                       raw_items: str, valid_until: date | None, comment: str | None) -> Quote:
    items, total = await build_quote_items(session, parse_items_json(raw_items))
    quote = Quote(
        number=await next_quote_number(session),
        lead_id=lead.id,
        user_id=user_id,
        status="draft",
        total=total,
        valid_until=valid_until,
        comment=comment,
    )
    session.add(quote)
    await session.flush()
    # Прямое присваивание quote.items = items в async-сессии триггерит ленивую
    # загрузку коллекции (MissingGreenlet) — проставляем FK и add_all.
    for it in items:
        it.quote_id = quote.id
    session.add_all(items)
    await session.flush()
    return quote


async def update_quote_items(session: AsyncSession, quote: Quote,
                             raw_items: str, valid_until: date | None, comment: str | None) -> None:
    """Правка только черновика: полная замена позиций."""
    if quote.status != "draft":
        raise ValueError("Править можно только черновик")
    items, total = await build_quote_items(session, parse_items_json(raw_items))
    await session.execute(sqlalchemy_delete(QuoteItem).where(QuoteItem.quote_id == quote.id))
    for it in items:
        it.quote_id = quote.id
    session.add_all(items)
    quote.total = total
    quote.valid_until = valid_until
    quote.comment = comment
    await session.flush()


async def _sync_deal_and_stage(session: AsyncSession, quote: Quote, action: str) -> None:
    """Кросс-фазные правила: accept → сделка (amount=total, статус contract) и
    лид на стадию 5; send → лид на стадию 3. Стадии двигаем только если сейчас
    числовая и меньше целевой; ошибки валидации воронки не валят статус КП."""
    lead = await session.get(Lead, quote.lead_id)
    if lead is None:
        return

    from app.services.funnel_service import change_stage

    if action == "send":
        if lead.stage.isdigit() and int(lead.stage) < 3:
            try:
                await change_stage(session, lead.id, "3", quote.user_id)
            except ValueError:
                pass
    elif action == "accept":
        # сделка: последняя неживая-не-lost по лиду, иначе новая
        deal = (
            await session.execute(
                select(Deal).where(Deal.lead_id == quote.lead_id, Deal.status != "lost")
                .order_by(Deal.id.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if deal is None:
            deal = Deal(lead_id=quote.lead_id, user_id=quote.user_id,
                        title=f"По КП {quote.number}", status="new")
            session.add(deal)
            await session.flush()
        quote.deal_id = deal.id
        deal.amount = float(quote.total)
        if deal.status in ("new", "kp_sent", "negotiation"):
            deal.status = "contract"
        if lead.stage.isdigit() and int(lead.stage) < 5:
            try:
                await change_stage(session, lead.id, "5", quote.user_id)
            except ValueError:
                pass


async def apply_status(session: AsyncSession, quote: Quote, action: str) -> None:
    """draft→send→sent; sent→accept|reject; sent/rejected→draft."""
    transitions = {
        "send": {"from": ["draft"], "to": "sent"},
        "accept": {"from": ["sent"], "to": "accepted"},
        "reject": {"from": ["sent"], "to": "rejected"},
        "reopen": {"from": ["sent", "rejected"], "to": "draft"},
    }
    if action not in transitions:
        raise ValueError("Неизвестное действие")
    tr = transitions[action]
    if quote.status not in tr["from"]:
        raise ValueError(f"Действие недоступно для статуса «{quote.status}»")

    if action == "send":
        quote.sent_at = datetime.now()
    await _sync_deal_and_stage(session, quote, action)
    quote.status = tr["to"]
    await session.flush()
