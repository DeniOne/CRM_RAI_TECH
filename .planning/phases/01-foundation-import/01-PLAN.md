---
phase: 1-foundation-import
plan: "01"
slice: 1-01
type: execute
wave: 1
depends_on: []
requirements:
  - CRM-1-01
autonomous: true
files_modified: []
files_created:
  - requirements.txt
  - run.py
  - app/__init__.py
  - app/config.py
  - app/database.py
  - app/models.py
  - app/schemas.py
  - app/auth.py
  - app/main.py
  - app/routes/__init__.py
  - app/routes/auth.py
  - app/routes/dashboard.py
  - app/templates/base.html
  - app/templates/login.html
  - app/templates/dashboard.html
  - app/static/css/app.css
  - app/services/__init__.py
  - app/services/import_service.py
  - app/services/phone_parser.py
  - scripts/import_xlsx.py
must_haves:
  truths:
    - "D-01: requirements.txt существует и содержит все зависимости из списка ниже"
    - "D-02: app/models.py определяет 10 ORM-моделей: User, Region, Lead, StageHistory, Contact, ContactLog, Comment, Task, Deal, Document, DocumentTemplate — со связями и enum-типами"
    - "D-03: app/database.py создаёт async SQLAlchemy engine на sqlite+aiosqlite, БД-файл в storage/crm.db"
    - "D-04: app/auth.py реализует сессионную аутентификацию (cookie-based через itsdangerous), зависимости get_current_user / require_role, хеширование паролей через passlib[bcrypt]"
    - "D-05: При первом запуске (через init_db в main.py lifespan) создаётся admin-аккаунт: email=admin@crm.local, пароль=admin, role=admin, is_active=True"
    - "D-06: GET /login отдаёт форму логина; POST /login — аутентификация; GET /logout — выход"
    - "D-07: GET / (dashboard) требует аутентификации, отдаёт HTML с счётчиками: всего лидов, по стадиям (0..7 + lost), по регионам, по уровням (A/B/C)"
    - "D-08: app/services/phone_parser.py содержит функцию parse_phones(raw: str) -> list[dict], разделяющую строку с несколькими номерами через ';' на отдельные контакты с извлечением имени/должности из текста"
    - "D-09: app/services/import_service.py содержит async-функцию import_xlsx(path, session), выполняющую: маппинг колонок, нормализацию приоритетов, парсинг телефонов, миграцию календаря звонков, определение стадии, создание Region/Lead/Contact/ContactLog записей"
    - "D-10: scripts/import_xlsx.py — standalone-скрипт: инициализирует БД, вызывает import_xlsx с путём к Екатерина.xlsx, печатает отчёт (создано регионов/лидов/контактов/записей журнала)"
    - "D-11: После импорта в БД: 13 регионов, ~290 лидов, ~600+ контактов, ~400+ записей ContactLog"
    - "D-12: uvicorn запускается через run.py на 127.0.0.1:8000, Swagger UI доступен на /docs"
  artifacts:
    - path: app/models.py
      provides: "Полная ORM-схема CRM (10 сущностей)"
    - path: scripts/import_xlsx.py
      provides: "Импорт данных из xlsx в БД с нормализацией"
    - path: app/templates/dashboard.html
      provides: "Базовый дашборд со счётчиками воронки"
  key_links:
    - from: app/main.py
      to: app/database.py
      via: "lifespan → init_db"
      pattern: "FastAPI startup"
    - from: app/routes/dashboard.py
      to: app/models.py
      via: "selectinload / select"
      pattern: "SQLAlchemy async query"
    - from: scripts/import_xlsx.py
      to: app/services/import_service.py
      via: "import_xlsx(path, session)"
      pattern: "service call"
---

# Plan 1-01 — Фундамент CRM + импорт данных (Wave 1)

**Phase:** 1 — foundation-import
**Wave:** B-1
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

Проект CRM_RAI стартует с нуля. Есть Excel-файл `Екатерина.xlsx` (~290 лидов, 13 листов по регионам) — это рабочая база менеджера по продажам препарата для рапса. Файл проанализирован техлидом:

- 12 региональных листов + 1 лист «Не звонить» (чёрный список)
- Колонки названы по-разному на разных листах (15 вариантов приоритета, разные имена колонок)
- Поле «Телефоны» содержит несколько номеров через `;` с примечаниями
- Дневные колонки (2026-07-06 … 07-31) — журнал звонков в формате «одна колонка = одна дата»

Цель фазы: создать фундамент приложения (модели, БД, аутентификация, базовый UI), импортировать все данные из xlsx в БД с нормализацией, и показать дашборд со счётчиками воронки.

