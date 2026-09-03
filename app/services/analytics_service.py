"""Аналитика продаж (фаза 22): воронка КП, факт по оплаченным счетам,
ABC по выручке / количеству / прибыли (наценке), разрезы по категориям и
менеджерам. Данные — по позициям принятых/отправленных КП; факт — по
оплаченным счетам (Document.status='paid').
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Document, Lead, Quote

STATUSES = ("draft", "sent", "accepted", "rejected")


def _abc(rows: list[dict], measure: str) -> list[dict]:
    """Классика ABC: кумулятивная доля ≤80% — A, ≤95% — B, остальное C."""
    total = sum(r[measure] for r in rows)
    rows = sorted(rows, key=lambda r: r[measure], reverse=True)
    cum = 0.0
    for r in rows:
        share = (r[measure] / total * 100) if total else 0.0
        cum += share
        r["share"] = share
        r["cum"] = cum
        r["abc"] = "A" if cum <= 80 else ("B" if cum <= 95 else "C")
    return rows


def _aggregate(records, key_field, name_field):
    agg: dict = {}
    for r in records:
        k = r[key_field]
        if k not in agg:
            agg[k] = {"name": r[name_field], "qty": 0.0, "revenue": 0.0,
                      "profit": 0.0, "has_profit": False}
        a = agg[k]
        a["qty"] += r["qty"]
        a["revenue"] += r["revenue"]
        if r["profit"] is not None:
            a["profit"] += r["profit"]
            a["has_profit"] = True
    out = [{"id": k, **v} for k, v in agg.items()]
    return sorted(out, key=lambda x: x["revenue"], reverse=True)


async def sales_analytics(session: AsyncSession, date_from=None, date_to=None,
                          manager_id: int | None = None) -> dict:
    quotes = (
        await session.execute(
            select(Quote)
            .options(
                selectinload(Quote.items),
                selectinload(Quote.lead).selectinload(Lead.assigned_manager),
                selectinload(Quote.user),
            )
        )
    ).scalars().unique().all()

    paid_docs = (
        await session.execute(
            select(Document).where(Document.doc_type == "invoice", Document.status == "paid")
        )
    ).scalars().all()
    paid_quote_ids = {d.quote_id for d in paid_docs if d.quote_id}

    # --- воронка КП ---
    funnel = {s: {"count": 0, "sum": 0.0} for s in STATUSES}
    for q in quotes:
        if date_from and q.created_at.date() < date_from:
            continue
        if date_to and q.created_at.date() > date_to:
            continue
        if manager_id and q.user_id != manager_id:
            continue
        funnel[q.status]["count"] += 1
        funnel[q.status]["sum"] += float(q.total or 0)
    created_total = sum(v["count"] for v in funnel.values())
    conversion = round(funnel["accepted"]["count"] / created_total * 100, 1) if created_total else 0.0

    # --- факт: позиции по оплаченным счетам ---
    records: list[dict] = []
    paid_sum = 0.0
    for doc in paid_docs:
        if date_from and doc.paid_at and doc.paid_at.date() < date_from:
            continue
        if date_to and doc.paid_at and doc.paid_at.date() > date_to:
            continue
        if manager_id:
            lead = doc.lead
            if lead and lead.assigned_manager_id != manager_id:
                continue
        paid_sum += float(doc.amount or 0)
        if not doc.quote_id:
            continue
        quote = next((q for q in quotes if q.id == doc.quote_id), None)
        if not quote:
            continue
        manager = (quote.lead.assigned_manager.full_name
                   if quote.lead.assigned_manager else quote.user.full_name)
        for it in quote.items:
            rate = float(it.vat_rate) if it.vat_rate is not None else None
            revenue = float(it.amount or 0)
            revenue_net = revenue / (1 + rate / 100) if rate is not None else revenue
            cost = float(it.price_in) * float(it.qty) if it.price_in is not None else None
            profit = (revenue_net - cost) if cost is not None else None
            records.append({
                "product_id": it.product_id,
                "product": it.name,
                "category_id": None, "category": "—",
                "manager": manager,
                "qty": float(it.qty or 0),
                "revenue": revenue,
                "profit": profit,
                "paid_date": doc.paid_at.date() if doc.paid_at else None,
            })

    if records:
        product_ids = {r["product_id"] for r in records if r["product_id"]}
        if product_ids:
            from app.models import Product, ProductCategory
            prods = (
                await session.execute(
                    select(Product.id, Product.name, ProductCategory.name)
                    .join(ProductCategory, ProductCategory.id == Product.category_id, isouter=True)
                    .where(Product.id.in_(product_ids))
                )
            ).all()
            pmap = {pid: (pname, cname) for pid, pname, cname in prods}
            for r in records:
                if r["product_id"] in pmap:
                    pname, cname = pmap[r["product_id"]]
                    r["product"], r["category"], r["category_id"] = pname, cname or "—", r["product_id"]

    abc_revenue = _abc(_aggregate(records, "product_id", "product"), "revenue")
    abc_qty = _abc(_aggregate(records, "product_id", "product"), "qty")
    with_profit = [r for r in records if r["profit"] is not None]
    abc_profit = _abc(_aggregate(with_profit, "product_id", "product"), "profit") if with_profit else []
    categories = _abc(_aggregate(records, "category", "category"), "revenue")
    managers = _aggregate(records, "manager", "manager")

    return {
        "funnel": funnel,
        "created_total": created_total,
        "conversion": conversion,
        "paid_count": sum(1 for d in paid_docs),
        "paid_sum": paid_sum,
        "records": records,
        "abc_revenue": abc_revenue,
        "abc_qty": abc_qty,
        "abc_profit": abc_profit,
        "categories": categories,
        "managers": managers,
    }
