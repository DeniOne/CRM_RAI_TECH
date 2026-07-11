import httpx

from app.config import settings


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
        # Primary — интернет. CRM-инструменты доступны, если запрос явно про
        # данные из базы (клиенты, лиды, задачи, сделки). По умолчанию — веб-поиск.
        system_content = base + (
            f"Режим поиска: INTERNET (основной источник — интернет). "
            f"По умолчанию используй инструменты веб-поиска: web_search, browser, "
            f"web_extract. Это основной режим работы в этом чате. "
            f"НО если запрос явно про данные из CRM (найти клиента, лида, хозяйство, "
            f"задачу, сделку, контакт, историю взаимодействий) — используй инструменты "
            f"CRM (MCP): search_leads, get_lead_details, search_tasks и т.д. "
            f"Не смешивай источники без необходимости: либо веб, либо CRM в зависимости "
            f"от сути запроса."
        )
    else:
        # CRM-режим — byte-identical прежнему промпту (не меняем дефолтное поведение).
        system_content = base + (
            f"ВАЖНО: все запросы о клиентах, хозяйствах, лидах, контактах, задачах, сделках — "
            f"выполняй ТОЛЬКО через инструменты CRM (MCP). НЕ используй web_search, browser, "
            f"web_extract для таких запросов — они вызовут таймаут. "
            f"Если в базе CRM нет данных — так и скажи, не ищи в интернете. "
            f"Веб-поиск разрешён только если пользователь явно просит найти внешнюю информацию "
            f"(новости, статьи, сайты)."
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

    try:
        async with httpx.AsyncClient(timeout=settings.HERMES_TIMEOUT) as client:
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
    except httpx.ConnectError:
        return {
            "reply": "Не удалось подключиться к агенту. Проверьте, что Hermes запущен.",
            "actions": [],
            "error": "connection",
        }
    except httpx.TimeoutException:
        return {
            "reply": "Агент не ответил вовремя. Попробуйте ещё раз.",
            "actions": [],
            "error": "timeout",
        }
    except Exception as e:
        return {
            "reply": f"Произошла ошибка при обращении к агенту: {str(e)}",
            "actions": [],
            "error": str(e),
        }
