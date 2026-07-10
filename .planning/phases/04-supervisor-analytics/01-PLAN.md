---
phase: 4-supervisor-analytics
plan: "01"
slice: 4-01
type: execute
wave: 1
depends_on:
  - phase-3
requirements:
  - CRM-4-01
autonomous: true
files_modified:
  - app/routes/deals.py
  - app/routes/dashboard.py
  - app/templates/base.html
  - app/templates/dashboard.html
files_created:
  - app/routes/reports.py
  - app/services/report_service.py
  - app/templates/supervisor_dashboard.html
  - app/templates/funnel_report.html
  - app/templates/partials/funnel_table.html
  - app/templates/partials/kpi_table.html
  - app/templates/partials/region_funnel.html
  - scripts/export_report.py
must_haves:
  truths:
    - "D-01: app/routes/deals.py — create_deal и lead_deals добавлен .options(selectinload(Deal.lead)) к запросам — фикс долга D-G (баг 500 MissingGreenlet)"
    - "D-02: app/services/report_service.py содержит async get_funnel_by_region(session) -> list[dict] — для каждого региона: name + count по каждой стадии (0..7 + lost) + total"
    - "D-03: app/services/report_service.py содержит async get_funnel_totals(session) -> dict — общее кол-во лидов по каждой стадии + конверсия между соседними стадиями (stage N → stage N+1 в процентах)"
    - "D-04: app/services/report_service.py содержит async get_manager_kpi(session, date_from, date_to) -> list[dict] — для каждого менеджера: full_name, total_leads, calls_count (ContactLog за период), kp_sent (Documents doc_type=kp за период), deals_count, conversion_rate (leads на стадии >=3 / total leads)"
    - "D-05: app/services/report_service.py содержит async get_funnel_bottlenecks(session) -> list[dict] — для каждой пары соседних стадий: from_stage, to_stage, from_count, to_count, conversion_pct, is_bottleneck (True если конверсия < 50%)"
    - "D-06: app/services/report_service.py содержит async get_stage_history_stats(session) -> list[dict] — из StageHistory: для каждого перехода from→to: count, avg_days (среднее время на стадии, вычисляется как разница changed_at между последовательными переходами одного lead_id)"
    - "D-07: GET /reports — дашборд супервайзера: доступен только supervisor/admin (require_role). Содержит 4 секции: воронка по регионам, общая воронка с конверсией, KPI менеджеров, просадки воронки"
    - "D-08: GET /reports/funnel — детальный отчёт воронки: таблица регион × стадия с подсветкой просадок (ячейки с конверсией <50% — amber, <25% — red)"
    - "D-09: GET /reports/managers — KPI менеджеров: таблица (менеджер, лидов всего, звонков за период, КП отправлено, сделок, конверсия). Фильтр по дате (date_from, date_to query params)"
    - "D-10: GET /reports/export — экспорт отчёта в Excel: создаёт .xlsx через pandas/openpyxl с 3 листами (Воронка, KPI менеджеров, Просадки). Возвращает FileResponse"
    - "D-11: Дашборд супервайзера (supervisor_dashboard.html) показывает: общее кол-во лидов, распределение по стадиям (bar chart через inline SVG или CSS-бары), топ-5 регионов по кол-ву лидов, просадки воронки с цветовой индикацией"
    - "D-12: GET /reports/managers корректно обрабатывает случай без менеджеров (0 users с role=manager) — показывает empty state 'Нет менеджеров', не падает"
    - "D-13: GET /reports корректно обрабатывает StageHistory с 0-1 записями — показывает empty state 'Недостаточно данных' вместо пустой таблицы или ошибки"
    - "D-14: Sidebar обновлён: для supervisor/admin добавлена ссылка 'Аналитика' → /reports. Для manager — не видна"
    - "D-15: Дашборд менеджера (GET /) — для role=manager показывает личные KPI: мои лиды по стадиям, мои звонки, мои таски (просроченные + на сегодня). Для supervisor/admin — общие счётчики (как сейчас)"
    - "D-16: report_service: все запросы используют async SQLAlchemy (select + func.count + group_by). Никаких raw SQL строк"
    - "D-17: scripts/export_report.py — standalone-скрипт: инициализирует БД, вызывает report_service функции, создаёт .xlsx через pandas, сохраняет в storage/exports/report_{date}.xlsx, печатает путь"
    - "D-18: GET /reports/export корректно создаёт .xlsx с 3 листами: 'Воронка' (регион × стадия), 'KPI' (менеджеры), 'Просадки' (переходы с конверсией). Файл сохраняется во временную директорию и отдаётся через FileResponse"
  artifacts:
    - path: app/services/report_service.py
      provides: "Агрегация данных: воронка по регионам, KPI менеджеров, просадки, история стадий"
    - path: app/routes/reports.py
      provides: "Веб-отчёты супервайзера + экспорт в Excel"
    - path: app/templates/supervisor_dashboard.html
      provides: "Дашборд аналитики с визуализацией воронки"
  key_links:
    - from: app/routes/reports.py
      to: app/services/report_service.py
      via: "get_funnel_by_region + get_manager_kpi + get_funnel_bottlenecks"
      pattern: "analytics aggregation"
    - from: app/routes/reports.py
      to: app/templates/supervisor_dashboard.html
      via: "TemplateResponse with report data"
      pattern: "report rendering"
