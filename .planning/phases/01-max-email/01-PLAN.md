# PLAN 01 — Каналы коммуникации: MAX Messenger (бот) + Email (SMTP)

> **Проект:** CRM_RAI (`/srv/crm-rai/`)
> **Стек:** FastAPI + SQLAlchemy (async) + SQLite + Jinja2 + Docker
> **Решение Owner:** верифицированный бот MAX (один на компанию) + email через SMTP reg.ru как фолбэк.

---

## Контекст и архитектурное решение

### Что выяснилось про MAX

MAX (VK) **не предоставляет API для личных аккаунтов** — нельзя программно
войти в аккаунт менеджера и писать клиентам «как человек». Это намеренная
политика всех мессенджеров (анти-спам). Официальные пути:

| Путь | Легальность | Цена | Для клиента выглядит как |
|------|-------------|------|--------------------------|
| **Верифицированный бот** ✅ выбор | легально | бесплатно | «RAI Technology ✓» (галочка, логотип) |
| Агрегатор (Umnico) | легально | ~$45+$7/мес | переписка с аккаунтом менеджера |
| Неофициальное API | бан-риск | бесплатно | переписка с аккаунтом менеджера |

**Решение Owner:** верифицированный бот. Один бот на компанию (не на каждого
менеджера), после верификации через Госуслуги получает имя фирмы + галочку.

### Бизнес-процесс (как это работает для агронома)

1. Менеджер звонит/встречается с агрономом, говорит «у нас есть MAX»
2. Менеджер даёт агроному ссылку на бота (или QR) — в CRM кнопка «Поделиться контактом»
3. Агроном открывает MAX, пишет боту (хотя бы «/start» или любой текст)
4. CRM связывает агронома с лидом (по телефону или вручную)
5. Дальше менеджер переписывается из CRM, агроном — в MAX
6. **Фолбэк:** если агроном не в MAX — менеджер шлёт документ на email

### Архитектура

```
          MAX Bot API (platform-api2.max.ru)            SMTP reg.ru
                 │                                         │
      webhook ───┤                                send ────┤
      (входящие) │                                (исход.) │
                 ▼                                         ▼
    ┌──────────────────────────────────────────────────────────┐
    │                   CRM RAI (FastAPI)                       │
    │                                                           │
    │  /max/webhook       ← MAX шлёт входящие (без auth)        │
    │  /messages          ← общий Inbox (все каналы)            │
    │  /leads/{id}/chat   ← вкладка Чат в карточке лида         │
    │  /leads/{id}/email  ← отправка письма (фолбэк)            │
    │                                                           │
    │  max_service.py     ← httpx-обёртка над Bot API           │
    │  email_service.py   ← aiosmtplib + Jinja2                 │
    │  ChannelAccount     ← модель: внеш. пользователь ↔ лид    │
    │  Message            ← модель: единая переписка            │
    └──────────────────────────────────────────────────────────┘
```

**Почему httpx, а не SDK:** MAX Bot API — REST. Сторонние Python-SDK
(`maxapi`, `python-max-bot`) поднимают собственный FastAPI/event-loop,
конфликтуют с приложением CRM. Прямые вызовы через `httpx` (как уже у Hermes
и DaData) — чисто и предсказуемо.

---

## D-критерии (must_haves.truths)

### D-1: Модель данных каналов (`app/models.py`)

**Новая таблица `channel_accounts`** — связь внешнего пользователя с CRM:

```python
class ChannelAccount(Base):
    __tablename__ = "channel_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)

    channel: Mapped[str] = mapped_column(String(20))  # 'max'
    external_user_id: Mapped[str] = mapped_column(String(100), index=True)
    external_chat_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # телефон клиента в MAX, если известен (для автосвязи с лидом)
    phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now())

    lead: Mapped[Optional["Lead"]] = relationship()
    messages: Mapped[List["Message"]] = relationship(
        back_populates="channel_account", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("channel", "external_user_id", name="uq_channel_user"),
    )
```

**Новая таблица `messages`** — единая переписка:

```python
class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel_account_id: Mapped[int] = mapped_column(
        ForeignKey("channel_accounts.id", ondelete="CASCADE"), index=True)

    direction: Mapped[str] = mapped_column(String(3))  # 'in' | 'out'
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attachment_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # путь к локальной копии вложения (для исходящих документов)
    attachment_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    external_message_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True)
    sent_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    read_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    channel_account: Mapped["ChannelAccount"] = relationship(back_populates="messages")
```

**Миграция:** Alembic-миграция `add_channel_and_messages`. Если Alembic не
настроен — auto-create через проверку `Base.metadata.create_all` при старте
(проверить, как сейчас создаются таблицы).

### D-2: MAX Bot API service (`app/services/max_service.py`)

