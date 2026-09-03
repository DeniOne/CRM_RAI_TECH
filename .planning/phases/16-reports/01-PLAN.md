---
phase: 16-reports
plan: "01"
slice: 16-01
type: execute
wave: 1
depends_on:
  - phase-4
  - phase-11
requirements:
  - CRM-16-01
autonomous: true
files_modified:
  - app/routes/reports.py
  - app/services/report_service.py
  - app/templates/supervisor_dashboard.html
files_created:
  - app/templates/reports_center.html
  - app/services/export_renderers.py
must_haves:
  truths:
    - "T-01: Существует страница /reports/center (HTMLResponse), доступная только supervisor/admin; остальные получают 403 (паттерн reports.py:25)."
    - "T-02: На странице есть форма фильтров: date_from, date_to (date-инпут), region_id (select из таблицы regions), manager_id (select из users where role=manager), и селектор отчёта (funnel | managers | lost_leads | deals_pipeline)."
    - "T-03: Эндпоинт /reports/download принимает те же фильтры + параметр format (xlsx | docx) и report (funnel | managers | lost_leads | deals_pipeline)."
    - "T-04: XLSX-рендер отдаётся через StreamingResponse с BytesIO — НЕТ записи во tempfile.gettempdir() и НЕТ FileResponse по пути на диске (замена текущего reports.py:110-116)."
    - "T-05: DOCX-рендер использует python-docx (Document) — создаёт заголовок (название отчёта + период фильтра), таблицу с данными, шапку колонок жирным."
    - "T-06: report_service.get_funnel_totals принимает необязательные фильтры region_id, manager_id, date_from, date_to и применяет их к запросу Lead (сейчас сигнатура без аргументов, reports.py:28)."
    - "T-07: report_service.get_manager_kpi применяет фильтр manager_id (если задан — возвращается одна строка; если нет — как сейчас, все пользователи)."
    - "T-08: Добавлены две новые функции агрегации: get_lost_leads(session, region_id, manager_id, date_from, date_to) и get_deals_pipeline(session, region_id, manager_id, date_from, date_to) — обе возвращают list[dict]."
    - "T-09: get_lost_leads группирует лиды по Lead.loss_reason (или по строке 'Без причины' если loss_reason IS NULL/пусто) на Lead.stage=='lost'; колонки: reason, count, примеры_лидов (до 3 названий)."
    - "T-10: get_deals_pipeline агрегирует Deal по Deal.status; колонки: status_label, count, total_amount (sum amount, 0 если NULL)."
    - "T-11: Кнопка 'Экспорт Excel' в supervisor_dashboard.html заменена на ссылку '/reports/center' (реорганизация входа в отчёты); старый /reports/export сохранён как alias на /reports/download?report=funnel&format=xlsx ради обратной совместимости bookmark'ов."
    - "T-12: Все 4 отчёта проходят ручной smoke-тест: выбор отчёта + формат → скачивается файл, открывается без ошибки (xlsx — в Excel, docx — в Word)."
  artifacts:
    - path: app/services/export_renderers.py
      provides: "Два рендерера: render_xlsx(report_data, sheets_meta) -> StreamingResponse(BytesIO) и render_docx(title, rows, headers) -> StreamingResponse(BytesIO). Без записи на диск."
    - path: app/templates/reports_center.html
      provides: "Единая страница-каталог отчётов с формой фильтров и кнопками XLSX/DOCX."
    - path: app/services/report_service.py (extended)
      provides: "Фильтры region_id/manager_id/date_from/date_to проброшены в get_funnel_totals и get_manager_kpi; +2 новые агрегации (lost_leads, deals_pipeline)."
    - path: app/routes/reports.py (extended)
      provides: "Роуты /reports/center (GET, HTML) и /reports/download (GET, файл). Сохранён alias /reports/export."
  key_links:
    - from: app/routes/reports.py
      to: app/services/export_renderers.py
      via: "import render_xlsx / render_docx"
      pattern: "renderer-import"
    - from: app/routes/reports.py
      to: app/services/report_service.py
      via: "вызов get_funnel_totals/get_manager_kpi/get_lost_leads/get_deals_pipeline с фильтрами"
      pattern: "aggregation-call"
    - from: app/templates/reports_center.html
      to: app/routes/reports.py
      via: "форма GET → /reports/download?report=...&format=..."
      pattern: "form-to-route"
