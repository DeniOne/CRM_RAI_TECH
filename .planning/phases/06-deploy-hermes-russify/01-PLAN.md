---
phase: 6-deploy-hermes-russify
plan: "01"
slice: 6-01
type: execute
wave: 1
depends_on:
  - phase-5
requirements:
  - CRM-6-01
autonomous: true
files_modified:
  - app/config.py
  - app/models.py
  - app/main.py
  - app/templates/base.html
  - app/templates/tasks.html
  - app/templates/dashboard.html
  - app/templates/partials/tasks_list.html
  - requirements.txt
files_created:
  - app/routes/agent.py
  - app/services/hermes_service.py
  - app/templates/agent_chat.html
  - app/templates/partials/agent_message_pair.html
must_haves:
  truths:
    - "D-01: app/config.py содержит HERMES_API_URL (default http://localhost:8080), HERMES_API_TOKEN (default пусто), HERMES_TIMEOUT (default 30), HERMES_ENABLED (default true) — все читаются из .env через pydantic-settings"
    - "D-02: app/models.py — новая модель AgentMessage: id, user_id (FK users), role (String 'user'|'assistant'), content (Text), context_lead_id (FK leads, nullable), actions (Text nullable, JSON), created_at. Связь user (relationship)"
    - "D-03: app/services/hermes_service.py — async send_to_hermes(message, user_id, user_name, role, context_lead_id=None) -> dict. POST на {HERMES_API_URL}/api/chat, body: {message, user_id, user_name, context:{role, current_lead_id}}. Возвращает {reply, actions}. Graceful degradation: ConnectError→'Не удалось подключиться к агенту...', TimeoutException→'Агент не ответил вовремя...', HERMES_ENABLED=False→'Агент отключён.'"
    - "D-04: app/routes/agent.py — GET /agent: страница чата, загружает последние 50 AgentMessage пользователя, рендерит agent_chat.html"
    - "D-05: app/routes/agent.py — POST /agent/send: Form(message, context_lead_id optional). Сохраняет AgentMessage(role='user'), вызывает send_to_hermes(), сохраняет AgentMessage(role='assistant', content=reply, actions=JSON). Возвращает partial agent_message_pair.html (HTMX swap beforeend)"
    - "D-06: app/routes/agent.py — POST /agent/clear: удаляет все AgentMessage текущего user_id, редирект на /agent"
    - "D-07: При недоступности Hermes (ConnectError/Timeout) — AgentMessage(role='assistant') сохраняется с текстом ошибки, история не теряется"
    - "D-08: app/templates/agent_chat.html — UI по AI Dock канону: header (заголовок 'Чат с агентом'), history (bubble-сообщения: user=bg-ink text-white right-aligned, assistant=bg-slate-50 border left-aligned), composer (input + кнопка 'Отправить' primary bg-ink). Quick actions: 3 кнопки ('Найти клиентов', 'Мои задачи', 'Создать задачу')"
    - "D-09: app/templates/partials/agent_message_pair.html — partial: сообщение пользователя (bg-ink, right) + ответ агента (bg-slate-50 border, left) + время. Для HTMX-swap beforeend в #chat-history"
    - "D-10: app/templates/base.html — sidebar: 'Таски' заменено на 'Задачи', добавлен пункт 'Чат с агентом' → /agent"
    - "D-11: Во ВСЕХ шаблонах: 0 вхождений 'таски' или 'тасков' (grep -ri 'таск' app/templates/ → 0)"
    - "D-12: Весь UI-текст на русском языке. Проверка: кодер проходит по всем шаблонам, проверяет placeholder, кнопки, empty states, tooltip. Английские слова заменяются на русские, кроме спецобозначений (ИНН, КП, БИК, PDF, .docx, ID)"
    - "D-13: requirements.txt — добавлен httpx"
    - "D-14: app/main.py — подключен agent.router"
    - "D-15: Сервер запускается без ошибок, GET /agent → 200, чат рендерится"
    - "D-16: POST /agent/send — при отключённом Hermes возвращает сообщение об ошибке, не падает"
    - "D-17: Функциональность не сломана: канбан, карточка лида, документы, отчёты — всё работает"
    - "D-18: init_db() создаёт таблицу agent_messages при старте (Base.metadata.create_all)"
  artifacts:
    - path: app/services/hermes_service.py
      provides: "HTTP-клиент Hermes с graceful degradation"
    - path: app/routes/agent.py
      provides: "Чат с агентом: история, отправка, очистка"
    - path: app/templates/agent_chat.html
      provides: "AI Dock UI по Visual Canon"
  key_links:
    - from: app/routes/agent.py
      to: app/services/hermes_service.py
      via: "send_to_hermes(message, user_id, ...)"
      pattern: "Hermes API call"
    - from: app/templates/agent_chat.html
      to: app/routes/agent.py
      via: "hx-post /agent/send + hx-target #chat-history"
      pattern: "HTMX chat"