Все функции `async`, через `httpx.AsyncClient`, таймаут 30с.

```python
MAX_API_BASE = settings.MAX_API_BASE_URL  # "https://platform-api2.max.ru"

class MaxApiError(Exception):
    def __init__(self, message, status_code=None):
        self.status_code = status_code
        super().__init__(message)

async def send_text(chat_id: int, text: str) -> dict:
    """POST /messages?access_token=TOKEN  body: {chat_id, text}"""

async def send_file(chat_id: int, file_path: str, caption: str = None) -> dict:
    """Шаг 1: POST /uploads?type=file (multipart) → token_id
       Шаг 2: POST /messages с attachments=[{token: token_id}]"""

async def get_bot_info() -> dict:
    """GET /me?access_token=TOKEN → {bot_id, name, avatar_url}"""

async def register_webhook(webhook_url: str) -> dict:
    """POST /subscriptions  body: {types: [message_created], url: webhook_url}"""

async def delete_webhook() -> None:
    """DELETE /subscriptions?type=message_created"""
```

Токен берётся из `settings.MAX_BOT_TOKEN` (один бот на компанию — из `.env`).

### D-3: Webhook endpoint (`POST /max/webhook`)

- **Без cookie-auth** (MAX не знает наши сессии).
- Верификация: единый секрет в URL — `POST /max/webhook/{secret}`, где
  `secret = settings.MAX_WEBHOOK_SECRET`. Несовпадение → 403.
- Тело callback: `{"message": {...}, "chat": {...}, "user": {...}}`
- Алгоритм обработки входящего:
  1. Найти `ChannelAccount` по `(channel='max', external_user_id)`.
     Если нет — создать. `display_name` = из профиля пользователя MAX.
  2. **Автосвязь с лидом:** если в сообщении есть `phone` (контакт отправлен
     через request_contact) — найти `Contact` по телефону → `lead_id`.
     Если телефона нет — оставить `lead_id=None` (менеджер привяжет вручную
     в Inbox).
  3. Создать `Message(direction='in', ...)`.
  4. Вернуть `200 {"ok": True}` **быстро** (MAX повторяет при таймауте > 5с).
- Дедупликация по `external_message_id`: если уже есть — вернуть 200 без дубля.

### D-4: Исходящие эндпоинты (`app/routes/messages.py`)

```python
@router.post("/leads/{lead_id}/max/send")
# Тело: {text: str}
# Требует: у лида есть привязанный ChannelAccount.
# Если нет — 400: "Клиент ещё не написал боту. Поделитесь ссылкой."
# Создаёт Message(direction='out', sent_by=user), вызывает send_text().

@router.post("/leads/{lead_id}/max/send-document/{doc_id}")
# Берёт Document.file_path_pdf (предпочтительно) или file_path.
# Загружает через send_file(). Caption: «Документ: {doc.title}».
# Обновляет Document.sent_at, Document.status='sent'.
# Создаёт Message(direction='out', attachment_name=doc.title).

@router.get("/leads/{lead_id}/max/messages")
# Возвращает JSON: список сообщений ChannelAccount лида (для AJAX-поллинга).
```

### D-5: UI — вкладка «Чат» в карточке лида

В `lead_card.html` добавить вкладку после «Сделки»:

```html
<button class="tab-btn ..." data-tab="chat" onclick="switchTab('chat')">
  Чат
</button>
<div id="tab-chat" class="tab-content hidden">
  {% include "partials/chat_widget.html" %}
</div>
```

`partials/chat_widget.html`:
- **Если нет ChannelAccount:** плашка
  «Клиент ещё не написал в MAX. [Поделиться ссылкой на бота] [Показать QR]»
  + кнопка «Отправить на email вместо этого» → переход к email-форме.
- **Если есть:** лента сообщений + поле ввода + кнопка «📎 Прикрепить документ».
- Обновление: polling `GET /leads/{id}/max/messages` каждые 15 сек.
- Отправка: `POST /leads/{id}/max/send` (AJAX, без перезагрузки).

### D-6: UI — общий Inbox («Сообщения»)

- `GET /messages` → `messages.html`.
- Слева: список диалогов (по `ChannelAccount`), сортировка по последнему
  сообщению. Бейдж непрочитанных.
- Справа: выбранный диалог — история + поле ввода + «📎 Документ».
- Если `channel_account.lead_id` — ссылка «↗ Открыть лид».
- Привязка неподключённого диалога к лиду: dropdown выбора лида
  (`POST /messages/{ca_id}/link-lead`).

### D-7: Email — SMTP service (`app/services/email_service.py`)

Добавить `aiosmtplib` + `email-validator` в `requirements.txt`.

