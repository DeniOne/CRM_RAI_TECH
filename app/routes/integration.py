"""Integration API для RAI Market Intelligence. X-API-Key: env CRM_INTEGRATION_KEY."""
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Lead, StageHistory
from app.services.funnel_service import STAGES, STAGE_LABELS

router = APIRouter(prefix="/api/v1/integration", tags=["integration"])


def _check_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get("CRM_INTEGRATION_KEY", "")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid api key")


# ── Schemas ─────────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    source: str = "RAI_MI"
    opportunity_ref: str
    inn: Optional[str] = None
    name: str
    region: Optional[str] = None
    level: Optional[str] = None  # A/B/C
    priority: Optional[int] = None  # 1/2/3
    evidence_summary: Optional[str] = None
    sellability_grade: Optional[str] = None
    value_hypothesis_summary: Optional[str] = None
    next_action: Optional[str] = None


class LeadResponse(BaseModel):
    id: int
    name: str
    inn: Optional[str] = None
    stage: str
    opportunity_ref: Optional[str] = None
    source: Optional[str] = None
    dedup_result: Optional[str] = None  # attached | created_new_cycle | manual_review
    predecessor_lead_id: Optional[int] = None

    class Config:
        from_attributes = True


class OutcomeResponse(BaseModel):
    lead_id: int
    stage: str
    stage_label: str
    stage_changed_at: datetime
    loss_reason: Optional[str] = None
    history: list[dict]
    deals: list[dict]


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/catalog")
async def get_catalog(x_api_key: str = Header(default=""), session: AsyncSession = Depends(get_session)):
    """Каталог CRM для MI sync (V12). Восстановлен после перезаписи файла в V13."""
    _check_key(x_api_key)
    cats = (await session.execute(text("SELECT id, name, parent_id, sort_order FROM product_categories ORDER BY sort_order"))).mappings().all()
    prods = (await session.execute(text("SELECT id, category_id, name, sku, unit, description FROM products"))).mappings().all()
    return {
        "categories": [dict(c) for c in cats],
        "products": [dict(p) for p in prods],
        "source_revision": f"crm-{len(prods)}",
    }