---

# Plan 4-01 — Аналитика супервайзера (Wave 1)

**Phase:** 4 — supervisor-analytics
**Wave:** B-1
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

Фазы 1–3 дали функциональный CRM: импорт данных, канбан, карточка лида, документооборот. Супервайзер пока видит только счётчики на дашборде. Фаза 4 даёт супервайзеру аналитический инструмент: воронка по регионам, KPI менеджеров, просадки воронки, экспорт в Excel.

**Текущее состояние данных (из разведки):**
- 583 лида, 29 регионов, 5 стадий активны (0: 382, 1: 151, 3: 26, 4: 3, lost: 21)
- 1 user (admin), 0 назначенных менеджеров
- 307 ContactLog (306 без user_id — импортированы из xlsx)
- StageHistory: 1 запись (почти пусто — воронка ещё не использовалась в CRM)
- 1 Document (kp, sent), 3 Deals (new)

**Важно:** аналитика по менеджерам пока покажет мало данных (нет менеджеров, нет истории стадий). Но структура должна быть готова — когда менеджеры начнут работать, данные появятся автоматически. Empty states обязательны.

**Долг Фазы 3, закрываемый здесь:**
- D-G: баг `create_deal` / `lead_deals` — MissingGreenlet (отсутствует selectinload)

## Что делает кодер (пофайлово)

### 0. Пре-фикс: `app/routes/deals.py` (модификация) — фикс долга D-G

**Сейчас:** `create_deal` (строка ~83) и `lead_deals` (строка ~50) делают `select(Deal).where(...)` без `.options(selectinload(Deal.lead))`. Шаблон `deal_row.html` обращается к `deal.lead.name` → `MissingGreenlet` → 500.

**Задача:** добавить `.options(selectinload(Deal.lead))` к обоим запросам:

```python
# В create_deal (после commit, при перезагрузке deals):
result = await session.execute(
    select(Deal).where(Deal.lead_id == lead_id)
    .options(selectinload(Deal.lead))
    .order_by(Deal.created_at.desc())
)

# В lead_deals:
result = await session.execute(
    select(Deal).where(Deal.lead_id == lead_id)
    .options(selectinload(Deal.lead))
    .order_by(Deal.created_at.desc())
)
```

### 1. `app/services/report_service.py` (новый) — агрегация данных

#### `async def get_funnel_by_region(session) -> list[dict]`

Для каждого региона — счётчик лидов по каждой стадии:

```python
async def get_funnel_by_region(session: AsyncSession) -> list[dict]:
    """Возвращает [{region_name, stage_0, stage_1, ..., stage_7, lost, total}, ...]"""
    result = await session.execute(
        select(
            Region.name,
            Lead.stage,
            func.count(Lead.id)
        )
        .join(Lead, Lead.region_id == Region.id)
        .group_by(Region.name, Lead.stage)
    )
    
    # Собираем матрицу регион × стадия
    regions_data = {}
    for row in result:
        name = row[0]
        stage = row[1]
        count = row[2]
        if name not in regions_data:
            regions_data[name] = {"region": name, "total": 0}
        regions_data[name][f"stage_{stage}"] = count
        regions_data[name]["total"] += count
    
    return sorted(regions_data.values(), key=lambda x: x["total"], reverse=True)
```

