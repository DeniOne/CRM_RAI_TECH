from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, Region, User, ContactLog, Document, Deal, StageHistory
from app.services.funnel_service import STAGES, STAGE_LABELS


async def get_funnel_by_region(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(Region.name, Lead.stage, func.count(Lead.id))
        .join(Lead, Lead.region_id == Region.id)
        .group_by(Region.name, Lead.stage)
    )

    regions_data = {}
    for row in result:
        name, stage, count = row
        if name not in regions_data:
            regions_data[name] = {"region": name, "total": 0}
        regions_data[name][f"stage_{stage}"] = count
        regions_data[name]["total"] += count

    return sorted(regions_data.values(), key=lambda x: x["total"], reverse=True)


async def get_funnel_totals(session: AsyncSession) -> dict:
    result = await session.execute(
        select(Lead.stage, func.count(Lead.id)).group_by(Lead.stage)
    )
    stage_counts = {row[0]: row[1] for row in result}

    stages = []
    prev_count = None
    for code in STAGES:
        count = stage_counts.get(code, 0)
        conversion = None
        if prev_count is not None and prev_count > 0 and code not in ("lost", "postponed"):
            conversion = round(count / prev_count * 100, 1)
        stages.append({
            "code": code,
            "label": STAGE_LABELS[code],
            "count": count,
            "conversion_pct": conversion,
        })
        if code not in ("lost", "postponed"):
            prev_count = count

    total = sum(stage_counts.values())
    return {"stages": stages, "total_leads": total}


async def get_manager_kpi(session: AsyncSession, date_from=None, date_to=None) -> list[dict]:
    users_result = await session.execute(select(User))
    users = users_result.scalars().all()

    kpi_list = []
    for user in users:
        total_leads = await session.scalar(
            select(func.count(Lead.id)).where(Lead.assigned_manager_id == user.id)
        )

        calls_query = select(func.count(ContactLog.id)).where(ContactLog.user_id == user.id)
        if date_from:
            calls_query = calls_query.where(ContactLog.contact_date >= date_from)
        if date_to:
            calls_query = calls_query.where(ContactLog.contact_date <= date_to)
        calls_count = await session.scalar(calls_query)

        kp_query = select(func.count(Document.id)).where(
            Document.user_id == user.id, Document.doc_type == "kp"
        )
        if date_from:
            kp_query = kp_query.where(Document.created_at >= date_from)
        if date_to:
            kp_query = kp_query.where(Document.created_at <= date_to)
        kp_sent = await session.scalar(kp_query)

        deals_count = await session.scalar(
            select(func.count(Deal.id)).where(Deal.user_id == user.id)
        )

        converted = await session.scalar(
            select(func.count(Lead.id)).where(
                Lead.assigned_manager_id == user.id,
                Lead.stage.in_(["3", "4", "5", "6", "7"])
            )
        )
        conversion_rate = round(converted / total_leads * 100, 1) if total_leads else 0

        kpi_list.append({
            "full_name": user.full_name,
            "role": user.role.value,
            "total_leads": total_leads or 0,
            "calls_count": calls_count or 0,
            "kp_sent": kp_sent or 0,
            "deals_count": deals_count or 0,
            "conversion_rate": conversion_rate,
        })

    return kpi_list


async def get_funnel_bottlenecks(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(Lead.stage, func.count(Lead.id)).group_by(Lead.stage)
    )
    stage_counts = {row[0]: row[1] for row in result}

    bottlenecks = []
    linear_stages = ["0", "1", "2", "3", "4", "5", "6", "7"]
    for i in range(len(linear_stages) - 1):
        from_stage = linear_stages[i]
        to_stage = linear_stages[i + 1]
        from_count = stage_counts.get(from_stage, 0)
        to_count = stage_counts.get(to_stage, 0)
        conversion = round(to_count / from_count * 100, 1) if from_count > 0 else 0
        bottlenecks.append({
            "from_stage": from_stage,
            "from_label": STAGE_LABELS[from_stage],
            "to_stage": to_stage,
            "to_label": STAGE_LABELS[to_stage],
            "from_count": from_count,
            "to_count": to_count,
            "conversion_pct": conversion,
            "is_bottleneck": conversion < 50,
        })
    return bottlenecks


async def get_stage_history_stats(session: AsyncSession) -> list[dict]:
    count_result = await session.scalar(select(func.count(StageHistory.id)))
    if count_result < 2:
        return []

    result = await session.execute(
        select(StageHistory.from_stage, StageHistory.to_stage, func.count(StageHistory.id))
        .group_by(StageHistory.from_stage, StageHistory.to_stage)
    )
    return [{"from_stage": r[0], "to_stage": r[1], "count": r[2]} for r in result]