## Стек

- **Backend:** FastAPI + SQLAlchemy 2.0 (async) + aiosqlite
- **Frontend:** Jinja2 + HTMX + Tailwind CSS (CDN)
- **БД:** SQLite (storage/crm.db)
- **Аутентификация:** сессионная (cookie-based, itsdangerous), passlib[bcrypt]
- **Импорт:** pandas + openpyxl (уже установлены)

## Что делает кодер (пофайлово)

### 1. `requirements.txt` (новый)

Зависимости (всё уже установлено в окружении, файл для воспроизводимости):
```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
aiosqlite
alembic
pydantic
pydantic-settings
python-multipart
jinja2
python-docx
openpyxl
pandas
passlib[bcrypt]
itsdangerous
```

### 2. `app/config.py` (новый) — конфигурация

Pydantic Settings:
- `DATABASE_URL` = `"sqlite+aiosqlite:///./storage/crm.db"`
- `SECRET_KEY` = `"dev-secret-change-in-production"` (дефолт, для прода — env var)
- `ADMIN_EMAIL` = `"admin@crm.local"`
- `ADMIN_PASSWORD` = `"admin"`
- Пути: `STORAGE_DIR`, `TEMPLATES_DIR`, `STATIC_DIR`, `DOCX_TEMPLATES_DIR`

### 3. `app/database.py` (новый) — async SQLAlchemy

- `async_engine` = `create_async_engine(DATABASE_URL)`
- `async_session_maker` = `async_sessionmaker(async_engine)`
- `Base` = `DeclarativeBase`
- `async def get_session() -> AsyncSession` — зависимость FastAPI
- `async def init_db()` — `Base.metadata.create_all` + вызов `create_default_admin()`

### 4. `app/models.py` (новый) — 10 ORM-моделей

Все модели наследуются от `Base`. Использовать `Mapped[]` + `mapped_column()` (SQLAlchemy 2.0 style).

#### 4.1. User
```python
id: int (PK, autoincrement)
email: str (unique, indexed)
password_hash: str
full_name: str
role: EnumStr ("manager" | "supervisor" | "admin")  # SQLAlchemy Enum
is_active: bool (default True)
created_at: datetime (server_default=func.now())
```

#### 4.2. Region
```python
id: int (PK)
name: str (unique, indexed)
created_at: datetime
# relationship: leads
```

#### 4.3. Lead — центральная сущность
```python
id: int (PK)
region_id: int (FK -> region.id, nullable=True)
assigned_manager_id: int (FK -> user.id, nullable=True)

# Реквизиты
name: str (indexed)
district: str (nullable)
settlement: str (nullable)
address: str (nullable)
inn: str (nullable)
head_name: str (nullable)
site: str (nullable)

# Рапс
rapeseed_info: str (nullable, Text)        # "Рапс/основание" из xlsx
rapeseed_verified: bool (default False)    # подтверждено менеджером
rapeseed_volume: str (nullable)            # тонн/га
harvest_timing: str (nullable)             # когда уборка

# Воронка
level: str (nullable)                      # "A" | "B" | "C"
priority: int (nullable)                   # 1 | 2 | 3 (нормализованное)
stage: str (default "0")                   # "0".."7" | "lost"
stage_changed_at: datetime (server_default=func.now())
loss_reason: str (nullable, Text)

# Заметки
general_comment: str (nullable, Text)      # "Комментарий для CRM"
done_summary: str (nullable, Text)         # "Что сделано"
todo_summary: str (nullable, Text)         # "Что нужно сделать"

created_at: datetime
updated_at: datetime (onupdate=func.now())

# relationships: region, assigned_manager, contacts, contact_logs, comments, tasks, deals
```

#### 4.4. StageHistory
```python
id: int (PK)
lead_id: int (FK -> lead.id)
from_stage: str (nullable)
to_stage: str
changed_by: int (FK -> user.id, nullable)
changed_at: datetime (server_default=func.now())
note: str (nullable, Text)
```

#### 4.5. Contact
```python
id: int (PK)
lead_id: int (FK -> lead.id)
name: str (nullable)
position: str (nullable)
phone: str
email: str (nullable)
is_decision_maker: bool (default False)    # ЛПР
note: str (nullable, Text)
```

#### 4.6. ContactLog
```python
id: int (PK)
lead_id: int (FK -> lead.id)
user_id: int (FK -> user.id, nullable)
contact_type: str (default "call")         # "call" | "email" | "visit"
contact_date: datetime
result: str (Text)                          # текст из ячейки xlsx
outcome: str (nullable)                     # "no_answer" | "busy" | "callback" | "agreed" | "refused" | "sent_kp"
next_action_date: date (nullable)
created_at: datetime
```