#### `async def get_funnel_totals(session) -> dict`

Общая воронка + конверсия между стадиями:

```python
async def get_funnel_totals(session: AsyncSession) -> dict:
    """Возвращает {stages: [{code, label, count, conversion_pct}], total_leads}"""
    result = await session.execute(
        select(Lead.stage, func.count(Lead.id)).group_by(Lead.stage)
    )
    stage_counts = {row[0]: row[1] for row in result}
    
    stages = []
    prev_count = None
    for code in STAGES:
        count = stage_counts.get(code, 0)
        conversion = None
        if prev_count and prev_count > 0 and code != "lost":
            conversion = round(count / prev_count * 100, 1)
        stages.append({"code": code, "label": STAGE_LABELS[code], "count": count, "conversion_pct": conversion})
        if code != "lost":
            prev_count = count
    
    total = sum(stage_counts.values())
    return {"stages": stages, "total_leads": total}
```

#### `async def get_manager_kpi(session, date_from=None, date_to=None) -> list[dict]`

KPI каждого менеджера за период:

```python
async def get_manager_kpi(session, date_from=None, date_to=None) -> list[dict]:
    """Для каждого user с role=manager (или admin): 
    full_name, total_leads, calls_count, kp_sent, deals_count, conversion_rate"""
    # 1. Загрузить всех users
    users_result = await session.execute(select(User))
    users = users_result.scalars().all()
    
    kpi_list = []
    for user in users:
        # Total leads assigned
        total_leads = await session.scalar(
            select(func.count(Lead.id)).where(Lead.assigned_manager_id == user.id)
        )
        
        # Calls in period
        calls_query = select(func.count(ContactLog.id)).where(ContactLog.user_id == user.id)
        if date_from:
            calls_query = calls_query.where(ContactLog.contact_date >= date_from)
        if date_to:
            calls_query = calls_query.where(ContactLog.contact_date <= date_to)
        calls_count = await session.scalar(calls_query)
        
        # KP sent in period
        kp_query = select(func.count(Document.id)).where(
            Document.user_id == user.id, Document.doc_type == "kp"
        )
        if date_from:
            kp_query = kp_query.where(Document.created_at >= date_from)
        if date_to:
            kp_query = kp_query.where(Document.created_at <= date_to)
        kp_sent = await session.scalar(kp_query)
        
        # Deals count
        deals_count = await session.scalar(
            select(func.count(Deal.id)).where(Deal.user_id == user.id)
        )
        
        # Conversion: leads on stage >= 3 / total leads
        converted = await session.scalar(
            select(func.count(Lead.id)).where(
                Lead.assigned_manager_id == user.id,
                Lead.stage.in_(["3", "4", "5", "6", "7"])
            )
        )
        conversion_rate = round(converted / total_leads * 100, 1) if total_leads else 0
        
        kpi_list.append({
            "full_name": user.full_name,
            "total_leads": total_leads,
            "calls_count": calls_count,
            "kp_sent": kp_sent,
            "deals_count": deals_count,
            "conversion_rate": conversion_rate,
        })
    
    return kpi_list
```

#### `async def get_funnel_bottlenecks(session) -> list[dict]`

Просадки между соседними стадиями:

```python
async def get_funnel_bottlenecks(session) -> list[dict]:
    """Для каждой пары соседних стадий: from, to, from_count, to_count, conversion_pct, is_bottleneck"""
    result = await session.execute(
        select(Lead.stage, func.count(Lead.id)).group_by(Lead.stage)
    )
    stage_counts = {row[0]: row[1] for row in result}
    
    bottlenecks = []
    linear_stages = ["0", "1", "2", "3", "4", "5", "6", "7"]  # без lost
    for i in range(len(linear_stages) - 1):
        from_stage = linear_stages[i]
        to_stage = linear_stages[i + 1]
        from_count = stage_counts.get(from_stage, 0)
        to_count = stage_counts.get(to_stage, 0)
        conversion = round(to_count / from_count * 100, 1) if from_count > 0 else 0
        bottlenecks.append({
            "from_stage": from_stage,
            "from_label": STAGE_LABELS[from_stage],
            "to_stage": to_stage,
            "to_label": STAGE_LABELS[to_stage],
            "from_count": from_count,
            "to_count": to_count,
            "conversion_pct": conversion,
            "is_bottleneck": conversion < 50,
        })
    return bottlenecks
```