---

# Plan 16-01 — Система отчётов CRM: каталог + фильтры + выгрузка XLSX/DOCX (Wave 1)

**Phase:** 16 — reports
**Wave:** 1
**Author (Tech Lead):** ZCode (@zcode-assistant)
**Coder:** mimo (через `/gsd-execute-phase 16` или hand-off)
**Judge:** чек-лист (smoke-тест выгрузок) — gate-автоматизации для UI-фазы нет; верификация по T-критериям + ручной прогон 4 отчётов × 2 формата.

## Контекст (почему эта фаза)

CRM RAI_EP — FastAPI + SQLAlchemy async + SQLite, рендер Jinja2 + Tailwind. Аналитический
слой для supervisor/admin уже существует и агрегирует данные:

- `app/services/report_service.py` — `get_funnel_totals`, `get_funnel_by_region`,
  `get_manager_kpi` (с date_from/date_to), `get_funnel_bottlenecks`, `get_stage_history_stats`.
- `app/routes/reports.py` — страницы `/reports`, `/reports/funnel`, `/reports/managers`
  и эндпоинт `/reports/export` (xlsx через pandas+openpyxl).
- Справочники стадий закреплены в `funnel_service.py:9-22` (STAGES, STAGE_LABELS, STAGE_COLORS).

**Что не устраивает (gap):**
1. Выгрузка только одного «сборного» xlsx (3 листа: Воронка/KPI/Просадки) — нельзя выбрать
   конкретный отчёт или формат. Запрос пользователя: «выгрузку сводных данных» с
   вариантами форматов и разрезов.
2. Нет фильтров по региону/менеджеру на уровне выгрузки (только дата — и только в KPI).
3. `reports.py:110-116` пишет файл в `tempfile.gettempdir()` БЕЗ очистки — файлы копятся
   на диске сервера (найденный долг).
4. Формат только xlsx. Нужен ещё docx (библиотека `python-docx` уже в requirements.txt).
5. Нет отчётов «потерянные лиды по причинам» (есть данные: `Lead.loss_reason`,
   `Lead.stage=='lost'`) и «пайплайн сделок» (есть `Deal.amount`, `Deal.status`).

**Решение Owner'а (фиксировано):** PDF НЕ делаем — слишком дорого по зависимостям
(docx2pdf требует Word/LibreOffice в контейнере, weasyprint/reportlab — новые либы).
Ограничиваемся xlsx + docx на уже установленных библиотеках. Это снимает технический риск.

**Скоуп Wave 1 (4 отчёта, MVP):**
- A1 — Воронка по стадиям (`get_funnel_totals` + фильтры)
- B1 — KPI менеджеров (`get_manager_kpi` + region/manager-фильтры)
- C2 — Потерянные лиды по причинам (`get_lost_leads` — НОВАЯ агрегация)
- D1 — Пайплайн сделок (`get_deals_pipeline` — НОВАЯ агрегация)

## Архитектура (обязательно к соблюдению)

1. **Разделение слоёв.** Агрегация данных — только в `report_service.py` (чистый SQL/ORM,
   возвращает list[dict] / dict). Рендер в байты — только в новом `export_renderers.py`
   (ничего не знает про БД, принимает готовые данные). Роут — только склейка
   фильтр→агрегация→рендер→ответ. Не смешивать (как сейчас в reports.py:96-116, где
   Excel-запись и агрегация в одной функции).
2. **Без записи на диск.** Все выгрузки — через `StreamingResponse` из `io.BytesIO`.
   Файл НИКОГДА не пишется в tempfile/storage. Это убирает долг №3 и риск переполнения
   диска.