#### 4.7. Comment
```python
id: int (PK)
lead_id: int (FK -> lead.id)
user_id: int (FK -> user.id)
body: str (Text)
created_at: datetime
updated_at: datetime (onupdate=func.now())
```

#### 4.8. Task
```python
id: int (PK)
lead_id: int (FK -> lead.id, nullable)
assigned_to: int (FK -> user.id)
created_by: int (FK -> user.id, nullable)
title: str
description: str (nullable, Text)
due_date: datetime (nullable)
priority: int (default 2)                  # 1=высокий, 2=средний, 3=низкий
status: str (default "pending")            # "pending" | "in_progress" | "done" | "cancelled"
completed_at: datetime (nullable)
created_at: datetime
```

#### 4.9. Deal
```python
id: int (PK)
lead_id: int (FK -> lead.id)
user_id: int (FK -> user.id)
title: str
amount: float (nullable)
status: str (default "new")                # "new" | "kp_sent" | "negotiation" | "contract" | "invoiced" | "paid" | "lost"
created_at: datetime
closed_at: datetime (nullable)
```

#### 4.10. Document
```python
id: int (PK)
deal_id: int (FK -> deal.id, nullable)
lead_id: int (FK -> lead.id)
user_id: int (FK -> user.id)
doc_type: str                              # "kp" | "contract" | "invoice" | "act"
template_id: int (FK -> document_template.id, nullable)
title: str
number: str (nullable)
amount: float (nullable)
file_path: str (nullable)                  # .docx
file_path_pdf: str (nullable)              # .pdf
status: str (default "draft")              # "draft" | "sent" | "viewed" | "accepted" | "rejected"
sent_at: datetime (nullable)
created_at: datetime
updated_at: datetime (onupdate=func.now())
```

#### 4.11. DocumentTemplate
```python
id: int (PK)
name: str
doc_type: str                              # "kp" | "contract" | "invoice" | "act"
file_path: str
placeholders: str (nullable, Text)         # JSON-строка
is_active: bool (default True)
created_at: datetime
```

### 5. `app/auth.py` (новый) — аутентификация

- `pwd_context = CryptContext(schemes=["bcrypt"])`
- `def hash_password(pw) -> str`
- `def verify_password(plain, hashed) -> bool`
- `async def authenticate_user(session, email, password) -> User | None`
- `async def create_default_admin(session)` — создаёт admin@crm.local / admin если нет юзеров
- `oauth2_scheme` или свой cookie-механизм:
  - `async def get_current_user(request: Request, session) -> User` — читает session-cookie, возвращает User или редирект на /login
  - `def require_role(*roles)` — зависимость-фабрика, проверяет `current_user.role in roles`
- Cookie: `session` = signed (itsdangerous URLSafeTimedSerializer) JSON `{"user_id": id}`, `httponly=True`, `max_age=86400`
- Функции `set_session(response, user_id)` и `clear_session(response)`

### 6. `app/main.py` (новый) — FastAPI app

- Создание `app = FastAPI(title="CRM RAI")`
- `lifespan` context manager: `init_db()` при старте
- Подключение `app.mount("/static", ...)` для статики
- Jinja2Templates
- Подключение роутеров: `auth.router`, `dashboard.router`
- Middleware: редирект на /login если не аутентифицирован (кроме /login, /static, /docs)

### 7. `app/routes/auth.py` (новый)

- `GET /login` — форма логина (HTML)
- `POST /login` — проверка email+password, set cookie, редирект на /
- `GET /logout` — clear cookie, редирект на /login

### 8. `app/routes/dashboard.py` (новый)

- `GET /` — dashboard:
  - Запрос: count leads по stage, по region (с join), по level
  - Передача в шаблон: `total_leads`, `by_stage` (dict stage→count), `by_region` (list of {name, total}), `by_level` (dict A/B/C→count), `current_user`
  - Рендер `dashboard.html`

### 9. `app/templates/base.html` (новый)

Базовый layout:
- `<head>`: Tailwind CSS (CDN), HTMX (CDN), кастомный `app.css`
- `<body>`: sidebar (навигация: Дашборд, Лиды, Импорт — ссылки заглушки), main content block
- Блок `{% block content %}{% endblock %}`
- Sidebar виден только аутентифицированным (проверка `current_user`)

### 10. `app/templates/login.html` (новый)

Простая форма: email, password, кнопка «Войти». Tailwind-стилизация, центрирование.