---

# Plan 6-01 — Hermes AI Dock + русификация UI (Wave 1)

**Phase:** 6 — deploy-hermes-russify
**Wave:** B-1
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст

CRM RAI завершён функционально (Фазы 1–5) и визуально (Visual Canon). Фаза 6 добавляет:
1. **Hermes AI Dock** — чат с AI-агентом в CRM. Hermes работает как HTTP API (webhook) на `http://localhost:8080/api/chat`. CRM обращается через httpx.
2. **Русификация UI** — «Таски» → «Задачи» везде. Правило: весь UI-текст только на русском (кроме спецобозначений).

Деплой (Docker) и интеграция с Hermes на сервере — отдельный блок техлида, НЕ кодера. Кодер делает только локальный код.

## Стек

- **HTTP-клиент:** httpx (async) — уже установлен
- **Транспорт:** HTTP POST (без SSE/WebSocket)
- **Грейсфул деградация:** при недоступности Hermes — сообщение об ошибке, история сохраняется

## Что делает кодер (пофайлово)

### 1. `app/config.py` (модификация)

Добавить 4 поля в Settings:
```python
HERMES_API_URL: str = "http://localhost:8080"
HERMES_API_TOKEN: str = ""
HERMES_TIMEOUT: int = 30
HERMES_ENABLED: bool = True
```

### 2. `requirements.txt` (модификация)

Добавить в конец:
```
httpx
```

### 3. `app/models.py` (модификация) — AgentMessage

Добавить после DocumentTemplate:
```python
class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    context_lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id"), nullable=True)
    actions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-строка
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship()
```

### 4. `app/services/hermes_service.py` (новый)

```python
import json
import httpx
from app.config import settings


async def send_to_hermes(
    message: str,
    user_id: int,
    user_name: str,
    role: str,
    context_lead_id: int = None,
) -> dict:
    """
    Отправляет сообщение в Hermes API.
    Возвращает {"reply": str, "actions": list, "error": str|None}.
    
    Graceful degradation:
    - HERMES_ENABLED=False → "Агент отключён в настройках."
    - ConnectError → "Не удалось подключиться к агенту. Проверьте, что Hermes запущен."
    - TimeoutException → "Агент не ответил вовремя. Попробуйте ещё раз."
    """
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
```

### 5. `app/routes/agent.py` (новый)