3. **Единый контракт фильтров.** Набор параметров фильтрации одинаковый для всех отчётов
   и для HTML-формы, и для download-эндпоинта:
   `date_from, date_to, region_id, manager_id`. Отчёт, не имеющий смысла для какого-то
   фильтра, его игнорирует (например, deals_pipeline игнорирует manager_id — сделки
   привязаны к lead, не к deal.user для группировки; НО фильтр по region_id работает через
   join Lead). Решение «какой фильтр к какому отчёту применим» зафиксировано в Т-критериях.
4. **Роли — повтор существующего паттерна.** Каждый новый эндпоинт начинается с
   `if user.role.value not in ("supervisor", "admin"): raise HTTPException(status_code=403)`
   (как reports.py:25,50,75,99). НЕ использовать `require_role` — для консистентности
   с соседними отчётными роутами.
5. **Справочники стадий — единственный источник правды** `funnel_service.STAGE_LABELS`.
   Не дублировать подписи стадий в новых функциях — импортировать оттуда. То же для
   Deal.status — ввести `DEAL_STATUS_LABELS` в `funnel_service.py` (новая константа рядом
   со STAGE_LABELS) и переиспользовать в report_service и шаблонах.
6. **Период: применение date-фильтра.** За «дату события» принимать:
   - funnel/lost_leads → `Lead.created_at` (дата появления лида)
   - managers → `ContactLog.contact_date` для звонков, `Document.created_at` для КП
     (как сейчас в get_manager_kpi, reports.py:62-76)
   - deals_pipeline → `Deal.created_at`
   Это зафиксировать в docstring каждой функции.
7. **python-docx: минимум зависимостей от вёрстки.** Использовать базовые стили
   (`Document()`, `add_heading`, `add_table(rows, cols)`, `table.style='Table Grid'`).
   Без кастомного XML/styling — это YAGNI для отчётов. Заголовок + таблица — достаточно.
8. **Обратная совместимость.** Bookmark'и на `/reports/export` не должны сломаться —
   оставить его как alias (см. T-11). Это спасёт пользователей, у которых ссылка в избранном.
9. **Импорт `pd` сохраняется** только ради `pd.DataFrame(...)`/`.to_excel` в рендерере.
   Не тащить pandas в report_service — там только ORM.

## Файлы

### 1. `app/services/export_renderers.py` (НОВЫЙ) — слой рендера

**Назначение:** изолировать генерацию xlsx/docx от БД и роутов. Принимает готовые данные
(list[dict] / dict), возвращает `StreamingResponse`.

**Экспортируемые функции:**

```python
from io import BytesIO
from fastapi.responses import StreamingResponse
import pandas as pd
from docx import Document

def render_xlsx(sheets: list[tuple[str, list[dict]]], filename: str = "report.xlsx") -> StreamingResponse:
    """
    sheets: список (sheet_name, rows). rows — list[dict] (или []).
    Каждая пара → отдельный лист xlsx.
    Возвращает StreamingResponse с корректными заголовками (Content-Disposition, MIME).
    """

def render_docx(title: str, period: str, headers: list[str], rows: list[list]) -> StreamingResponse:
    """
    title: заголовок отчёта (add_heading, уровень 0).
    period: строка периода (например "01.07.2026 — 23.07.2026" или "Весь период").
    headers: имена колонок (шапка таблицы, жирным).
    rows: list[list] — значения по строкам (без заголовка).
    """
```

**Важно:**
- `render_xlsx` создаёт `buf = BytesIO()`, `pd.ExcelWriter(buf, engine="openpyxl")`,
  в конце `buf.seek(0)`. НЕ использует tempfile.
- `render_docx` — `buf = BytesIO()`, `doc.save(buf)`, `buf.seek(0)`.
- Обе функции возвращают `StreamingResponse(buf, media_type=..., headers={
  "Content-Disposition": f'attachment; filename="{filename}"'})`.