### 11. `app/templates/dashboard.html` (новый)

- Заголовок: «CRM RAI — Дашборд»
- Карточки-счётчики (grid, Tailwind):
  - Всего лидов
  - По стадиям воронки (8 карточек: Сырые, В работе, Квалифиц., КП отправ., Переговоры, Договор, Счёт, Оплачено + Потерян)
  - По регионам (таблица: регион → кол-во лидов)
  - По уровням (A / B / C)

### 12. `app/static/css/app.css` (новый)

Минимальные кастомные стили поверх Tailwind (если нужны).

### 13. `app/services/phone_parser.py` (новый) — парсинг телефонов

```python
def parse_phones(raw: str) -> list[dict]:
    """
    Разбирает поле 'Телефоны' из xlsx на отдельные контакты.
    
    Вход: '8(800)350-74-85; 7 (8112) 75-34-42; отд.закупок- 72-41-80 ольга ивановна, жанна'
    Выход: [
        {"phone": "8(800)350-74-85", "name": None, "position": None, "note": None},
        {"phone": "7 (8112) 75-34-42", "name": None, "position": None, "note": None},
        {"phone": "72-41-80", "name": "ольга ивановна", "position": "отд.закупок", "note": "жанна"},
    ]
    """
```

Логика:
1. Разделение по `;` и переносу строки
2. В каждом фрагменте: извлечение номера (regex для телефонных паттернов)
3. Извлечение имени (ищем ФИО — слова с заглавной, не номер)
4. Извлечение должности ("отд.закупок", "гл.агроном", "приемная", "секретарь" и т.д. — список ключевых слов)
5. Остаток → note
6. Пустые фрагменты пропускаем

### 14. `app/services/import_service.py` (новый) — импорт xlsx

Главная async-функция:

```python
async def import_xlsx(path: str, session: AsyncSession) -> dict:
    """
    Импортирует xlsx в БД. Возвращает отчёт:
    {"regions": N, "leads": N, "contacts": N, "contact_logs": N}
    """
```

**Алгоритм:**

1. **Открыть xlsx** через `pd.ExcelFile(path)`

2. **Маппинг колонок** — для каждого листа сопоставить вариации названий:
   ```python
   COLUMN_MAP = {
       "name": ["Название компании", "Название"],
       "district": ["Район"],
       "settlement": ["Нас. пункт"],
       "address": ["Адрес"],
       "inn": ["ИНН"],
       "head_name": ["Руководитель"],
       "phones_raw": ["Телефоны", "Телефон"],
       "email": ["Email"],
       "site": ["Сайт / Холдинг", "Сайт/Холдинг", "Сайт", "Профиль"],
       "rapeseed_info": ["Рапс / основание", "Рапс - основание", "Рапс/основание"],
       "level": ["Уровень"],
       "priority": ["Приоритет"],
       "general_comment": ["Комментарий для CRM", "Комментарий для CR"],  # обрезано в xlsx
       "done_summary": ["Что сделано"],
       "todo_summary": ["Что нужно сделать"],
   }
   ```
   Для каждого листа: прочитать заголовки, смаппить по COLUMN_MAP.

3. **Нормализация региона** — имя листа → очистить от номеров/восклицательных:
   - `"Псковская область 8!"` → `"Псковская область"`
   - `"Челябенская+2  2!"` → `"Челябенская+2"` (или `"Челябинская обл."` — на усмотрение кодера, главное без trailing номера и `!`)
   - `"Не звонить"` → `"Не звонить"` (особый лист)
   - Создать Region если не существует

4. **Нормализация приоритета** — 15 вариантов → 3:
   ```python
   def normalize_priority(raw):
       if not raw or pd.isna(raw): return None
       s = str(raw).strip().lower()
       if any(x in s for x in ["1", "высок", "первая", "1-я", "1 очередь", "1-я очередь"]): return 1
       if any(x in s for x in ["2", "средн", "вторая", "2-я", "2 очередь", "2-я очередь"]): return 2
       if any(x in s for x in ["3", "низк", "трет", "3-я", "3 очередь", "3-я очередь"]): return 3
       return None  # "Инфо", "—", и пр.
   ```
   ⚠ Внимание: "1" содержится в "13", "1-я очередь" и т.д. — проверять от длинных к коротким или использовать regex `^[123]\b`.

5. **Парсинг телефонов** — `parse_phones(raw)` → список контактов → создать Contact-записи

