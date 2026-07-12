import httpx

from app.config import settings


DADATA_SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
DADATA_FIND_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"


async def find_party_by_inn(inn: str) -> dict:
    """
    Точный поиск контрагента по ИНН через DaData findById/party.
    Возвращает {"result": {...} | None, "error": str | None}.
    """
    if not settings.DADATA_API_KEY:
        return {"result": None, "error": "DaData API key не настроен"}

    headers = _headers()
    payload = {"query": inn.strip(), "branch_type": "MAIN"}

    try:
        async with httpx.AsyncClient(timeout=settings.DADATA_TIMEOUT) as client:
            resp = await client.post(DADATA_SUGGEST_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            suggestions = data.get("suggestions", [])
            if not suggestions:
                return {"result": None, "error": None}
            return {"result": _extract(suggestions[0]), "error": None}
    except httpx.ConnectError:
        return {"result": None, "error": "Не удалось подключиться к DaData"}
    except httpx.TimeoutException:
        return {"result": None, "error": "DaData не ответила вовремя"}
    except Exception as e:
        return {"result": None, "error": str(e)}


async def suggest_party(query: str, count: int = 5) -> dict:
    """
    Поиск контрагентов по названию/ИНН через DaData suggest/party.
    Возвращает {"results": [...], "error": str | None}.
    """
    if not settings.DADATA_API_KEY:
        return {"results": [], "error": "DaData API key не настроен"}

    headers = _headers()
    payload = {"query": query.strip(), "count": count}

    try:
        async with httpx.AsyncClient(timeout=settings.DADATA_TIMEOUT) as client:
            resp = await client.post(DADATA_FIND_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            suggestions = data.get("suggestions", [])
            results = [_extract(s) for s in suggestions]
            return {"results": results, "error": None}
    except httpx.ConnectError:
        return {"results": [], "error": "Не удалось подключиться к DaData"}
    except httpx.TimeoutException:
        return {"results": [], "error": "DaData не ответила вовремя"}
    except Exception as e:
        return {"results": [], "error": str(e)}


def _headers() -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Token {settings.DADATA_API_KEY}",
    }
    if settings.DADATA_SECRET_KEY:
        headers["X-Secret"] = settings.DADATA_SECRET_KEY
    return headers


def _extract(suggestion: dict) -> dict:
    """
    Извлекает базовые реквизиты из ответа DaData.
    """
    data = suggestion.get("data", {})
    return {
        "inn": data.get("inn", ""),
        "name": (suggestion.get("value") or "").strip(),
        "full_name": data.get("name", {}).get("full_with_opf", ""),
        "ogrn": data.get("ogrn", ""),
        "kpp": data.get("kpp", ""),
        "okpo": data.get("okpo", ""),
        # Адрес (юридический — DaData отдаёт зарегистрированный адрес)
        "address": data.get("address", {}).get("value", ""),
        # Руководитель
        "head_name": _person_name(data.get("management", {})),
        # Контакты
        "phones": _extract_phones(data),
        "site": _extract_site(data),
        # Дополнительно
        "okved": data.get("okved", ""),
        "status": data.get("state", {}).get("status", ""),
    }


def _person_name(management: dict) -> str:
    if not management:
        return ""
    name = management.get("name", "")
    if name:
        return name.strip()
    return ""


def _extract_phones(data: dict) -> str:
    phones = data.get("phones", [])
    if not phones:
        return ""
    return phones[0].get("value", "")


def _extract_site(data: dict) -> str:
    site = (data.get("opf") or {}).get("code", "")
    # DaData не всегда возвращает сайт напрямую — извлечём из email/phones если есть
    emails = data.get("emails", [])
    if emails:
        email = emails[0].get("value", "")
        # Из email вида info@company.ru можно получить домен
        if "@" in email:
            domain = email.split("@")[-1]
            if domain and domain not in ("mail.ru", "gmail.com", "yandex.ru"):
                return domain
    return ""
