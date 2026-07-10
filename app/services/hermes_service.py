import httpx

from app.config import settings


async def send_to_hermes(
    message: str,
    user_id: int,
    user_name: str,
    role: str,
    context_lead_id: int = None,
) -> dict:
    if not settings.HERMES_ENABLED:
        return {
            "reply": "Агент отключён в настройках.",
            "actions": [],
            "error": "disabled",
        }

    payload = {
        "message": message,
        "user_id": user_id,
        "user_name": user_name,
        "context": {
            "role": role,
            "current_lead_id": context_lead_id,
        },
    }

    headers = {"Content-Type": "application/json"}
    if settings.HERMES_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.HERMES_API_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=settings.HERMES_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.HERMES_API_URL}/api/chat",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "reply": data.get("reply", "Пустой ответ от агента."),
                "actions": data.get("actions", []),
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