```python
async def send_email(
    to: str, subject: str, html_body: str,
    attachments: list[str] = None,  # пути к файлам
) -> dict:
    """Отправляет письмо через SMTP reg.ru.
    Возвращает {success: bool, error: str|None}."""
    # SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_USE_SSL из settings
```

Шаблон письма — простой Jinja2 `email_base.html` (HTML + inline-стили).

### D-8: Email endpoints

```python
@router.post("/leads/{lead_id}/email/send")
# Поля: to (по умолчанию = первый Contact.email лида), subject, body,
#       attachment_ids: list[int] (ID документов)
# Отправляет через email_service.send_email().
# Создаёт ContactLog(type='email', result=body) — фиксация в Журнале.
# Для каждого вложенного документа — обновить Document.sent_at.

@router.get("/leads/{lead_id}/email/compose")
# Возвращает partial email_compose.html (HTMX-modal): форма письма.
```

### D-9: UI — кнопка «Отправить письмо»

В карточке лида (вкладка «Документы»):
- У каждого документа — кнопка «✉️ Отправить по email»
- Открывает HTMX-modal `email_compose.html` с предзаполненным вложением.
- После отправки — toast «Письмо отправлено» + запись в Журнале.

### D-10: Config (`app/config.py`)

```python
# MAX
MAX_API_BASE_URL: str = "https://platform-api2.max.ru"
MAX_BOT_TOKEN: str = ""
MAX_WEBHOOK_SECRET: str = ""  # случайная строка для верификации webhook

# SMTP
SMTP_HOST: str = ""
SMTP_PORT: int = 465
SMTP_USER: str = ""
SMTP_PASSWORD: str = ""
SMTP_USE_SSL: bool = True
SMTP_FROM_NAME: str = "RAI Technology"
```

---

## Success criteria

### MAX
- ✅ Входящее сообщение от агронома появляется в CRM (вкладка Чат + Inbox)
- ✅ Ответ менеджера из CRM доходит до агронома в MAX
- ✅ Документ из CRM отправляется в MAX как файл
- ✅ Непривязанный диалог можно привязать к лиду вручную
- ✅ Дубли не создаются (дедупликация по external_message_id)

### Email
- ✅ Письмо из CRM доходит до email агронома
- ✅ Можно прикрепить PDF-документ
- ✅ Отправка фиксируется в Журнале (ContactLog)
- ✅ Ошибка SMTP показывается менеджеру (не молча)

## Не готово, когда
- ❌ Webhook возвращает не-200 и MAX спамит повторами
- ❌ Входящее сообщение теряется
- ❌ Нельзя ответить из CRM (нет endpoint/UI)
- ❌ Email тихо падает без сообщения менеджеру

## Anti-conflict (НЕ трогать)
- Существующие роуты — только ДОБАВЛЯТЬ новые
- `hermes_service.py` — отдельная зона
- `ContactLog` — не менять структуру, только добавлять записи (type='email')
- `lead_card.html` — не перестраивать, только добавить вкладку «Чат»
- Базу не пересоздавать — миграция должна сохранить данные

## Файлы для создания/изменения

**Создать:**
- `app/services/max_service.py`
- `app/services/email_service.py`
- `app/routes/messages.py` (роутер: MAX webhook + send + inbox + email)
- `app/templates/messages.html` (Inbox)
- `app/templates/partials/chat_widget.html`
- `app/templates/partials/chat_message.html`
- `app/templates/partials/email_compose.html`
- `app/templates/email_base.html` (HTML-шаблон письма)
- `app/static/js/chat.js` (polling + отправка)

**Изменить:**
- `app/models.py` — ChannelAccount, Message
- `app/config.py` — MAX_* + SMTP_* настройки
- `app/main.py` — подключить роутер messages
- `app/templates/lead_card.html` — вкладка «Чат»
- `app/templates/base.html` — пункт «Сообщения» + бейдж
- `app/templates/partials/documents_list.html` — кнопка «✉️ email»
- `requirements.txt` — aiosmtplib, email-validator

---

## Что нужно от Owner ДО старта кодера

| # | Действие | Где | Подробно |
|---|----------|-----|----------|
| 1 | Зарегистрировать профиль организации на `business.max.ru` | MAX app / web | Войти по номеру телефона → верификация через Госуслуги |
| 2 | Создать бота, получить BOT_TOKEN | `business.max.ru` → бот | Имя: «RAI Technology» |
| 3 | (опционально) Пройти верификацию для галочки ✓ | чат «Поддержка MAX для бизнеса» | Нужен ИНН организации/ИП |
| 4 | Записать BOT_TOKEN и придумать WEBHOOK_SECRET | `.env` на сервере | Я помогу |
| 5 | Создать mailbox на reg.ru (или mail.ru для домена) | панель reg.ru | Например manager@raitechnology.online |
| 6 | Получить пароль приложений SMTP | настройки ящика | Записать в `.env` |
