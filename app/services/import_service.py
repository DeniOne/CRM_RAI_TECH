import re
from datetime import datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Region, Lead, Contact, ContactLog
from app.services.phone_parser import parse_phones

COLUMN_MAP = {
    "name": ["Название компании", "Название"],
    "district": ["Район", "Район/Округ"],
    "settlement": ["Нас. пункт"],
    "address": ["Адрес"],
    "inn": ["ИНН"],
    "head_name": ["Руководитель"],
    "phones_raw": ["Телефоны", "Телефон"],
    "email": ["Email"],
    "site": ["Сайт / Холдинг", "Сайт/Холдинг", "Сайт", "Профиль"],
    "rapeseed_info": ["Рапс / основание", "Рапс - основание", "Рапс/основание"],
    "level": ["Уровень"],
    "priority": ["Приоритет", "Приоритет обзвона"],
    "general_comment": ["Комментарий для CRM", "Комментарий для CR"],
    "done_summary": ["Что сделано"],
    "todo_summary": ["Что нужно сделать"],
}

OUTCOME_KEYWORDS = {
    "sent_kp": ["кп", "коммерческ", "предложен"],
    "busy": ["сброс", "занят"],
    "no_answer": ["не дозвон", "нет ответ", "недоступ", "не отвеч"],
    "agreed": ["соглас", "договорил", "возьм", "заказ"],
    "refused": ["отказ", "не нужн", "не интерес", "ликвидир"],
    "callback": ["перезв", "перезван", "набрать", "звонить"],
}


def map_columns(df_columns: list) -> dict:
    mapped = {}
    for field, variants in COLUMN_MAP.items():
        for variant in variants:
            for col in df_columns:
                if isinstance(col, str) and col.strip() == variant:
                    mapped[field] = col
                    break
            if field in mapped:
                break
    return mapped


def normalize_region_name(sheet_name: str) -> str:
    name = re.sub(r"\s+\d+!*$", "", sheet_name).strip()
    name = re.sub(r"\s+\d+$", "", name).strip()
    return name


def normalize_priority(raw) -> int | None:
    if not raw or pd.isna(raw):
        return None
    s = str(raw).strip().lower()
    if any(x in s for x in ["1 очередь", "1-я очередь", "1-очередь"]):
        return 1
    if any(x in s for x in ["2 очередь", "2-я очередь", "2-очередь"]):
        return 2
    if any(x in s for x in ["3 очередь", "3-я очередь", "3-очередь"]):
        return 3
    if re.search(r"^1\b", s) or "высок" in s or "первая" in s:
        return 1
    if re.search(r"^2\b", s) or "средн" in s or "вторая" in s:
        return 2
    if re.search(r"^3\b", s) or "низк" in s or "трет" in s:
        return 3
    return None


def classify_outcome(text: str) -> str | None:
    if not text or pd.isna(text):
        return None
    s = str(text).strip().lower()
    for outcome, keywords in OUTCOME_KEYWORDS.items():
        for kw in keywords:
            if kw in s:
                return outcome
    return None


def determine_stage(contact_logs: list) -> str:
    if not contact_logs:
        return "0"
    outcomes = [log["outcome"] for log in contact_logs]
    results_text = " ".join(log["result"] for log in contact_logs).lower()
    if "sent_kp" in outcomes or "кп" in results_text:
        return "3"
    if "agreed" in outcomes or "соглас" in results_text:
        return "4"
    if any(o in outcomes for o in ["busy", "no_answer", "callback"]):
        return "1"
    return "1"


async def get_or_create_region(session: AsyncSession, name: str, cache: dict) -> Region:
    if name in cache:
        return cache[name]
    result = await session.execute(select(Region).where(Region.name == name))
    region = result.scalar_one_or_none()
    if not region:
        region = Region(name=name)
        session.add(region)
        await session.flush()
    cache[name] = region
    return region


async def import_xlsx(path_or_buf, session: AsyncSession) -> dict:
    """Импорт лидов из xlsx. path_or_buf — путь к файлу или BytesIO."""
    xls = pd.ExcelFile(path_or_buf)
    region_cache: dict[str, Region] = {}
    stats = {"regions": 0, "leads": 0, "contacts": 0, "contact_logs": 0}

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        if df.empty:
            continue

        region_name = normalize_region_name(sheet_name)
        is_blacklist = region_name.lower() == "не звонить"
        region = await get_or_create_region(session, region_name, region_cache)
        stats["regions"] = len(region_cache)

        col_map = map_columns(list(df.columns))

        date_columns = [c for c in df.columns if isinstance(c, datetime)]

        for _, row in df.iterrows():
            name_val = str(row.get(col_map.get("name", ""), "")).strip()
            if not name_val or name_val.lower() == "nan":
                continue

            level_raw = _str_or_none(row.get(col_map.get("level", "")))
            level_val = level_raw if level_raw in ("A", "B", "C") else None

            lead = Lead(
                region_id=region.id,
                name=name_val,
                district=_str_or_none(row.get(col_map.get("district", ""))),
                settlement=_str_or_none(row.get(col_map.get("settlement", ""))),
                address=_str_or_none(row.get(col_map.get("address", ""))),
                inn=_str_or_none(row.get(col_map.get("inn", ""))),
                head_name=_str_or_none(row.get(col_map.get("head_name", ""))),
                site=_str_or_none(row.get(col_map.get("site", ""))),
                rapeseed_info=_str_or_none(row.get(col_map.get("rapeseed_info", ""))),
                level=level_val,
                priority=normalize_priority(row.get(col_map.get("priority", ""))),
                general_comment=_str_or_none(row.get(col_map.get("general_comment", ""))),
                done_summary=_str_or_none(row.get(col_map.get("done_summary", ""))),
                todo_summary=_str_or_none(row.get(col_map.get("todo_summary", ""))),
            )

            if is_blacklist:
                lead.stage = "lost"
                lead.loss_reason = "Чёрный список (из xlsx)"

            session.add(lead)
            await session.flush()

            phones_raw = str(row.get(col_map.get("phones_raw", ""), ""))
            parsed = parse_phones(phones_raw)
            for p in parsed:
                if p["phone"] or p["name"]:
                    contact = Contact(
                        lead_id=lead.id,
                        name=p["name"],
                        position=p["position"],
                        phone=p["phone"],
                        note=p["note"],
                    )
                    session.add(contact)
                    stats["contacts"] += 1

            lead_contact_logs = []
            for dc in date_columns:
                cell = row.get(dc)
                if cell and not pd.isna(cell) and str(cell).strip():
                    outcome = classify_outcome(str(cell))
                    cl = ContactLog(
                        lead_id=lead.id,
                        contact_date=dc,
                        result=str(cell).strip(),
                        outcome=outcome,
                    )
                    session.add(cl)
                    lead_contact_logs.append({"outcome": outcome, "result": str(cell).strip()})
                    stats["contact_logs"] += 1

            if not is_blacklist:
                lead.stage = determine_stage(lead_contact_logs)

            stats["leads"] += 1

            if stats["leads"] % 50 == 0:
                await session.flush()

    await session.flush()
    return stats


def _str_or_none(val) -> str | None:
    if val is None or pd.isna(val):
        return None
    if isinstance(val, float) and val == int(val):
        val = int(val)
    s = str(val).strip()
    if s.lower() in ("nan", "—", "-", ""):
        return None
    return s
