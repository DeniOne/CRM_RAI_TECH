from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, Region, User, ContactLog, Document, Deal, StageHistory, UserRole
from app.services.funnel_service import STAGES, STAGE_LABELS, DEAL_STATUS_LABELS


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


async def get_funnel_totals(session: AsyncSession, region_id=None, manager_id=None, date_from=None, date_to=None) -> dict:
    """Воронка по стадиям. Период — по Lead.created_at."""
    query = select(Lead.stage, func.count(Lead.id))
    if region_id is not None:
        query = query.where(Lead.region_id == region_id)
    if manager_id is not None:
        query = query.where(Lead.assigned_manager_id == manager_id)
    if date_from is not None:
        query = query.where(Lead.created_at >= date_from)
    if date_to is not None:
        query = query.where(Lead.created_at <= date_to)
    query = query.group_by(Lead.stage)

    result = await session.execute(query)
    stage_counts = {row[0]: row[1] for row in result}

    # База конверсии — вход в воронку (стадия "0" Серые лиды).
    # Конверсия стадии = лиды на ней / лидов на входе × 100.
    # Это даёт монотонно убывающую воронку без бессмысленных >100%
    # (бывшая формула «деление на соседа» давала 625% при нелинейном переходе).
    entry_count = stage_counts.get("0", 0)

    stages = []
    for code in STAGES:
        count = stage_counts.get(code, 0)
        conversion = None
        if entry_count > 0:
            conversion = round(count / entry_count * 100, 1)
        stages.append({
            "code": code,
            "label": STAGE_LABELS[code],
            "count": count,
            "conversion_pct": conversion,
        })

    total = sum(stage_counts.values())
    return {"stages": stages, "total_leads": total}


async def get_manager_kpi(session: AsyncSession, date_from=None, date_to=None, manager_id=None, region_id=None) -> list[dict]:
    """
    KPI менеджеров. Все метрики считаются по ПОРТФЕЛЮ менеджера — лидам,
    закреплённым за ним (Lead.assigned_manager_id), а не по тому, кто физически
    создал запись ContactLog/Document/Deal. Иначе записи, заведённые под чужим
    логином (импорт/supervisor), не засчитывались бы ответственному менеджеру.

    Показываются только операционные менеджеры (role=manager). date-фильтр
    применяется едино ко всем метрикам (Lead.created_at / ContactLog.contact_date /
    Document.created_at).
    """
    users_query = select(User).where(User.role == UserRole.manager)
    if manager_id is not None:
        users_query = users_query.where(User.id == manager_id)
    users_result = await session.execute(users_query)
    users = users_result.scalars().all()

    kpi_list = []
    for user in users:
        # Лиды менеджера (портфель) — единый набор фильтров для всех метрик.
        leads_filters = [Lead.assigned_manager_id == user.id]
        if region_id is not None:
            leads_filters.append(Lead.region_id == region_id)
        if date_from is not None:
            leads_filters.append(Lead.created_at >= date_from)
        if date_to is not None:
            leads_filters.append(Lead.created_at <= date_to)

        # total_leads — размер портфеля менеджера в выбранном периоде/регионе.
        total_leads = await session.scalar(
            select(func.count(Lead.id)).where(*leads_filters)
        )

        # Звонки/КП/сделки — через join Lead, на лидов менеджера.
        calls_query = (
            select(func.count(ContactLog.id))
            .join(Lead, ContactLog.lead_id == Lead.id)
            .where(*leads_filters)
        )
        if date_from:
            calls_query = calls_query.where(ContactLog.contact_date >= date_from)
        if date_to:
            calls_query = calls_query.where(ContactLog.contact_date <= date_to)
        calls_count = await session.scalar(calls_query)

        kp_query = (
            select(func.count(Document.id))
            .join(Lead, Document.lead_id == Lead.id)
            .where(*leads_filters, Document.doc_type == "kp")
        )
        if date_from:
            kp_query = kp_query.where(Document.created_at >= date_from)
        if date_to:
            kp_query = kp_query.where(Document.created_at <= date_to)
        kp_sent = await session.scalar(kp_query)

        deals_query = (
            select(func.count(Deal.id))
            .join(Lead, Deal.lead_id == Lead.id)
            .where(*leads_filters)
        )
        deals_count = await session.scalar(deals_query)

        # Конверсия — доля портфеля, дошедшая до КП+ (стадии 3-7).
        converted_query = select(func.count(Lead.id)).where(
            *leads_filters, Lead.stage.in_(["3", "4", "5", "6", "7"])
        )
        converted = await session.scalar(converted_query)
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


async def get_lost_leads(session: AsyncSession, region_id=None, manager_id=None, date_from=None, date_to=None) -> list[dict]:
    """
    Группировка потерянных лидов по причине.
    Колонки: reason, count, examples (до 3 названий).
    Период — по Lead.created_at.
    """
    base_filters = [Lead.stage == "lost"]
    if region_id is not None:
        base_filters.append(Lead.region_id == region_id)
    if manager_id is not None:
        base_filters.append(Lead.assigned_manager_id == manager_id)
    if date_from is not None:
        base_filters.append(Lead.created_at >= date_from)
    if date_to is not None:
        base_filters.append(Lead.created_at <= date_to)

    # Агрегация по причинам
    count_query = select(Lead.loss_reason, func.count(Lead.id)).where(*base_filters).group_by(Lead.loss_reason)
    count_result = await session.execute(count_query)
    reason_counts = {}
    for row in count_result:
        reason = row[0] if row[0] else "Без причины"
        reason_counts[reason] = row[1]

    # Примеры названий (до 3 на причину)
    examples_query = select(Lead.loss_reason, Lead.name).where(*base_filters)
    examples_result = await session.execute(examples_query)
    reason_examples: dict[str, list[str]] = {}
    for row in examples_result:
        reason = row[0] if row[0] else "Без причины"
        if reason not in reason_examples:
            reason_examples[reason] = []
        if len(reason_examples[reason]) < 3:
            reason_examples[reason].append(row[1])

    result = []
    for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
        result.append({
            "reason": reason,
            "count": count,
            "examples": ", ".join(reason_examples.get(reason, [])),
        })
    return result


async def get_deals_pipeline(session: AsyncSession, region_id=None, manager_id=None, date_from=None, date_to=None) -> list[dict]:
    """
    Агрегат Deal по Deal.status.
    Колонки: status_code, status_label, count, total_amount.
    region_id/manager_id — через join Lead. Период — по Deal.created_at.
    """
    need_join = region_id is not None or manager_id is not None
    query = select(
        Deal.status, func.count(Deal.id), func.coalesce(func.sum(Deal.amount), 0)
    )
    if need_join:
        query = query.join(Lead, Deal.lead_id == Lead.id)
    if region_id is not None:
        query = query.where(Lead.region_id == region_id)
    if manager_id is not None:
        query = query.where(Lead.assigned_manager_id == manager_id)
    if date_from is not None:
        query = query.where(Deal.created_at >= date_from)
    if date_to is not None:
        query = query.where(Deal.created_at <= date_to)
    query = query.group_by(Deal.status)

    result = await session.execute(query)
    status_map = {row[0]: {"count": row[1], "total_amount": row[2]} for row in result}

    # Порядок — как в DEAL_STATUS_LABELS
    pipeline = []
    for code, label in DEAL_STATUS_LABELS.items():
        data = status_map.get(code, {"count": 0, "total_amount": 0})
        pipeline.append({
            "status_code": code,
            "status_label": label,
            "count": data["count"],
            "total_amount": data["total_amount"],
        })
    return pipeline