- MIME: xlsx → `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`;
  docx → `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.
- Имя файла всегда в ASCII (избежать проблем с кириллицей в заголовке): например
  `report_funnel_2026-07-23.xlsx`. Кодируем через translit или фиксированные имена.

### 2. `app/services/report_service.py` — расширить агрегации

**Сейчас:** `get_funnel_totals(session)` без аргументов (стр. 26), `get_manager_kpi(session,
date_from, date_to)` (стр. 52). Фильтров region/manager нет.

**Задача:** пробросить единый набор фильтров; добавить 2 функции.

**(a) `get_funnel_totals`** — `app/services/report_service.py:26`

**Было:** `async def get_funnel_totals(session: AsyncSession) -> dict:`
**Стало:** `async def get_funnel_totals(session, region_id=None, manager_id=None, date_from=None, date_to=None) -> dict:`

Базовый запрос `select(Lead.stage, func.count(Lead.id))` обернуть в построение `where`:
- region_id → `Lead.region_id == region_id`
- manager_id → `Lead.assigned_manager_id == manager_id`
- date_from → `Lead.created_at >= date_from`
- date_to → `Lead.created_at <= date_to`

Тело цикла по STAGES не меняется (конверсия считается так же).

**(b) `get_manager_kpi`** — `app/services/report_service.py:52`

**Было:** `async def get_manager_kpi(session, date_from=None, date_to=None) -> list[dict]:`
**Стало:** `async def get_manager_kpi(session, date_from=None, date_to=None, manager_id=None, region_id=None) -> list[dict]:`

- manager_id → фильтр `User.id == manager_id` (одна строка вместо всех). Применять в
  `select(User)`.
- region_id → применяется к подзапросам лидов (`Lead.assigned_manager_id == user.id` AND
  `Lead.region_id == region_id`). Это меняет total_leads и conversion_rate для менеджера
  в выбранном регионе.
- docstring: «date-фильтр применяется к ContactLog.contact_date и Document.created_at».

**(c) `get_lost_leads` (НОВАЯ)** — добавить после `get_stage_history_stats` (стр. 139)

```python
async def get_lost_leads(session, region_id=None, manager_id=None, date_from=None, date_to=None) -> list[dict]:
    """
    Группировка потерянных лидов по причине.
    Колонки: reason (loss_reason или 'Без причины'), count, examples (до 3 названий).
    Период — по Lead.created_at.
    """
```

Логика:
1. Запрос «по причинам»: `select(Lead.loss_reason, func.count(Lead.id)).where(
   Lead.stage=='lost', <фильтры>).group_by(Lead.loss_reason)`.
2. Нормализовать `None`/`""` → `"Без причины"`.
3. Отдельным запросом — примеры названий (до 3) на причину:
   `select(Lead.loss_reason, Lead.name).where(Lead.stage=='lost', <фильтры>)`,
   собрать в dict reason→list, обрезать до 3.
4. Соединить, вернуть list[dict] отсортированный по count desc.

**(d) `get_deals_pipeline` (НОВАЯ)** — рядом

```python
async def get_deals_pipeline(session, region_id=None, manager_id=None, date_from=None, date_to=None) -> list[dict]:
    """
    Агрегат Deal по Deal.status.
    Колонки: status_code, status_label, count, total_amount.
    region_id/manager_id — через join Lead (Deal.lead_id → Lead.id).
    Период — по Deal.created_at.
    """
