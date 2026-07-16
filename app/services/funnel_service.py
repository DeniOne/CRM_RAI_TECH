from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Lead, StageHistory, Contact

STAGES = ["0", "1", "2", "3", "4", "5", "6", "7", "postponed", "lost"]

STAGE_LABELS = {
    "0": "Серые лиды",
    "1": "В работе",
    "2": "Квалифицирован",
    "3": "КП отправлено",
    "4": "Переговоры",
    "5": "Договор + Счёт",
    "6": "Оплачено",
    "7": "Доставлено",
    "postponed": "Отложенный спрос",
    "lost": "Потерян",
}

STAGE_COLORS = {
    "0": "gray", "1": "blue", "2": "indigo", "3": "purple",
    "4": "orange", "5": "yellow", "6": "green", "7": "teal",
    "postponed": "amber",
    "lost": "red",
}


def validate_transition(lead: Lead, from_stage: str, to_stage: str) -> tuple[bool, list[str]]:
    if from_stage == to_stage:
        return True, []

    if to_stage in ("lost", "postponed"):
        return True, []

    if from_stage == "0" and to_stage == "1":
        if not lead.assigned_manager_id:
            return False, ["Назначьте менеджера"]
        return True, []

    if from_stage == "1" and to_stage == "2":
        errors = []
        has_dm = any(c.is_decision_maker for c in lead.contacts)
        if not has_dm:
            errors.append("Отметьте ЛПР среди контактов")
        if not lead.rapeseed_verified:
            errors.append("Подтвердите выращивание рапса")
        if errors:
            return False, errors
        return True, []

    return True, []


async def change_stage(session: AsyncSession, lead_id: int, to_stage: str, user_id: int) -> Lead:
    result = await session.execute(
        select(Lead).where(Lead.id == lead_id).options(selectinload(Lead.contacts))
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise ValueError("Лид не найден")

    from_stage = lead.stage
    ok, errors = validate_transition(lead, from_stage, to_stage)
    if not ok:
        raise ValueError(errors)

    history = StageHistory(
        lead_id=lead.id,
        from_stage=from_stage,
        to_stage=to_stage,
        changed_by=user_id,
        changed_at=datetime.now(),
    )
    session.add(history)

    lead.stage = to_stage
    lead.stage_changed_at = datetime.now()

    if to_stage == "lost" and not lead.loss_reason:
        lead.loss_reason = "Причина не указана"

    await session.flush()
    return lead