```python
import json
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import AgentMessage
from app.services.hermes_service import send_to_hermes

router = APIRouter()


@router.get("/agent", response_class=HTMLResponse)
async def agent_chat_page(request: Request, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        return RedirectResponse("/login", status_code=303)

    result = await session.execute(
        select(AgentMessage)
        .where(AgentMessage.user_id == user.id)
        .order_by(AgentMessage.created_at.desc())
        .limit(50)
    )
    messages = list(result.scalars().all())
    messages.reverse()  # хронологический порядок

    return templates.TemplateResponse(
        request=request,
        name="agent_chat.html",
        context={"current_user": user, "messages": messages},
    )


@router.post("/agent/send", response_class=HTMLResponse)
async def agent_send(
    request: Request,
    message: str = Form(...),
    context_lead_id: int = Form(None),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    # Сохранить сообщение пользователя
    user_msg = AgentMessage(
        user_id=user.id,
        role="user",
        content=message,
        context_lead_id=context_lead_id,
    )
    session.add(user_msg)
    await session.flush()

    # Вызвать Hermes
    result = await send_to_hermes(
        message=message,
        user_id=user.id,
        user_name=user.full_name,
        role=user.role.value,
        context_lead_id=context_lead_id,
    )

    # Сохранить ответ агента
    assistant_msg = AgentMessage(
        user_id=user.id,
        role="assistant",
        content=result["reply"],
        context_lead_id=context_lead_id,
        actions=json.dumps(result["actions"], ensure_ascii=False) if result["actions"] else None,
    )
    session.add(assistant_msg)
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/agent_message_pair.html",
        context={
            "current_user": user,
            "user_message": message,
            "agent_reply": result["reply"],
            "agent_actions": result["actions"],
            "created_at": assistant_msg.created_at,
        },
    )


@router.post("/agent/clear")
async def agent_clear(request: Request, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    await session.execute(
        delete(AgentMessage).where(AgentMessage.user_id == user.id)
    )
    await session.commit()
    return RedirectResponse("/agent", status_code=303)
```

### 6. `app/templates/agent_chat.html` (новый)

```html
{% extends "base.html" %}
{% block title %}Чат с агентом — CRM RAI{% endblock %}
{% block content %}

<div class="max-w-3xl mx-auto">
    <div class="flex justify-between items-center mb-4">
        <h1 class="text-2xl font-medium text-ink">Чат с агентом</h1>
        <form action="/agent/clear" method="post">
            <button type="submit" class="text-muted hover:text-ink text-sm">Очистить историю</button>
        </form>
    </div>

    <!-- История сообщений -->
    <div id="chat-history" class="bg-white border border-black/10 rounded-2xl p-6 mb-4 min-h-[400px] max-h-[600px] overflow-y-auto space-y-4">
        {% for msg in messages %}
        <div class="{% if msg.role == 'user' %}text-right{% else %}text-left{% endif %}">
            <div class="inline-block max-w-[80%] px-4 py-2 rounded-2xl
                {% if msg.role == 'user' %}
                    bg-ink text-white
                {% else %}
                    bg-slate-50 border border-black/10 text-ink
                {% endif %}">
                <div class="text-sm whitespace-pre-wrap">{{ msg.content }}</div>
            </div>
            <div class="text-xs text-muted mt-1">{{ msg.created_at.strftime('%H:%M') if msg.created_at else '' }}</div>
        </div>
        {% else %}
        <div class="text-center text-muted py-12">
            <div class="text-sm">Начните разговор с агентом</div>
            <div class="text-xs mt-2">Например: «Найди клиентов в Псковской области»</div>
        </div>
        {% endfor %}
    </div>

    <!-- Composer -->
    <form hx-post="/agent/send" hx-target="#chat-history" hx-swap="beforeend"
          hx-on::after-request="document.getElementById('message-input').value=''; document.getElementById('chat-history').scrollTop = document.getElementById('chat-history').scrollHeight"
          class="flex gap-2">
        <input type="hidden" name="context_lead_id" value="">
        <input type="text" id="message-input" name="message" required
               placeholder="Напишите сообщение агенту..."
               class="flex-1 border border-black/10 rounded-lg px-4 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-ink/20">
        <button type="submit" class="bg-ink text-white px-6 py-2 rounded-lg text-sm hover:bg-ink/90">
            Отправить
        </button>
    </form>

    <!-- Quick actions -->
    <div class="mt-4 flex flex-wrap gap-2">
        <button onclick="document.getElementById('message-input').value='Найди клиентов уровня A в Псковской области'"
                class="bg-white border border-black/10 px-3 py-1.5 rounded-lg text-xs text-muted hover:text-ink hover:bg-slate-50">
            Найти клиентов
        </button>
        <button onclick="document.getElementById('message-input').value='Какие у меня задачи на сегодня?'"
                class="bg-white border border-black/10 px-3 py-1.5 rounded-lg text-xs text-muted hover:text-ink hover:bg-slate-50">
            Мои задачи
        </button>
        <button onclick="document.getElementById('message-input').value='Создай задачу: перезвонить ООО Тригорское завтра'"
                class="bg-white border border-black/10 px-3 py-1.5 rounded-lg text-xs text-muted hover:text-ink hover:bg-slate-50">
            Создать задачу
        </button>
    </div>
</div>

{% endblock %}
```