```

Логика:
1. `select(Deal.status, func.count(Deal.id), func.coalesce(func.sum(Deal.amount), 0))`.
2. `.join(Lead, Deal.lead_id == Lead.id)` если задан region_id или manager_id.
3. Применить where по фильтрам.
4. `.group_by(Deal.status)`.
5. Для каждого status проставить `status_label` из `DEAL_STATUS_LABELS` (новая константа).
6. Вернуть list[dict], порядок — как в DEAL_STATUS_LABELS (а не как вернёт group_by).

### 3. `app/services/funnel_service.py` — новая константа DEAL_STATUS_LABELS

**Сейчас:** определены STAGES, STAGE_LABELS, STAGE_COLORS (стр. 9-29).
**Задача:** добавить рядом (после STAGE_COLORS, стр. 29):

```python
DEAL_STATUS_LABELS = {
    "new": "Новая",
    "kp_sent": "КП отправлено",
    "negotiation": "Переговоры",
    "contract": "Договор",
    "invoiced": "Счёт выставлен",
    "paid": "Оплачено",
    "lost": "Потеряна",
}
```

Источник значений — `app/templates/partials/deal_row.html:13-19` (подтверждено при аудите).
Этот же dict используется в шаблонах сделок — обновить `deal_row.html` и место рендера
select'а статуса сделки, чтобы значения не дублировались (см. правило зависимостей AGENTS.md).
Если вынести все 7 значений из шаблона в константу нетривиально — оставить шаблон как есть,
а константу использовать только в отчётах; зафиксировать как известный дубль в
README-CONTRACT Known limitations.

### 4. `app/templates/reports_center.html` (НОВЫЙ) — каталог отчётов

**Назначение:** единая страница входа в отчёты. Заменяет хаотичные 3 ссылки в шапке
`supervisor_dashboard.html` одной точкой.

**Структура:**
- `{% extends "base.html" %}`, title «Отчёты — CRM RAI».
- Форма `method="get"` (HTMX-стиль не обязателен; обычный GET, т.к. выгрузка = файл).
  Поля: date_from, date_to (date-инпуты), region_id (select: «Все» + список из `regions`),
  manager_id (select: «Все» + менеджеры из `managers`), report (radio/select из 4 отчётов).
- Блок «Каталог отчётов»: 4 карточки (Воронка / KPI / Потерянные / Пайплайн), каждая с
  кратким описанием и кнопками `[XLSX]` `[DOCX]`. Кнопки — это `<a href>` на
  `/reports/download?report=<name>&format=<fmt>&<фильтры>`.
- Контекст из роута: `regions` (list[Region]), `managers` (list[User where role=manager]),
  `current_user`.
- Стиль — Tailwind, повторить паттерн `managers_report.html` (bg-white, border-black/10,
  rounded-2xl, текстовые классы text-ink/text-muted из VISUAL_CANON).

**JS для синхронизации фильтров с кнопками карточек (минимум):**
при изменении полей формы — обновлять `href` у кнопок XLSX/DOCX через querystring
(`URLSearchParams`). Иначе фильтры не попадут в выгрузку. Это ~15 строк vanilla JS
в `<script>` в конце шаблона. Без нового файла в static/js (YAGNI).

### 5. `app/routes/reports.py` — новые роуты + alias

**(a) Новый роут `/reports/center`** (GET, HTML) — перед `@router.get("/reports")` (стр. 21)
или сразу после. Загружает `regions` и `managers`:

```python
@router.get("/reports/center", response_class=HTMLResponse)
async def reports_center(request: Request, session: AsyncSession = Depends(get_session)):
    # стандартный role-гейт (reports.py:25)
    regions = await session.execute(select(Region).order_by(Region.name))
    managers = await session.execute(select(User).where(User.role == UserRole.manager).order_by(User.full_name))
    return templates.TemplateResponse("reports_center.html", {...})
```

**(b) Новый роут `/reports/download`** (GET, файл) — ядро выгрузки:

```python
@router.get("/reports/download")
async def download_report(
    request: Request,
    report: str,            # funnel | managers | lost_leads | deals_pipeline
    format: str = "xlsx",   # xlsx | docx
    date_from: str = None, date_to: str = None,
    region_id: int = None, manager_id: int = None,
    session: AsyncSession = Depends(get_session),
):
    # role-гейт
    # парсинг date_from/date_to в datetime (как reports.py:79-80)
    # dispatch по report → вызов соответствующей агрегации с фильтрами
    # dispatch по format → render_xlsx / render_docx
    # вернуть StreamingResponse
