# CRM RAI — Техническая документация

**Версия:** 1.0 (Фазы 1–6)
**Дата:** 11 июля 2026
**Репозиторий:** https://github.com/DeniOne/CRM_RAI_TECH.git

---

## Оглавление

1. [Архитектура](#1-архитектура)
2. [Стек технологий](#2-стек-технологий)
3. [Структура проекта](#3-структура-проекта)
4. [Модель данных](#4-модель-данных)
5. [Роуты (API)](#5-роуты-api)
6. [Сервисы](#6-сервисы)
7. [Воронка продаж — правила](#7-воронка-продаж--правила)
8. [Hermes AI-интеграция](#8-hermes-ai-интеграция)
9. [MCP-сервер](#9-mcp-сервер)
10. [Деплой](#10-деплой)
11. [Обслуживание](#11-обслуживание)
12. [Visual Canon](#12-visual-canon)

---

## 1. Архитектура

```
rai-dev (161.35.89.51)
│
├── Hermes Gateway :8080
│   ├── OpenAI-совместимый API (/v1/chat/completions)
│   ├── MCP-подключение к CRM (crm-rai-tech)
│   └── AI Agent (модель, инструменты, память)
│
├── CRM RAI (Docker, network_mode: host) :8000
│   ├── FastAPI + uvicorn
│   ├── SQLite (storage/crm.db, WAL mode)
│   ├── Jinja2 + HTMX + Tailwind CSS (CDN)
│   ├── httpx → Hermes :8080/v1/chat/completions
│   └── python-docx + docx2pdf (генерация документов)
│
└── Данные:
    ├── /srv/crm-rai/storage/crm.db
    ├── /srv/crm-rai/storage/documents/
    └── /srv/crm-rai/templates_docx/
```

### Поток данных

```
Браузер ──HTTP/HTMX──► FastAPI (:8000)
                            │
                            ├── SQLite (storage/crm.db)
                            │
                            └── Чат агента ──httpx──► Hermes (:8080)
                                                          │
                                                          └── MCP stdio ──► mcp_server.py
                                                                                │
                                                                                └── SQLite (read/write)
```

---

## 2. Стек технологий

| Слой | Технология | Версия |
|---|---|---|
| **Backend** | FastAPI | 0.139 |
| **Сервер** | uvicorn[standard] | 0.51 |
| **ORM** | SQLAlchemy 2.0 (async) | 2.0.51 |
| **БД** | SQLite + aiosqlite | — |
| **Миграции** | Alembic | 1.18 (установлен, схема через create_all) |
| **Валидация** | Pydantic + pydantic-settings | 2.13 / 2.14 |
| **Frontend** | Jinja2 + HTMX 1.9.10 + Tailwind CSS (CDN) | — |
| **Drag-and-drop** | SortableJS 1.15.0 | — |
| **Шрифты** | Geist Sans + Geist Mono (CDN) | — |
| **Документы** | python-docx + docx2pdf (Word COM) | 1.2 / 0.1.8 |
| **Импорт** | pandas + openpyxl | 3.0 / 3.1 |
| **AI-клиент** | httpx (async) | 0.28 |
| **Аутентификация** | itsdangerous (signed cookie) + pbkdf2_hmac | — |
| **Контейнер** | Docker (python:3.11-slim) | — |

---

## 3. Структура проекта

```
CRM_RAI/
├── app/
│   ├── main.py                  # FastAPI app, middleware, lifespan, роутеры
│   ├── config.py                # Pydantic Settings (БД, Hermes, admin)
│   ├── database.py              # async engine, sessionmaker, Base, init_db
│   ├── auth.py                  # Cookie-сессии, hash_password, get_current_user
│   ├── models.py                # 11 ORM-моделей
│   ├── schemas.py               # Pydantic-схемы (частично используются)
│   ├── routes/
│   │   ├── auth.py              # /login, /logout
│   │   ├── dashboard.py         # / (роль-зависимый дашборд)
│   │   ├── leads.py             # /kanban, /leads/{id}, edit, contacts, stage, assign
│   │   ├── tasks.py             # /tasks, /api/tasks/{id}/status
│   │   ├── deals.py             # /deals, CRUD сделок
│   │   ├── documents.py         # /templates, генерация/скачивание документов
│   │   ├── reports.py           # /reports (воронка, KPI, экспорт)
│   │   └── agent.py             # /agent (чат с Hermes)
│   ├── services/
│   │   ├── funnel_service.py    # STAGES, validate_transition, change_stage
│   │   ├── import_service.py    # Парсинг xlsx, нормализация, импорт в БД
│   │   ├── document_service.py  # .docx плейсхолдеры, генерация, PDF
│   │   ├── phone_parser.py      # Разбор поля "Телефоны"
│   │   ├── report_service.py    # Агрегация воронки, KPI, просадок
│   │   └── hermes_service.py    # HTTP-клиент Hermes (OpenAI format)
│   ├── templates/               # 29 Jinja2 HTML-шаблонов
│   │   ├── base.html            # Layout (sidebar, drawer, шрифты)
│   │   ├── kanban.html          # Канбан-доска
│   │   ├── lead_card.html       # Карточка лида (7 табов)
│   │   ├── agent_chat.html      # AI Dock
│   │   ├── supervisor_dashboard.html
│   │   ├── partials/            # 16 HTMX-фрагментов
│   │   └── ...
│   └── static/
│       ├── css/app.css          # Visual Canon CSS
│       └── js/
│           ├── kanban.js        # SortableJS + HTMX
│           └── drawer.js        # Боковая панель
├── scripts/
│   ├── import_xlsx.py           # Импорт данных
│   ├── export_report.py         # Экспорт отчёта
│   └── cleanup_data.py          # Очистка данных
├── storage/                     # SQLite + documents (volume)
├── templates_docx/              # .docx-шаблоны (volume)
├── .env                         # Переменные окружения
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .gitignore
├── .dockerignore
└── docs/
    ├── CRM_RAI_MANUAL.md        # Руководство пользователя
    └── CRM_RAI_TECH.md          # Этот файл
```

---

## 4. Модель данных

### Сущности (11 таблиц)

#### User
```
id | email (unique) | password_hash | full_name | role (enum) | is_active | created_at
```
- `role`: manager | supervisor | admin

#### Region
```
id | name (unique) | created_at
```

#### Lead — центральная сущность
```
id | region_id (FK) | assigned_manager_id (FK→User)
name | district | settlement | address | inn | head_name | site
rapeseed_info | rapeseed_verified (bool) | rapeseed_volume | harvest_timing
level (A/B/C) | priority (1/2/3) | stage (0..7/lost) | stage_changed_at | loss_reason
general_comment | done_summary | todo_summary
created_at | updated_at
```
- Связи: region, assigned_manager, contacts[], contact_logs[], comments[], tasks[], deals[], documents[]

#### StageHistory
```
id | lead_id (FK) | from_stage | to_stage | changed_by (FK→User) | changed_at | note
```

#### Contact
```
id | lead_id (FK) | name | position | phone | email | is_decision_maker (bool) | note
```

#### ContactLog
```
id | lead_id (FK) | user_id (FK) | contact_type (call/email/visit)
contact_date | result (text) | outcome | next_action_date | created_at
```
- `outcome`: no_answer | busy | callback | agreed | refused | sent_kp

#### Comment
```
id | lead_id (FK) | user_id (FK) | body | created_at | updated_at
```

#### Task
```
id | lead_id (FK, nullable) | assigned_to (FK) | created_by (FK)
title | description | due_date | priority (1/2/3) | status | completed_at | created_at
```
- `status`: pending | in_progress | done | cancelled

#### Deal
```
id | lead_id (FK) | user_id (FK) | title | amount | status | created_at | closed_at
```
- `status`: new | kp_sent | negotiation | contract | invoiced | paid | lost

#### Document
```
id | deal_id (FK, nullable) | lead_id (FK) | user_id (FK)
doc_type (kp/contract/invoice/act) | template_id (FK) | title | number | amount
file_path | file_path_pdf | status | sent_at | created_at | updated_at
```

#### DocumentTemplate
```
id | name | doc_type | file_path | placeholders (JSON) | is_active | created_at
```

#### AgentMessage
```
id | user_id (FK) | role (user/assistant) | content | context_lead_id (FK, nullable)
actions (JSON, nullable) | created_at
```

---

## 5. Роуты (API)

### Аутентификация

| Метод | Путь | Описание |
|---|---|---|
| GET | `/login` | Форма входа |
| POST | `/login` | Аутентификация (email + password) |
| GET | `/logout` | Выход |

### Дашборд

| Метод | Путь | Роль | Описание |
|---|---|---|---|
| GET | `/` | все | Дашборд (manager: личный, supervisor/admin: общий) |

### Канбан и лиды

| Метод | Путь | Описание |
|---|---|---|
| GET | `/kanban` | Канбан-доска (query: manager, region, level, priority) |
| GET | `/leads/{id}` | Карточка лида (7 табов) |
| POST | `/api/leads/{id}/stage` | Смена стадии (JSON `{ok, stage}` или 422) |
| POST | `/leads/{id}/edit` | Редактирование полей (HTMX → partial) |
| POST | `/leads/{id}/assign` | Назначение менеджера (supervisor/admin) |
| POST | `/leads/{id}/contacts` | Добавить контакт (HTMX → partial) |
| POST | `/leads/{id}/contacts/{cid}/toggle-dm` | Переключить ЛПР (HTMX) |
| POST | `/leads/{id}/contact-log` | Запись в журнал + авто-задача (HTMX) |
| POST | `/leads/{id}/comments` | Комментарий (HTMX) |
| GET | `/leads/{id}/contacts/form` | Форма добавления контакта (drawer) |
| GET | `/leads/{id}/contact-log/form` | Форма журнала (drawer) |
| GET | `/leads/{id}/comments/form` | Форма комментария (drawer) |
| GET | `/leads/{id}/deals/form` | Форма сделки (drawer) |

### Задачи

| Метод | Путь | Описание |
|---|---|---|
| GET | `/tasks` | Список задач (query: status) |
| POST | `/api/tasks/{id}/status` | Смена статуса (HTMX → partial) |

### Сделки

| Метод | Путь | Описание |
|---|---|---|
| GET | `/deals` | Список сделок (query: status) |
| POST | `/leads/{id}/deals` | Создать сделку (HTMX → partial) |
| POST | `/deals/{id}/status` | Смена статуса (HTMX → partial) |

### Документы

| Метод | Путь | Описание |
|---|---|---|
| GET | `/templates` | Управление шаблонами |
| POST | `/templates/upload` | Загрузка .docx (UploadFile + name + doc_type) |
| POST | `/templates/{id}/delete` | Soft delete (is_active=False) |
| GET | `/leads/{id}/documents` | Список документов лида (partial) |
| GET | `/templates/{id}/fields` | Доп. поля шаблона (partial) |
| POST | `/leads/{id}/documents/generate` | Генерация документа → .docx + .pdf |
| GET | `/documents/{id}/download` | Скачивание (query: format=docx\|pdf) |
| POST | `/documents/{id}/status` | Смена статуса (HTMX) |

### Аналитика (supervisor/admin)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/reports` | Дашборд аналитики |
| GET | `/reports/funnel` | Воронка по регионам |
| GET | `/reports/managers` | KPI менеджеров (query: date_from, date_to) |
| GET | `/reports/export` | Экспорт в .xlsx (3 листа) |

### AI-агент

| Метод | Путь | Описание |
|---|---|---|
| GET | `/agent` | Чат с агентом (история + форма) |
| POST | `/agent/send` | Отправка сообщения (HTMX → partial) |
| POST | `/agent/clear` | Очистка истории |

---

## 6. Сервисы

### funnel_service.py
- `STAGES` — список кодов стадий `["0".."7", "lost"]`
- `STAGE_LABELS` — русские названия
- `validate_transition(lead, from_stage, to_stage)` → `(bool, list[str])` — проверка ворот
- `change_stage(session, lead_id, to_stage, user_id)` → `Lead` — смена + StageHistory

### import_service.py
- `import_xlsx(path, session)` → `dict` — импорт xlsx в БД
- `normalize_priority(raw)` → `int|None` — 15 вариантов → 3
- `classify_outcome(text)` → `str|None` — ключевые слова → outcome
- `determine_stage(contact_logs)` → `str` — стадия по истории звонков
- `parse_phones(raw)` (в phone_parser.py) — разбор поля "Телефоны"

### document_service.py
- `extract_placeholders(docx_path)` → `list[str]` — парсинг `{placeholder}`
- `generate_document(template, replacements, output)` → `str` — замена (split-run safe)
- `convert_to_pdf(docx, pdf)` → `str|None` — docx2pdf (graceful fallback)
- `DEFAULT_PLACEHOLDERS` — 14 авто-полей из Lead
- `build_replacements(lead, user, extra)` → `dict`

### report_service.py
- `get_funnel_by_region(session)` → `list[dict]`
- `get_funnel_totals(session)` → `dict` (стадии + конверсия)
- `get_manager_kpi(session, date_from, date_to)` → `list[dict]`
- `get_funnel_bottlenecks(session)` → `list[dict]`
- `get_stage_history_stats(session)` → `list[dict]`

### hermes_service.py
- `send_to_hermes(message, user_id, user_name, role, context_lead_id)` → `dict`
- POST `{HERMES_API_URL}/v1/chat/completions` (OpenAI format)
- Graceful degradation: disabled / ConnectError / TimeoutException / generic

---

## 7. Воронка продаж — правила

### Ворота перехода

| Переход | Условие | Сообщение при ошибке |
|---|---|---|
| 0 → 1 | `lead.assigned_manager_id is not None` | «Назначьте менеджера» |
| 1 → 2 | есть Contact с `is_decision_maker=True` AND `lead.rapeseed_verified == True` | «Отметьте ЛПР среди контактов» / «Подтвердите выращивание рапса» |
| * → lost | всегда разрешено | (устанавливается дефолтная причина) |
| остальные | свободный переход | — |

---

## 8. Hermes AI-интеграция

### Архитектура

```
CRM /agent/send
    │
    ├── Сохраняет AgentMessage(role="user")
    │
    ├── httpx.POST → Hermes :8080/v1/chat/completions
    │   {
    │     "model": "hermes-agent",
    │     "messages": [
    │       {"role": "system", "content": "Ты — AI-ассистент CRM RAI..."},
    │       {"role": "user", "content": "сообщение"}
    │     ]
    │   }
    │
    ├── Hermes обрабатывает:
    │   ├── AI-модель генерирует ответ
    │   ├── При необходимости вызывает MCP-инструменты
    │   └── Возвращает OpenAI-совместимый response
    │
    ├── Парсит choices[0].message.content
    │
    └── Сохраняет AgentMessage(role="assistant")
```

### Конфигурация (.env)

```env
HERMES_API_URL=http://localhost:8080
HERMES_API_TOKEN=               # Bearer token (если нужен)
HERMES_TIMEOUT=120              # секунд (AI-генерация может быть долгой)
HERMES_ENABLED=true             # вкл/выкл
```

### Формат запроса

```json
POST /v1/chat/completions
{
  "model": "hermes-agent",
  "messages": [
    {"role": "system", "content": "Ты — AI-ассистент CRM RAI. Работаешь с пользователем {name} (роль: {role})."},
    {"role": "user", "content": "текст сообщения"}
  ]
}
```

### Формат ответа (OpenAI)

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "текст ответа"
    }
  }]
}
```

---

## 9. MCP-сервер

**Файл:** `/srv/crm-rai/mcp_server.py`
**Транспорт:** stdio (Hermes запускает как subprocess)
**БД:** прямое подключение к SQLite (read-only для поисков, read-write для мутаций)

### Конфигурация в Hermes (config.yaml)

```yaml
crm-rai-tech:
  command: "/usr/local/lib/hermes-agent/venv/bin/python"
  args: ["/srv/crm-rai/mcp_server.py"]
  env:
    CRM_DB_PATH: "/srv/crm-rai/storage/crm.db"
  connect_timeout: 30
  timeout: 60
```

### Инструменты (16 шт.)

| Инструмент | Тип | Описание |
|---|---|---|
| `search_leads` | RO | Поиск лидов (фильтры: query, region, stage, level, priority, manager) |
| `get_lead_details` | RO | Полная карточка (контакты, журнал, комментарии, задачи, сделки, документы) |
| `get_funnel` | RO | Воронка по стадиям |
| `search_tasks` | RO | Поиск задач (фильтры: status, manager, lead, overdue) |
| `create_task` | RW | Создание задачи |
| `update_task_status` | RW | Смена статуса задачи |
| `search_deals` | RO | Поиск сделок |
| `create_deal` | RW | Создание сделки |
| `update_deal_status` | RW | Смена статуса сделки |
| `add_comment` | RW | Комментарий к лиду |
| `add_contact_log` | RW | Запись звонка + авто-задача |
| `get_lead_documents` | RO | Документы лида |
| `get_templates` | RO | Шаблоны документов |
| `list_users` | RO | Пользователи CRM |
| `list_regions` | RO | Регионы |
| `change_lead_stage` | RW | Смена стадии в воронке + StageHistory |

### Безопасность

- Поисковые инструменты открывают БД в `mode=ro` (read-only)
- Мутационные инструменты используют `_get_conn_rw()` с WAL mode
- MCP-сервер не зависит от CRM FastAPI — прямой доступ к SQLite
- Нет cookie-auth — изоляция через конфигурацию Hermes

---

## 10. Деплой

### Предварительные требования

- Сервер с Docker и docker-compose
- Python 3.11 (в Docker-образе)
- Git

### Первый деплой

```bash
# На сервере
cd /srv
git clone https://github.com/DeniOne/CRM_RAI_TECH.git crm-rai
cd crm-rai

# Создать .env (НЕ коммитится — в .gitignore)
cat > .env << EOF
DATABASE_URL=sqlite+aiosqlite:///./storage/crm.db
SECRET_KEY=<сгенерировать>
ADMIN_EMAIL=admin@crm.local
ADMIN_PASSWORD=<пароль>
HERMES_API_URL=http://localhost:8080
HERMES_API_TOKEN=
HERMES_TIMEOUT=120
HERMES_ENABLED=true
EOF

# Собрать и запустить
docker compose up -d --build

# Открыть порт
ufw allow 8000/tcp

# Импорт данных
cp Екатерина.xlsx storage/
docker compose exec crm python scripts/import_xlsx.py storage/Екатерина.xlsx
```

### Обновление

```bash
# Локально
git add -A && git commit -m "..." && git push

# На сервере
cd /srv/crm-rai
git pull
docker compose up -d --build
```

### Docker-конфигурация

- `network_mode: host` — для доступа к Hermes на localhost:8080
- Volumes: `./storage` и `./templates_docx`
- `restart: unless-stopped`
- `env_file: .env`

---

## 11. Обслуживание

### Резервное копирование

```bash
# БД
ssh rai-dev "cp /srv/crm-rai/storage/crm.db /srv/crm-rai/storage/crm.db.bak.$(date +%Y%m%d)"

# Документы
ssh rai-dev "tar czf /tmp/crm_docs_$(date +%Y%m%d).tar.gz /srv/crm-rai/storage/documents/"
```

### Логи

```bash
# Логи CRM контейнера
ssh rai-dev "docker logs crm-rai-dev --tail 50"

# Логи Hermes gateway
ssh rai-dev "journalctl --user -u hermes-gateway --no-pager -n 50"

# Статус MCP-сервера
ssh rai-dev "ps aux | grep mcp_server"
```

### Перезапуск

```bash
# CRM
ssh rai-dev "cd /srv/crm-rai && docker compose restart crm"

# Hermes
ssh rai-dev "hermes gateway restart"
```

### Создание новых пользователей

На данный момент управление пользователями — через БД напрямую (нет UI):

```sql
-- Через sqlite3
INSERT INTO users (email, password_hash, full_name, role, is_active)
VALUES ('manager@crm.local', '<hash>', 'Имя Менеджера', 'manager', 1);
```

Хеш пароля генерируется скриптом:
```bash
docker compose exec crm python -c "
from app.auth import hash_password
print(hash_password('пароль'))
"
```

---

## 12. Visual Canon

Полное описание — `.planning/canon/VISUAL_CANON.md`.

### Ключевые правила

| Правило | Значение |
|---|---|
| Шрифт UI | Geist Sans |
| Шрифт тех. данных | Geist Mono (ИНН, телефоны, суммы, ID) |
| Жирность | font-medium (заголовки), font-normal (текст). **font-bold запрещён** |
| Фон | bg-canvas (#F8FAFC) |
| Поверхности | bg-white + border border-black/10 + rounded-2xl |
| Текст | text-ink (#030213), text-muted (#717182) |
| Primary кнопка | bg-ink text-white (одна на страницу) |
| Secondary | bg-white border border-black/10 |
| Ghost | text-muted hover:text-ink |
| R4 Critical | text-red-600 (lost, ошибка) |
| R3 High | text-amber-600 (просрочка) |
| R1 Info | text-blue-500 (сырой лид) |
| Success | text-emerald-500 (оплачено) |
| View/Edit | По умолчанию Label+Value без рамок; «Редактировать» → Edit Mode |
| Drawer | Формы создания — в боковой панели |
| Списки | Табличный вид (карточки запрещены, кроме канбан-board) |
| Язык | Только русский (кроме ИНН, КП, PDF и т.п.) |