### 7. `app/templates/partials/agent_message_pair.html` (новый)

```html
<!-- Сообщение пользователя -->
<div class="text-right mb-2">
    <div class="inline-block max-w-[80%] px-4 py-2 rounded-2xl bg-ink text-white">
        <div class="text-sm whitespace-pre-wrap">{{ user_message }}</div>
    </div>
</div>
<!-- Ответ агента -->
<div class="text-left mb-4">
    <div class="inline-block max-w-[80%] px-4 py-2 rounded-2xl bg-slate-50 border border-black/10 text-ink">
        <div class="text-sm whitespace-pre-wrap">{{ agent_reply }}</div>
    </div>
    {% if created_at %}
    <div class="text-xs text-muted mt-1">{{ created_at.strftime('%H:%M') }}</div>
    {% endif %}
</div>
```

### 8. `app/main.py` (модификация)

```python
from app.routes import auth, dashboard, leads, tasks, documents, deals, reports, agent
app.include_router(agent.router)
```

### 9. `app/templates/base.html` (модификация)

В sidebar:
- «Таски» → «Задачи»
- Добавить после «Сделки»:
```html
<a href="/agent" class="block px-3 py-2 rounded-lg text-sm text-ink hover:bg-slate-100">Чат с агентом</a>
```

### 10. Русификация — все шаблоны

**«Таски» → «Задачи»:**

| Файл | Найти | Заменить на |
|---|---|---|
| `base.html` | `>Таски<` | `>Задачи<` |
| `tasks.html:2` | `Таски — CRM RAI` | `Задачи — CRM RAI` |
| `tasks.html:4` | `Мои таски` | `Мои задачи` |
| `tasks.html:20` | `Нет тасков` | `Нет задач` |
| `partials/tasks_list.html:2` | `>Таски<` | `>Задачи<` |
| `partials/tasks_list.html:11` | `Нет тасков` | `Нет задач` |
| `dashboard.html` | `Все мои таски` | `Все мои задачи` |
| `dashboard.html` | `Таски на сегодня` | `Задачи на сегодня` |
| `dashboard.html` | `Просроченные таски` | `Просроченные задачи` |

**Правило русификации:** пройтись по всем 29 шаблонам, проверить что весь видимый текст — на русском. Заменить английские слова на русские, кроме спецобозначений (ИНН, КП, БИК, PDF, .docx, ID).

Примеры проверок:
- `placeholder="..."` — русский
- Кнопки — русский
- Empty states — русский
- Tooltip-тексты — русский

## Anti-conflict

**НЕ ТРОГАТЬ:**
- `app/auth.py`, `app/database.py`
- `app/services/funnel_service.py`, `document_service.py`, `report_service.py`, `import_service.py`, `phone_parser.py`
- Существующие роуты (auth, dashboard, leads, tasks, deals, documents, reports) — без изменений
- `Екатерина.xlsx`, `_Вероника.xlsx`, `.planning/`

**Создавать:**
- `app/routes/agent.py`
- `app/services/hermes_service.py`
- `app/templates/agent_chat.html`
- `app/templates/partials/agent_message_pair.html`

## Готово, когда

- [ ] D-01..D-18 — все выполнены
- [ ] `grep -ri 'таск' app/templates/` → 0 результатов
- [ ] `GET /agent` → 200, чат рендерится
- [ ] `POST /agent/send` → 200, partial возвращается (с сообщением об ошибке, т.к. Hermes локально не запущен)
- [ ] Sidebar: «Задачи» (не «Таски»), «Чат с агентом»
- [ ] httpx в requirements.txt
- [ ] Сервер запускается, функциональность не сломана

## Не готово, когда

- «Таски» где-то осталось
- /agent падает с 500
- POST /agent/send падает при недоступном Hermes (нет graceful degradation)
- agent_chat.html не соответствует Visual Canon
- Канбан/карточка лида/документы сломались