```

Dispatch-таблица (внутри функции, map report→(aggregator, meta)):

| report | aggregator | sheets/headers для xlsx | docx title |
|---|---|---|---|
| funnel | get_funnel_totals | один лист «Воронка», колонки code/label/count/conversion_pct | «Воронка продаж» |
| managers | get_manager_kpi | лист «KPI», колонки full_name/role/total_leads/calls_count/kp_sent/deals_count/conversion_rate | «KPI менеджеров» |
| lost_leads | get_lost_leads | лист «Потерянные», колонки reason/count/examples | «Потерянные лиды» |
| deals_pipeline | get_deals_pipeline | лист «Пайплайн», колонки status_label/count/total_amount | «Пайплайн сделок» |

Валидация: неизвестный `report` → `HTTPException(400, "Неизвестный тип отчёта")`.
Неизвестный `format` → `HTTPException(400, "Неизвестный формат")`.

**(c) Alias `/reports/export`** — `app/routes/reports.py:96-116`

**Было:** пишет во tempfile, `FileResponse`.
**Стало:** тонкий redirect/alias на новый контракт:

```python
@router.get("/reports/export")
async def export_report_legacy(request, report: str = "funnel", format: str = "xlsx",
                                date_from=None, date_to=None, region_id=None, manager_id=None,
                                session=Depends(get_session)):
    # делегирует логику в download_report (вызов общей внутренней функции _build_report_response)
    return await download_report(request, report=report, format=format, date_from=date_from,
                                 date_to=date_to, region_id=region_id, manager_id=manager_id,
                                 session=session)