#### `async def get_stage_history_stats(session) -> list[dict]`

Среднее время на стадии (из StageHistory):

```python
async def get_stage_history_stats(session) -> list[dict]:
    """Из StageHistory: для каждого перехода from→to: count, avg_days"""
    result = await session.execute(
        select(StageHistory.from_stage, StageHistory.to_stage, func.count())
        .group_by(StageHistory.from_stage, StageHistory.to_stage)
    )
    return [{"from_stage": r[0], "to_stage": r[1], "count": r[2]} for r in result]
```

⚠ **Примечание:** расчёт avg_days (среднее время на стадии) требует оконных функций или Python-обработки. StageHistory почти пуст — не усложнять. Если записей < 10 — возвращать empty list с пометкой "недостаточно данных".

### 2. `app/routes/reports.py` (новый) — роутер отчётов

Подключается в `app/main.py`: `app.include_router(reports.router)`

Все роуты — `require_role("supervisor", "admin")`.

#### `GET /reports` — дашборд супервайзера

```python
@router.get("/reports")
async def supervisor_dashboard(request, session):
    user = await get_current_user(request, session)
    # Проверка роли
    if user.role.value not in ("supervisor", "admin"):
        raise HTTPException(403)
    
    funnel_totals = await get_funnel_totals(session)
    funnel_regions = await get_funnel_by_region(session)
    bottlenecks = await get_funnel_bottlenecks(session)
    
    return templates.TemplateResponse(
        request, "supervisor_dashboard.html",
        {"current_user": user, "funnel_totals": funnel_totals, 
         "funnel_regions": funnel_regions[:10], "bottlenecks": bottlenecks}
    )
```

#### `GET /reports/funnel` — детальная воронка

```python
@router.get("/reports/funnel")
async def funnel_report(request, session, region: int = None):
    # Если region указан — фильтр по региону
    funnel_regions = await get_funnel_by_region(session)
    # ... рендер funnel_report.html
```

#### `GET /reports/managers` — KPI менеджеров

```python
@router.get("/reports/managers")
async def managers_report(request, session,
                          date_from: str = None, date_to: str = None):
    # Парсинг дат
    df = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    dt = datetime.strptime(date_to, "%Y-%m-%d") if date_to else None
    
    kpi_list = await get_manager_kpi(session, df, dt)
    return templates.TemplateResponse(
        request, "managers_report.html",
        {"current_user": user, "kpi_list": kpi_list, "date_from": date_from, "date_to": date_to}
    )
```

#### `GET /reports/export` — экспорт в Excel

```python
@router.get("/reports/export")
async def export_report(request, session):
    # Собрать данные
    funnel_regions = await get_funnel_by_region(session)
    kpi_list = await get_manager_kpi(session)
    bottlenecks = await get_funnel_bottlenecks(session)
    
    # Создать DataFrame → Excel
    import pandas as pd
    import tempfile, os
    
    df_funnel = pd.DataFrame(funnel_regions)
    df_kpi = pd.DataFrame(kpi_list)
    df_bottlenecks = pd.DataFrame(bottlenecks)
    
    # Excel с 3 листами
    output_path = os.path.join(tempfile.gettempdir(), f"crm_report_{int(time.time())}.xlsx")
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_funnel.to_excel(writer, sheet_name="Воронка", index=False)
        df_kpi.to_excel(writer, sheet_name="KPI менеджеров", index=False)
        df_bottlenecks.to_excel(writer, sheet_name="Просадки", index=False)
    
    return FileResponse(output_path, filename=f"crm_report.xlsx")
```

### 3. `app/templates/supervisor_dashboard.html` (новый)

Структура:

```html
{% extends "base.html" %}
{% block content %}

<h1 class="text-2xl font-medium mb-6">Аналитика</h1>

<!-- Общая воронка с конверсией -->
<div class="bg-white border border-black/10 rounded-2xl p-6 mb-4">
    <h2 class="text-lg font-medium mb-4">Воронка продаж</h2>
    <div class="space-y-2">
        {% for stage in funnel_totals.stages %}
        <div class="flex items-center gap-4">
            <div class="w-32 text-sm text-gray-600">{{ stage.label }}</div>
            <!-- CSS bar -->
            <div class="flex-1 bg-gray-100 rounded-full h-6 relative">
                <div class="absolute inset-y-0 left-0 rounded-full"
                     style="width: {{ (stage.count / funnel_totals.total_leads * 100) if funnel_totals.total_leads else 0 }}%"
                     ... ></div>
            </div>
            <div class="w-12 text-sm font-medium text-right">{{ stage.count }}</div>
            {% if stage.conversion_pct is not none %}
            <div class="w-16 text-xs text-gray-400 text-right">{{ stage.conversion_pct }}%</div>
            {% else %}
            <div class="w-16"></div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    <div class="mt-4 text-sm text-gray-500">Всего лидов: {{ funnel_totals.total_leads }}</div>
</div>

<!-- Просадки воронки -->
<div class="bg-white border border-black/10 rounded-2xl p-6 mb-4">
    <h2 class="text-lg font-medium mb-4">Просадки воронки</h2>
    <table class="w-full text-sm">
        <thead class="text-gray-500 border-b">
            <tr>
                <th class="text-left py-2">Переход</th>
                <th class="text-right py-2">Было</th>
                <th class="text-right py-2">Стало</th>
                <th class="text-right py-2">Конверсия</th>
            </tr>
        </thead>
        <tbody>
            {% for b in bottlenecks %}
            <tr class="border-b">
                <td class="py-2">{{ b.from_label }} → {{ b.to_label }}</td>
                <td class="text-right py-2">{{ b.from_count }}</td>
                <td class="text-right py-2">{{ b.to_count }}</td>
                <td class="text-right py-2
                    {% if b.conversion_pct < 25 %}text-red-600
                    {% elif b.conversion_pct < 50 %}text-amber-600
                    {% else %}text-emerald-600{% endif %}">
                    {{ b.conversion_pct }}%
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<!-- Топ регионов -->
<div class="bg-white border border-black/10 rounded-2xl p-6 mb-4">
    <h2 class="text-lg font-medium mb-4">Регионы</h2>
    <table class="w-full text-sm">
        <thead class="text-gray-500 border-b">
            <tr><th class="text-left py-2">Регион</th><th class="text-right py-2">Лидов</th></tr>
        </thead>
        <tbody>
            {% for r in funnel_regions %}
            <tr class="border-b">
                <td class="py-2">{{ r.region }}</td>
                <td class="text-right py-2">{{ r.total }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<!-- Экспорт -->
<a href="/reports/export" class="inline-block bg-[#030213] text-white px-4 py-2 rounded text-sm">
    Экспорт в Excel
</a>

{% endblock %}
```

### 4. `app/templates/funnel_report.html` (новый)

Детальная таблица: регион × стадия. Ячейки с конверсией <50% — amber, <25% — red.

### 5. `app/templates/managers_report.html` (новый)

Таблица KPI менеджеров + форма фильтра по датам (date_from, date_to). Empty state если нет менеджеров.

### 6. `app/routes/dashboard.py` (модификация) — персонализация по роли

**Сейчас:** GET / — общие счётчики для всех.

**Задача:** для role=manager — личные KPI:
```python
if user.role.value == "manager":
    # Только свои лиды
    total_leads = await session.scalar(
        select(func.count(Lead.id)).where(Lead.assigned_manager_id == user.id)
    )
    # Свои звонки за сегодня
    # Свои просроченные таски
    # Рендер dashboard.html с manager-specific контекстом
else:
    # Общие счётчики (как сейчас)
```

### 7. `app/templates/dashboard.html` (модификация)

Для manager — добавить блок «Мои таски на сегодня» и «Мои просроченные таски».

### 8. `app/templates/base.html` (модификация)

Добавить в sidebar для supervisor/admin:
```html
{% if current_user.role.value in ('supervisor', 'admin') %}
<a href="/reports" class="...">Аналитика</a>
{% endif %}
```

### 9. `scripts/export_report.py` (новый)

