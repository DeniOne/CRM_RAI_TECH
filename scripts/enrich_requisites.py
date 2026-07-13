"""
Bulk-обогащение реквизитов лидов через DaData suggest/party.

Для каждого лида с пустым ИНН:
  1. Чистит название (убирает ОПФ — ООО/АО/... — кавычки, лишние пробелы).
  2. Запрашивает DaData suggest/party с region-фильтром (lead.region.name).
  3. Заполняет ТОЛЬКО пустые поля (inn, ogrn, kpp, okpo, legal_address,
     head_name, site) — не перетирает вручную введённые данные.
  4. Логирует unmatched/ошибки в storage/exports/enrich_report_<ts>.json.

Лимиты DaData (free): 10 000 запросов/день, 10 RPS.
Sleep 0.15s между запросами ≈ 6.6 RPS — с запасом.

Использование:
  python scripts/enrich_requisites.py                  # все лиды с пустым ИНН
  python scripts/enrich_requisites.py --manager-id 4   # только Екатерина
  python scripts/enrich_requisites.py --dry-run        # без записи, только отчёт
  python scripts/enrich_requisites.py --region-id 4    # только Кировская обл.

На сервере:
  docker cp scripts/enrich_requisites.py crm-rai-dev:/app/scripts/enrich_requisites.py
  docker exec crm-rai-dev python scripts/enrich_requisites.py --dry-run
"""
import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select, or_

from app.config import settings
from app.database import init_db, async_session_maker
from app.models import Lead, Region
from app.services.dadata_service import DADATA_FIND_URL, _extract, _headers

# Пауза между запросами к DaData (сек). ~6.6 RPS при лимите 10.
REQUEST_DELAY = 0.15
# Таймаут одного запроса (сек).
REQUEST_TIMEOUT = settings.DADATA_TIMEOUT

# Карта: название региона в CRM → допустимые коды субъектов РФ (первые 2 цифры ИНН).
# Источник: ФНС, коды субъектов РФ. Если найденный DaData ИНН начинается с кода не из
# списка — совпадение считается ложным (компания из другого региона).
# DaData locations/restrict_value ненадёжно фильтруют по региону, поэтому проверяем сами.
REGION_INN_CODES: dict[str, list[str]] = {
    "Псковская область": ["60"],
    "Нижний Новгород": ["52"],
    "Кировская область": ["43"],
    "Воронежская область": ["36"],
    "Челябенская+2": ["74", "75"],
    "Свердловская+2": ["66", "92"],
    "Марий Эл": ["12"],
    "Ярославская": ["76"],
    "Владимерская": ["33"],
    "Костромская": ["44"],
    "Пензенская": ["58"],
    "Алтайский край +4": ["22", "04"],
    "Липецкая область": ["48"],
    "Курская область": ["46"],
    "Белгородская область": ["31"],
    "Рязанская область": ["62"],
    "Чувашия": ["21"],
    "Ульяновская": ["73"],
    "Волгоградскя": ["34"],
    "Саратовская +1ч": ["64"],
    "Оренбурская +2ч": ["56"],
    "Курганская +2": ["45"],
    "Пермский +2": ["59", "81"],
    "Тюменская +2": ["72", "86", "89"],
    "Омская +3": ["55"],
    "красноярский край +4": ["24", "84", "88"],
    "Новосибирская+4": ["54", "42"],
    "Томская +4": ["70"],
    "Не звонить": [],  # без проверки
}

# ОПФ и шумовые слова для очистки названия перед поиском.
_OPF = r"(?:ООО|ОАО|ЗАО|ПАО|НАО|АО|ИП|КФХ|СПК|ТНВ|ОП|ГК)\b"
_QUOTES = r"[«»\"'\u2018\u2019\u201c\u201d]"


def clean_query(name: str) -> str:
    """Очистка названия для DaData: убрать ОПФ, кавычки, лишние пробелы."""
    if not name:
        return ""
    s = str(name)
    # убрать формы собственности (в начале и в скобках)
    s = re.sub(_OPF, "", s, flags=re.IGNORECASE)
    # убрать кавычки
    s = re.sub(_QUOTES, "", s)
    # убрать висячую пунктуацию и лишние пробелы
    s = re.sub(r"[\(\)]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,;:-")
    return s


def inn_matches_region(inn: str, region_name: str | None) -> bool:
    """
    Проверяет, что первые 2 цифры ИНН входят в список кодов региона.
    Если регион неизвестен или без карты кодов — пропускаем проверку (True).
    """
    if not region_name or not inn:
        return True
    codes = REGION_INN_CODES.get(region_name)
    if codes is None or not codes:
        return True  # регион не в карте — не проверяем
    inn = str(inn).strip()
    if len(inn) < 2:
        return True
    return inn[:2] in codes