```

Убрать `import os, tempfile, time` (стр. 1-3), если больше нигде не используются в файле.
Оставить `import pandas as pd` только если он остался нужен (если xlsx-рендер уехал в
export_renderers — убрать отсюда).

**(d) Обновить шапку `supervisor_dashboard.html`** — `app/templates/supervisor_dashboard.html:9`

**Было:**
```html
<a href="/reports/export" class="...">Экспорт Excel</a>
```
**Стало:**
```html
<a href="/reports/center" class="...">Отчёты</a>
```
Соседние ссылки на `/reports/funnel`, `/reports/managers` (стр. 7-8) оставить — это
HTML-представления, они не дублируют выгрузку.

## Anti-conflict (важно для кодера)

**НЕ ТРОГАТЬ:**
- `app/services/hermes_service.py`, `app/services/dadata_service.py`, `app/routes/agent.py`
  (AI-агент — другая зона, активная разработка в фазах 6).
- `app/services/document_service.py`, `app/routes/documents.py` — это генерация клиентских
  docx/pdf документов (КП/договоры), НЕ отчёты. Не путать с docx-рендером отчётов.
  Нужная функция `convert_to_pdf` — НЕ трогать (PDF в этой фазе нет).
- `app/models.py` — НЕТ миграций БД. Все нужные поля (`Lead.loss_reason`, `Deal.amount`,
  `Deal.status`, `Lead.region_id`, `Lead.assigned_manager_id`) уже существуют.
- `app/database.py:38-89` (ALTER-миграции) — не добавлять новые колонки.
- `app/auth.py`, `app/main.py` (роутер уже зарегистрирован: `app/main.py` include_router
  reports — новый роут подхersватится автоматически).
- `templates_docx/`, `storage/documents/` — клиентские документы, не отчёты.
- Частотный парсер `app/services/phone_parser.py`, `app/services/import_service.py`.

**Осторожно (читать, не ломать):**
- `app/services/funnel_service.py` — используется канбаном (`kanban.html`, `lead_card.html`),
  сменой стадии. Добавление константы `DEAL_STATUS_LABELS` безопасно (новый символ).
  Существующие STAGES/STAGE_LABELS/STAGE_COLORS НЕ менять.
- `app/templates/partials/deal_row.html:13-19` — читает статусы сделок. Если выносим
  значения в DEAL_STATUS_LABELS — проверить, что рендер не сломался (правило зависимостей).

## Готово, когда (success criteria)

- [ ] T-01..T-12 из frontmatter выполнены (сверка по коду + ручной прогон).
- [ ] `GET /reports/center` отдаёт HTML с формой и 4 карточками; под manager/обычным
      пользователем возвращает 403.
- [ ] `GET /reports/download?report=funnel&format=xlsx` скачивает .xlsx, открывается в
      Excel (LibreOffice) без ошибки, содержит лист «Воронка» с колонками стадий.
- [ ] `GET /reports/download?report=managers&format=docx` скачивает .docx, открывается в
      Word, содержит заголовок «KPI менеджеров» + таблицу с шапкой.
- [ ] Фильтр region_id отражается в результате: `?report=funnel&region_id=<id>&format=xlsx`
      даёт другое (меньшее) число лидов, чем без фильтра.
- [ ] `grep -rn "tempfile" app/routes/reports.py` → пусто (долг №3 закрыт).
- [ ] `grep -rn "FileResponse" app/routes/reports.py` → пусто (только StreamingResponse).
- [ ] `/reports/export` (старый URL) по-прежнему отдаёт xlsx — обратная совместимость.
- [ ] Существующие страницы `/reports`, `/reports/funnel`, `/reports/managers` работают
      без регресса (не сломаны правками report_service).

## Не готово, когда

- XLSX или DOCX не открывается (битый файл / ошибка рендера).
- Любой из 4 отчётов падает с 500 (исключение в агрегации/рендере).
- Нарушен role-гейт (менеджер может скачать отчёт) — критичный регресс безопасности.
- Сломан старый `/reports/export` (регресс для bookmark'ов).
- Файл пишется на диск (tempfile/storage) — T-04 нарушен.
- `get_funnel_totals`/`get_manager_kpi` потеряли обратную совместимость по сигнатуре
  (вызов без аргументов в `/reports` должен работать как раньше — T-06/T-07).

## Что даёт эта фаза для проекта

- **Capability:** единая точка выгрузки сводных отчётов с фильтрами и двумя форматами
  (xlsx + docx). Раньше — один жёсткий xlsx без фильтров.
- **Долг закрыт:** tempfile-накопление в `/reports/export` (найдено при аудите этой фазы).
- **Расширяемость:** контракт «aggregator → renderer → route» позволяет добавить новый
  отчёт за одну функцию в report_service + строку в dispatch-таблице, не трогая рендер.

## Не делаем (YAGNI — отдельные фазы, если будет запрос)

- **PDF** — прямо запрещён Owner'ом (технический риск зависимостей). Если понадобится —
  отдельная фаза с оценкой weasyprint vs reportlab vs docx2pdf-в-контейнере.
- **CSV-формат** — тривиально добавить (одна строка в renderer), но явного запроса не было.
  Кандидат на быстрый follow-up, не блокирует.
- **Отчёты по задачам** (просроченные, по исполнителям) — фаза 17-кандидат. Данные есть
  (`Task.due_date`, `Task.status`), но `is_overdue` — runtime-формула, нужна аккуратная
  SQL-репликация.
- **Time-in-stage (скорость воронки)** — фаза 18-кандидат. Требует агрегации по
  `StageHistory.changed_at` (разница соседних переходов).
- **Активности и исходы контактов** (звонки по дням, дозвон/отказ/КП) — фаза 19-кандидат.
  `ContactLog.outcome` уже есть, но UI-фильтров и агрегаций пока нет.
- **«Источник лида» (lead source)** — поля в схеме НЕТ. Нужна мини-фаза миграции:
  new column `Lead.source` + заполнение при импорте + UI. Без этого отчёта «каналы
  привлечения» быть не может. Блокер для отчёта-источников, но НЕ для этой фазы.
- **Графики/визуализация в выгрузках** — docx/xlsx — табличный формат, графики YAGNI.
  Визуализация есть на HTML-страницах (воронка-бары в supervisor_dashboard.html).
- **Сохранение настроек отчёта / «мои отчёты»** — YAGNI, нет запроса.
- **Отправка отчёта по email / по расписанию** — отдельная фаза, требует SMTP-настройки.

## Следующий шаг

После PASS фазы 16 — оценить спрос на отчёты задач (фаза 17) и time-in-stage (фаза 18).
CSV-формат можно добавить как микро-patch в любом коммите (одна строка renderer + кнопка).