Standalone-скрипт:
```python
import asyncio
from app.database import init_db, async_session_maker
from app.services.report_service import (
    get_funnel_by_region, get_manager_kpi, get_funnel_bottlenecks
)
import pandas as pd

async def main():
    await init_db()
    async with async_session_maker() as session:
        funnel = await get_funnel_by_region(session)
        kpi = await get_manager_kpi(session)
        bottlenecks = await get_funnel_bottlenecks(session)
        
        output = f"storage/exports/report_{int(time.time())}.xlsx"
        os.makedirs("storage/exports", exist_ok=True)
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(funnel).to_excel(writer, sheet_name="Воронка", index=False)
            pd.DataFrame(kpi).to_excel(writer, sheet_name="KPI менеджеров", index=False)
            pd.DataFrame(bottlenecks).to_excel(writer, sheet_name="Просадки", index=False)
        print(f"Отчёт сохранён: {output}")

asyncio.run(main())
```

### 10. `app/main.py` (модификация)

```python
from app.routes import auth, dashboard, leads, tasks, documents, deals, reports
app.include_router(reports.router)
```

## Anti-conflict (важно для кодера)

**НЕ ТРОГАТЬ:**
- `app/models.py` — модели не меняются
- `app/auth.py`, `app/database.py`, `app/config.py`
- `app/services/document_service.py`, `app/services/funnel_service.py` — только импорт STAGES/STAGE_LABELS
- `Екатерина.xlsx`, `_Вероника.xlsx`, `.planning/`
- Существующие роуты auth.py, leads.py, tasks.py, documents.py — без изменений

**Модифицировать (аккуратно):**
- `app/routes/deals.py` — только добавление `.options(selectinload(Deal.lead))` в 2 функциях
- `app/routes/dashboard.py` — ветвление по роли
- `app/templates/base.html` — только sidebar
- `app/templates/dashboard.html` — блок тасков для manager
- `app/main.py` — только include_router

## Готово, когда (success criteria)

- [ ] D-01..D-18 — все выполнены
- [ ] `POST /leads/1/deals` — больше не возвращает 500 (долг D-G закрыт)
- [ ] `GET /reports` — дашборд супервайзера: воронка с CSS-барами, просадки с цветами, топ регионов
- [ ] `GET /reports/funnel` — таблица регион × стадия
- [ ] `GET /reports/managers` — KPI таблица, empty state при отсутствии менеджеров
- [ ] `GET /reports/export` — скачивается .xlsx с 3 листами
- [ ] `GET /reports` доступен только supervisor/admin; manager → 403
- [ ] Sidebar: «Аналитика» видна только supervisor/admin
- [ ] Дашборд менеджера (GET /): личные KPI (свои лиды, свои таски)
- [ ] Просадки с конверсией <25% — красные, <50% — жёлтые
- [ ] `python scripts/export_report.py` — создаёт .xlsx, печатает путь
- [ ] Нет `print` / `console.log` отладочного мусора (кроме в export скрипте)

## Не готово, когда

- `POST /leads/{id}/deals` всё ещё 500 (D-G не исправлен)
- `/reports` падает на пустых данных (0 менеджеров, 0 stage_history)
- Экспорт создаёт битый .xlsx или падает
- Воронка показывает 0 лидов при 583 в БД
- KPI менеджеров падает на NULL значениях
- Sidebar показывает «Аналитика» для manager

## Что даёт эта фаза

Супервайзер получает аналитический инструмент:
- ✅ **Воронка по стадиям** — визуальные CSS-бары + конверсия между стадиями
- ✅ **Воронка по регионам** — таблица регион × стадия
- ✅ **Просадки воронки** — цветовая индикация проблемных переходов
- ✅ **KPI менеджеров** — звонки, КП, конверсия за период
- ✅ **Экспорт в Excel** — 3 листа, готовый отчёт
- ✅ **Персонализированный дашборд** — manager видит свои данные, supervisor — общие
- ✅ **Долг Фазы 3 закрыт** — баг create_deal (D-G)

## Следующий шаг

Фаза 5 — Redesign: применение Visual Canon (Geist, Institutional Light, View/Edit B-Pattern, Risk Triage) ко всем экранам CRM.