@router.get("/leads/by-inn/{inn}")
async def get_lead_by_inn(
    inn: str,
    x_api_key: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
):
    """Дедупликация перед handoff: проверка ИНН в CRM."""
    _check_key(x_api_key)
    result = await session.execute(
        select(Lead).where(Lead.inn == inn).order_by(Lead.created_at.desc())
    )
    leads = result.scalars().all()
    if not leads:
        return {"found": False, "leads": []}
    return {
        "found": True,
        "leads": [
            {
                "id": l.id,
                "name": l.name,
                "inn": l.inn,
                "stage": l.stage,
                "stage_label": STAGE_LABELS.get(l.stage, l.stage),
                "opportunity_ref": l.opportunity_ref,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in leads
        ],
    }


@router.post("/leads", response_model=LeadResponse)
async def create_lead(
    body: LeadCreate,
    x_api_key: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
):
    """Handoff MI→CRM. Идемпотентно по opportunity_ref (повтор → существующий lead, 200)."""
    _check_key(x_api_key)

    # Idempotency: check existing by opportunity_ref
    if body.opportunity_ref:
        result = await session.execute(
            select(Lead).where(Lead.opportunity_ref == body.opportunity_ref)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return LeadResponse(
                id=existing.id,
                name=existing.name,
                inn=existing.inn,
                stage=existing.stage,
                opportunity_ref=existing.opportunity_ref,
                source=existing.source,
            )

    # Resolve region_id if region name provided
    region_id = None
    if body.region:
        region_result = await session.execute(
            text("SELECT id FROM regions WHERE name = :name"),
            {"name": body.region},
        )
        region_row = region_result.first()
        if region_row:
            region_id = region_row[0]

    # Дедуп по ИНН — статусная политика (Owner 07.09):
    #   0–5 или postponed → attach к незавершённому лиду (контекст обновляем, стадию не трогаем);
    #   несколько незавершённых → manual_review (решает человек);
    #   lost/6/7 → новый цикл: predecessor_lead_id + причина прошлого проигрыша.
    unfinished_stages = {"0", "1", "2", "3", "4", "5", "postponed"}
    finished_stages = {"6", "7", "lost"}
    leads_by_inn = []
    if body.inn:
        res_by_inn = await session.execute(
            select(Lead).where(Lead.inn == body.inn).order_by(Lead.created_at.desc())
        )
        leads_by_inn = list(res_by_inn.scalars().all())
    unfinished = [l for l in leads_by_inn if l.stage in unfinished_stages]

    if len(unfinished) > 1:
        return JSONResponse(status_code=200, content={
            "dedup_result": "manual_review",
            "opportunity_ref": body.opportunity_ref,
            "candidates": [
                {"id": l.id, "stage": l.stage, "name": l.name, "opportunity_ref": l.opportunity_ref}
                for l in unfinished[:5]
            ],
        })

    if unfinished:
        lead = unfinished[0]
        lead.evidence_summary = body.evidence_summary or lead.evidence_summary
        lead.sellability_grade = body.sellability_grade or lead.sellability_grade
        lead.value_hypothesis_summary = body.value_hypothesis_summary or lead.value_hypothesis_summary
        lead.recommended_action = body.next_action or lead.recommended_action
        if not lead.opportunity_ref:
            lead.opportunity_ref = body.opportunity_ref
        await session.commit()
        await session.refresh(lead)
        return LeadResponse(
            id=lead.id, name=lead.name, inn=lead.inn, stage=lead.stage,
            opportunity_ref=lead.opportunity_ref, source=lead.source,
            dedup_result="attached",
        )

    predecessor_lead = None
    if leads_by_inn and (body.source or "") == "RAI_MI":
        finished = [l for l in leads_by_inn if l.stage in finished_stages]
        if finished:
            predecessor_lead = max(finished, key=lambda x: x.created_at)

    # ADR-005 S7 (RETURNED Owner 07.09): лиды из MI стартуют «в разведке» —
    # стадия "0" (Серые лиды). Сразу «В работе» = premature pressure.
    initial_stage = "0" if (body.source or "") == "RAI_MI" else "1"
    lead = Lead(
        name=body.name,
        inn=body.inn,
        region_id=region_id,
        level=body.level,
        priority=body.priority,
        stage=initial_stage,
        stage_changed_at=datetime.now(timezone.utc),
        opportunity_ref=body.opportunity_ref,
        source=body.source,
        evidence_summary=body.evidence_summary,
        sellability_grade=body.sellability_grade,
        value_hypothesis_summary=body.value_hypothesis_summary,
        recommended_action=body.next_action,
        predecessor_lead_id=predecessor_lead.id if predecessor_lead else None,
    )
    if predecessor_lead is not None and predecessor_lead.stage == "lost":
        prev_reason = predecessor_lead.loss_reason or "не указана"
        prev_note = f"[Предыдущий цикл] lead {predecessor_lead.id} (lost): {prev_reason}"
        lead.evidence_summary = f"{lead.evidence_summary}; {prev_note}" if lead.evidence_summary else prev_note
    session.add(lead)
    await session.flush()

    # Record stage history
    history = StageHistory(
        lead_id=lead.id,
        from_stage=None,
        to_stage=initial_stage,
        note=f"MI handoff: {body.opportunity_ref}",
    )
    session.add(history)
    await session.commit()
    await session.refresh(lead)

    return LeadResponse(
        id=lead.id,
        dedup_result="created_new_cycle",
        predecessor_lead_id=predecessor_lead.id if predecessor_lead else None,
        name=lead.name,
        inn=lead.inn,
        stage=lead.stage,
        opportunity_ref=lead.opportunity_ref,
        source=lead.source,
    )


@router.get("/leads/{lead_id}/outcome")
async def get_lead_outcome(
    lead_id: int,
    x_api_key: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
):
    """Stage + StageHistory + loss_reason + deals/оплаты."""
    _check_key(x_api_key)

    result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")

    # Stage history
    hist_result = await session.execute(
        select(StageHistory)
        .where(StageHistory.lead_id == lead_id)
        .order_by(StageHistory.changed_at.asc())
    )
    history = [
        {
            "from_stage": h.from_stage,
            "to_stage": h.to_stage,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None,
            "note": h.note,
        }
        for h in hist_result.scalars().all()
    ]

    # Deals
    deals_result = await session.execute(
        text("SELECT id, title, amount, status, created_at, closed_at FROM deals WHERE lead_id = :lid"),
        {"lid": lead_id},
    )
    deals = [
        {
            "id": row[0],
            "title": row[1],
            "amount": row[2],
            "status": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
            "closed_at": row[5].isoformat() if row[5] else None,
        }
        for row in deals_result.fetchall()
    ]

    return {
        "lead_id": lead.id,
        "stage": lead.stage,
        "stage_label": STAGE_LABELS.get(lead.stage, lead.stage),
        "stage_changed_at": lead.stage_changed_at.isoformat() if lead.stage_changed_at else None,
        "loss_reason": lead.loss_reason,
        "history": history,
        "deals": deals,
    }


@router.get("/funnel/changes")
async def get_funnel_changes(
    since: str = Query(..., description="ISO datetime cursor"),
    x_api_key: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
):
    """Инкремент для pull-джобы MI (курсор `since`)."""
    _check_key(x_api_key)

    try:
        since_dt = datetime.fromisoformat(since)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid 'since' format, use ISO datetime")

    result = await session.execute(
        select(StageHistory)
        .where(StageHistory.changed_at > since_dt)
        .order_by(StageHistory.changed_at.asc())
        .limit(500)
    )
    changes = []
    for h in result.scalars().all():
        lead_result = await session.execute(select(Lead).where(Lead.id == h.lead_id))
        lead = lead_result.scalar_one_or_none()
        changes.append({
            "lead_id": h.lead_id,
            "from_stage": h.from_stage,
            "to_stage": h.to_stage,
            "stage_changed_at": h.changed_at.isoformat() if h.changed_at else None,
            "note": h.note,
            "loss_reason": lead.loss_reason if lead else None,
            "inn": lead.inn if lead else None,
            "opportunity_ref": lead.opportunity_ref if lead else None,
        })

    return {"changes": changes, "count": len(changes)}
