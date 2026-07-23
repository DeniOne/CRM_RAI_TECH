import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _hermes_timeout() -> httpx.Timeout:
    """Раздельные лимиты по фазам соединения.

    connect/write/pool — короткие (10с): если Hermes не принимает запрос или
    соединение встало, падаем быстро и понятно (ConnectError, а не «не ответил
    вовремя»). read — длинный (HERMES_TIMEOUT): агентные запросы с tool-use
    легитимно идут десятки секунд, и ответ надо дождаться.
    """
    read = settings.HERMES_TIMEOUT
    return httpx.Timeout(connect=10.0, read=read, write=10.0, pool=10.0)


async def send_to_hermes(
    message: str,
    user_id: int,
    user_name: str,
    role: str,
    context_lead_id: int = None,
    search_mode: str = "crm",
) -> dict:
    """
    Отправляет сообщение в Hermes через OpenAI-совместимый API.
    POST {HERMES_API_URL}/v1/chat/completions
    Возвращает {"reply": str, "actions": [], "error": str|None}.

    search_mode: "crm" (по умолчанию — primary-поиск в CRM) или "internet"
    (primary-поиск в интернете, но CRM доступна если запрос явно про данные CRM).

    При таймауте делает одну тихую повторную попытку тем же payload — зависания
    агента часто стохастичны (долгий веб-поиск, ретраи upstream-модели), и второй
    запрос нередко укладывается.
    """
    if not settings.HERMES_ENABLED:
        return {
            "reply": "Агент отключён в настройках.",
            "actions": [],
            "error": "disabled",
        }

    # OpenAI Chat Completions формат.
    # Базовая часть одинакова для обоих режимов.
    base = (
        f"Ты — AI-ассистент CRM RAI. Работаешь с пользователем {user_name} (роль: {role}). "
        f"Отвечай кратко и по делу. "
    )

    if search_mode == "internet":
        # Internet-режим: веб-поиск — ОБЯЗАТЕЛЬНЫЙ первичный источник. Прежний
        # промпт был внутренне противоречив («ищи в интернете, НО если про CRM —
        # в CRM»), и агент почти всегда выбирал CRM, потому что MCP-тулы быстрее
        # и надёжнее. Теперь: ищи в интернете ВСЕГДА, кроме случая, когда
        # пользователь ЯВНО написал «в нашей базе / в CRM / у нас».
        system_content = base + (
            f"РЕЖИМ ПОИСКА: INTERNET. В этом режиме ОТВЕЧАЙ ТОЛЬКО на основе "
            f"веб-поиска — используй инструменты web_search, web_extract, browser. "
            f"Это твоё ПЕРВИЧНОЕ и основное действие по любому запросу, даже если "
            f"запрос звучит как поиск компании/контакта/телефона — ищи их В ИНТЕРНЕТЕ, "
            f"а не в CRM. "
            f"Инструменты CRM (search_leads и др.) в этом режиме НЕ используй — "
            f"только если пользователь ЯВНО написал «в нашей базе», «в CRM», «у нас». "
            f"Если web_search вернул ошибку/пусто — попробуй browser или переформулируй "
            f"запрос; не откатывайся в CRM автоматически. "
            f"Источники цитируй (сайт, ссылка). "
            f"ИСКЛЮЧЕНИЕ — запросы по ИНН/ОГРН контрагента (реквизиты, проверить "
            f"компанию, «это холдинг?», учредители, статус): используй инструменты "
            f"lookup_company_by_inn и find_affiliated_companies (DaData) — это быстро "
            f"(~1с) и надёжно, НЕ используй для них браузер/веб-поиск по сайтам-реестрам "
            f"(они виснут по 60с из-за антиспама)."
        )
    else:
        # CRM-режим — byte-identical прежнему промпту (не меняем дефолтное поведение).
        system_content = base + (
            f"ВАЖНО: все запросы о клиентах, хозяйствах, лидах, контактах, задачах, сделках — "
            f"выполняй ТОЛЬКО через инструменты CRM (MCP). НЕ используй web_search, browser, "
            f"web_extract для таких запросов — они вызовут таймаут. "
            f"Если в базе CRM нет данных — так и скажи, не ищи в интернете. "
            f"Веб-поиск разрешён только если пользователь явно просит найти внешнюю информацию "
            f"(новости, статьи, сайты). "
            f"Для внешней проверки контрагента по ИНН/ОГРН (реквизиты, «это холдинг?», "
            f"учредители, статус) — используй инструменты lookup_company_by_inn и "
            f"find_affiliated_companies (DaData, MCP): они быстрые и не зависают."
        )

    if context_lead_id:
        system_content += f" Текущий контекст: работа с лидом ID {context_lead_id}."

    payload = {
        "model": "hermes-agent",
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": message},
        ],
    }

    headers = {"Content-Type": "application/json"}
    if settings.HERMES_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.HERMES_API_TOKEN}"

    # Одна повторная попытка при таймауте (зависания агента часто стохастичны).
    last_exc: Exception | None = None
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=_hermes_timeout()) as client:
                resp = await client.post(
                    f"{settings.HERMES_API_URL}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                # OpenAI формат: choices[0].message.content
                reply = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "Пустой ответ от агента.")
                )
                return {
                    "reply": reply,
                    "actions": [],
                    "error": None,
                }
        except httpx.TimeoutException as e:
            last_exc = e
            if attempt == 1:
                logger.warning(
                    "Hermes timeout (attempt 1/%ds), retrying once — %r",
                    settings.HERMES_TIMEOUT,
                    message[:80],
                )
                continue
            logger.warning(
                "Hermes timeout after retry (attempt 2): %r", message[:80]
            )
            return {
                "reply": (
                    "Не удалось получить ответ за отведённое время — запрос, "
                    "видимо, потребовал долгого поиска. Попробуйте сформулировать "
                    "короче или уточнить (например, название компании вместо номера "
                    "телефона), либо повторите через минуту."
                ),
                "actions": [],
                "error": "timeout",
            }
        except httpx.ConnectError:
            return {
                "reply": "Не удалось подключиться к агенту. Проверьте, что Hermes запущен.",
                "actions": [],
                "error": "connection",
            }
        except Exception as e:
            return {
                "reply": f"Произошла ошибка при обращении к агенту: {str(e)}",
                "actions": [],
                "error": str(e),
            }
    # Сюда попадаем только если цикл завершился нетипично.
    return {
        "reply": f"Произошла ошибка при обращении к агенту: {last_exc}",
        "actions": [],
        "error": str(last_exc) if last_exc else "unknown",
    }