async def enrich_one(client: httpx.AsyncClient, lead: Lead, region_name: str | None) -> dict:
    """
    Обогащает один лид через DaData. Возвращает отчёт по операции:
    {"status": "updated"|"unmatched"|"error", "matched_name": ..., "fields": [...], "detail": ...}

    Защита от ложных совпадений: DaData locations/restrict_value ненадёжно фильтруют
    по региону, поэтому после поиска проверяем код региона по первым 2 цифрам ИНН.
    Если ИНН не из нужного региона — считаем unmatched (не записываем ложные данные).
    """
    query = clean_query(lead.name)
    if not query:
        return {"status": "error", "detail": "пустое название после очистки"}

    payload = {"query": query, "count": 1}
    if region_name:
        payload["locations"] = [{"region": region_name}]
        payload["restrict_value"] = True

    try:
        resp = await client.post(DADATA_FIND_URL, json=payload, headers=_headers())
        resp.raise_for_status()
        suggestions = resp.json().get("suggestions", [])
    except Exception as e:
        return {"status": "error", "detail": f"HTTP: {e}"}

    if not suggestions:
        return {"status": "unmatched", "query": query, "region": region_name, "reason": "no hits"}

    d = _extract(suggestions[0])

    # Проверка региона по коду ИНН — главный фильтр от ложных совпадений.
    if not inn_matches_region(d.get("inn", ""), region_name):
        return {
            "status": "unmatched",
            "query": query,
            "region": region_name,
            "reason": f"ИНН {d.get('inn')} не из региона {region_name}",
            "matched_name": d.get("name"),
            "matched_inn": d.get("inn"),
        }

    filled = []
    # fill-only-empty: пишем только в пустые поля.
    if not lead.inn and d.get("inn"):
        lead.inn = d["inn"]; filled.append("inn")
    if not lead.ogrn and d.get("ogrn"):
        lead.ogrn = d["ogrn"]; filled.append("ogrn")
    if not lead.kpp and d.get("kpp"):
        lead.kpp = d["kpp"]; filled.append("kpp")
    if not lead.okpo and d.get("okpo"):
        lead.okpo = d["okpo"]; filled.append("okpo")
    if not lead.legal_address and d.get("address"):
        lead.legal_address = d["address"]; filled.append("legal_address")
    if not lead.head_name and d.get("head_name"):
        lead.head_name = d["head_name"]; filled.append("head_name")
    if not lead.site and d.get("site"):
        lead.site = d["site"]; filled.append("site")

    return {
        "status": "updated",
        "matched_name": d.get("name"),
        "matched_inn": d.get("inn"),
        "fields": filled,
        "query": query,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk-обогащение реквизитов через DaData")
    parser.add_argument("--manager-id", type=int, default=None, help="Только лиды этого менеджера")
    parser.add_argument("--region-id", type=int, default=None, help="Только лиды этого региона")
    parser.add_argument("--dry-run", action="store_true", help="Без записи в БД, только отчёт")
    parser.add_argument("--limit", type=int, default=None, help="Ограничить кол-во (для теста)")
    args = parser.parse_args()

    await init_db()

    async with async_session_maker() as session:
        # Выборка лидов с пустым ИНН.
        stmt = select(Lead).where(or_(Lead.inn == None, Lead.inn == ""))  # noqa: E711
        if args.manager_id:
            stmt = stmt.where(Lead.assigned_manager_id == args.manager_id)
        if args.region_id:
            stmt = stmt.where(Lead.region_id == args.region_id)
        stmt = stmt.order_by(Lead.id)
        if args.limit:
            stmt = stmt.limit(args.limit)

        result = await session.execute(stmt)
        leads = result.scalars().all()
        total = len(leads)
        print(f"Лидов с пустым ИНН к обогащению: {total}")
        if args.dry_run:
            print(">>> DRY RUN — запись в БД отключена")
        if total == 0:
            return 0

        # Префетч имён регионов одним запросом.
        region_ids = {l.region_id for l in leads if l.region_id}
        region_names: dict[int, str] = {}
        if region_ids:
            rres = await session.execute(select(Region).where(Region.id.in_(region_ids)))
            for r in rres.scalars().all():
                region_names[r.id] = r.name

        updated, unmatched, errors = [], [], []
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            for i, lead in enumerate(leads, 1):
                region_name = region_names.get(lead.region_id)
                report = await enrich_one(client, lead, region_name)
                report["lead_id"] = lead.id
                report["lead_name"] = lead.name
                report["region"] = region_name

                if report["status"] == "updated":
                    updated.append(report)
                    fields = ",".join(report.get("fields", []))
                    print(f"[{i}/{total}] id={lead.id} OK  {lead.name[:40]!r} → inn={report.get('matched_inn')} [{fields}]")
                elif report["status"] == "unmatched":
                    unmatched.append(report)
                    print(f"[{i}/{total}] id={lead.id} ---  {lead.name[:40]!r} не найден (q={report.get('query')!r} region={region_name})")
                else:
                    errors.append(report)
                    print(f"[{i}/{total}] id={lead.id} ERR {lead.name[:40]!r}: {report.get('detail')}")

                await asyncio.sleep(REQUEST_DELAY)

        if not args.dry_run:
            await session.commit()
            print(f"\nБД закоммичена: {len(updated)} лидов обновлено.")
        else:
            print(f"\nDRY RUN: изменения не сохранены. Было бы обновлено {len(updated)} лидов.")

        # Отчёт в файл.
        os.makedirs("storage/exports", exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        report_path = f"storage/exports/enrich_report_{ts}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({
                "total": total,
                "updated": len(updated),
                "unmatched": len(unmatched),
                "errors": len(errors),
                "dry_run": args.dry_run,
                "filter": {"manager_id": args.manager_id, "region_id": args.region_id},
                "updated_leads": updated,
                "unmatched_leads": unmatched,
                "error_leads": errors,
            }, f, ensure_ascii=False, indent=2, default=str)
        print(f"Отчёт: {report_path}")
        print(f"\nИТОГО: updated={len(updated)} unmatched={len(unmatched)} errors={len(errors)} из {total}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