6. **Миграция календаря звонков** — дата-колонки (datetime-заголовки с year attr):
   - Для каждой строки: перебрать дата-колонки, если ячейка непустая → создать ContactLog:
     - `contact_date` = значение заголовка-даты
     - `result` = текст ячейки
     - `outcome` = `classify_outcome(text)` — поиск ключевых слов:
       ```python
       OUTCOME_KEYWORDS = {
           "sent_kp": ["кп", "коммерческ", "предложен"],
           "busy": ["сброс", "занят"],
           "no_answer": ["не дозвон", "нет ответ", "недоступ", "не отвеч"],
           "agreed": ["соглас", "договорил", "возьм", "заказ"],
           "refused": ["отказ", "не нужн", "не интерес", "ликвидир"],
           "callback": ["перезв", "перезван", "набрать", "звонить"],
       }
       ```

7. **Определение стадии** — по последним записям ContactLog:
   ```python
   def determine_stage(contact_logs):
       if not contact_logs: return "0"
       last = contact_logs[-1]  # по дате
       outcomes = [log.outcome for log in contact_logs]
       results_text = " ".join(log.result for log in contact_logs).lower()
       if "sent_kp" in outcomes or "кп" in results_text: return "3"
       if "agreed" in outcomes or "соглас" in results_text: return "4"
       if any(o in outcomes for o in ["busy", "no_answer", "callback"]): return "1"
       return "1"
   ```

8. **Лист "Не звонить"** — все лиды: `stage="lost"`, `loss_reason="Чёрный список (из xlsx)"`

9. **Создание записей** — для каждой строки:
   - Найти или создать Region
   - Создать Lead (stage из п.7)
   - Создать Contact-записи (из п.5)
   - Создать ContactLog-записи (из п.6)
   - `session.flush()` периодически (каждые 50 лидов) для памяти

10. **Возврат отчёта**: `{"regions": N, "leads": N, "contacts": N, "contact_logs": N}`

### 15. `scripts/import_xlsx.py` (новый) — standalone-импорт

```python
import asyncio
from app.database import init_db, async_session_maker
from app.services.import_service import import_xlsx

async def main():
    await init_db()
    async with async_session_maker() as session:
        report = await import_xlsx("Екатерина.xlsx", session)
        await session.commit()
    print(f"Импорт завершён: {report}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 16. `run.py` (новый) — точка входа

```python
import uvicorn
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
```

### 17. `app/routes/__init__.py`, `app/services/__init__.py` (новые) — пустые `__init__.py`

## Anti-conflict (важно для кодера)

**НЕ ТРОГАТЬ:**
- `Екатерина.xlsx` — исходный файл, только чтение
- `.planning/` — артефакты техлида (PLAN, README-CONTRACT)
- Ничего вне директорий `app/`, `scripts/`, `storage/`, `templates_docx/`, корневых конфигов

**Создавать директории:**
- `app/routes/`
- `app/services/`
- `app/templates/`
- `app/static/css/`
- `storage/documents/`
- `templates_docx/`

## Готово, когда (success criteria)

- [ ] D-01..D-12 (см. must_haves.truths) — все выполнены
- [ ] `python run.py` запускает сервер на 127.0.0.1:8000 без ошибок
- [ ] `http://127.0.0.1:8000/docs` — Swagger UI доступен
- [ ] `http://127.0.0.1:8000/login` — форма логина отображается
- [ ] Логин `admin@crm.local` / `admin` → редирект на дашборд
- [ ] `python scripts/import_xlsx.py` — импорт проходит без ошибок, печатает отчёт с ~290 лидами
- [ ] Дашборд показывает: 13 регионов, ~290 лидов, разбивку по стадиям/уровням
- [ ] Нет `console.log` / `print` отладочного мусора (только в import скрипте)

## Не готово, когда

- Сервер не запускается (import error, синтаксис)
- Импорт падает с ошибкой или создаёт <250 лидов (данные потеряны)
- Дашборд пустой или показывает 0 лидов после импорта
- Логин не работает (admin не создаётся при первом запуске)
- Нормализация приоритетов сломана (все → None или все → 1)
- Телефоны не распарсены (все в одном поле, нет отдельных Contact-записей)

## Что даёт эта фаза

Фундамент приложения: работающий FastAPI-сервер с аутентификацией, полная ORM-схема CRM (10 сущностей), и все 290 лидов из Excel импортированы в БД с нормализацией. Дашборд показывает сводку воронки. База для Фазы 2 (канбан, карточка лида, журнал контактов).

## Следующий шаг

Фаза 2 — Канбан и работа менеджера: drag-and-drop доска по стадиям, карточка лида (HTMX-модалка), журнал контактов, комментарии, таски. Строится на моделях и данных из Фазы 1.
