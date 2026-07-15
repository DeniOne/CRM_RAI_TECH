---
phase: 7-tasks-sidebar-menu
plan: "01"
slice: 7-01
type: execute
wave: 1
depends_on:
  - phase-5
requirements:
  - CRM-7-01
autonomous: true
files_modified:
  - app/templates/base.html
  - app/routes/tasks.py
files_created:
  - app/templates/tasks_leads.html
  - app/templates/partials/sidebar_tasks_menu.html
  - app/static/js/sidebar_tasks.js
must_haves:
  truths:
    - "T-01: В app/templates/base.html пункт «Задачи» (стр. 51) превращён в раскрывающуюся группу: кликабельный заголовок «Задачи» с шевроном (▸ свёрнуто / ▾ развёрнуто) и контейнером подменю. По умолчанию группа РАЗВЁРНУТА. Состояние (свёрнуто/развёрнуто) сохраняется в localStorage между перезагрузками"
    - "T-02: Под заголовком «Задачи» — 4 подменю, каждый ведёт на /tasks/leads?filter=<value> и содержит справа бейдж с актуальным числом: «Всего задач» (filter=total), «Сегодня» (filter=today), «Просроченные» (filter=overdue), «Лиды без задач» (filter=no_tasks)"
    - "T-03: Бейджи счётчиков грузятся lazily через fetch GET /api/tasks/sidebar → заполнение контейнера #sidebar-tasks-counts, по паттерну существующего тикера (app/static/js/ticker.js → /api/ticker). НЕ прокидывать счётчики в контекст каждого view (общего context processor нет, это антипаттерн для проекта)"
    - "T-04: Скелетон-плейсхолдер «…» в бейджах до загрузки счётчиков; при ошибке загрузки — тихий фолбэк (пустой бейдж), не ломать страницу (как ticker.js)"
    - "T-05: Скоуп по ролям для счётчиков И списков: manager — только свои задачи (Task.assigned_to == user.id) и свои лиды (Lead.assigned_manager_id == user.id); supervisor/admin — всех менеджеров (без фильтра по user). Та же логика, что в app/routes/ticker.py (ветка manager vs supervisor)"
    - "T-06: ACTIVE_STATUSES импортируется из app/routes/ticker.py (там константа ('pending','in_progress')). НЕ дублировать определение. Границы суток — user_day_bounds(user) из app/tz_utils.py (TZ-корректно). НЕ использовать datetime.now() напрямую"
    - "T-07: GET /tasks/leads?filter={total|today|overdue|no_tasks} — новый роут в app/routes/tasks.py. Возвращает полный HTML (extends base.html) со списком ЛИДОВ, сгруппированных по лиду (каждый лид = блок, внутри — его задачи через {% include 'partials/task_row.html' %})"
    - "T-08: Семантика фильтров списка /tasks/leads строго соответствует счётчикам (единые WHERE-условия, чтобы число и список сходились): total→все активные задачи; today→active tasks где due_date IS NULL OR day_start <= due_date <= day_end; overdue→active tasks где due_date IS NOT NULL AND due_date < day_start; no_tasks→активные лиды (stage != 'lost') без ни одной Task"
    - "T-09: «Лиды без задач» (filter=no_tasks) — только активные лиды: Lead.stage != 'lost' (стадии из funnel_service: '0'..'7' активные, 'lost' потерян). Считать лидов, у которых NOT EXISTS (Task.lead_id == Lead.id)"
    - "T-10: Блок лида на странице /tasks/leads: имя лида (ссылка /leads/{id}), бейдж стадии (STAGE_LABELS), для supervisor/admin — имя менеджера. Список задач внутри — инклуд task_row.html. Для filter=no_tasks блоки задач нет (только список лидов)"
    - "T-11: Активное подменю подсвечивается: JS в sidebar_tasks.js парсит location.search (?filter=...) и выставляет класс активного пункта (bg-slate-100 font-medium) на соответствующем подменю"
    - "T-12: Существующий роут GET /tasks и страница tasks.html НЕ ТРОГАЮТСЯ — остаются рабочими. Раскрывающееся меню лишь добавляет быстрые переходы"
    - "T-13: partials/task_row.html переиспользуется без правок — ему нужны только переменные task и current_user (проверить, что в контексте цикла они есть)"
    - "T-14: Стили раскрывающегося меню консистентны с Visual Canon (фаза 5): bg-white sidebar, text-ink, hover:bg-slate-100, бейдж счётчика — bg-slate-100 text-muted rounded-full text-xs. Активный пункт — bg-slate-100 font-medium. Никакого font-bold/bg-blue-600"
  artifacts:
    - path: app/static/js/sidebar_tasks.js
      provides: "loadSidebarCounts() — lazy-загрузка счётчиков через /api/tasks/sidebar; toggleSidebarSection() — свернуть/развернуть; подсветка активного подменю по ?filter="
    - path: app/templates/partials/sidebar_tasks_menu.html
      provides: "Partial с 4 подменю и бейджами счётчиков — ответ /api/tasks/sidebar"
    - path: app/templates/tasks_leads.html
      provides: "Страница списка лидов с задачами, сгруппированных по лиду — extends base.html"
    - path: app/routes/tasks.py (модификация)
      provides: "GET /api/tasks/sidebar (счётчики) + GET /tasks/leads (список лидов) + хелперы _task_counts/_query_leads_with_tasks"
  key_links:
    - from: app/templates/base.html
      to: app/static/js/sidebar_tasks.js
      via: "<script src='/static/js/sidebar_tasks.js'></script> рядом с ticker.js"
      pattern: "Lazy-loaded sidebar counts (как тикер)"
    - from: app/routes/tasks.py
      to: app/routes/ticker.py
      via: "from app.routes.ticker import ACTIVE_STATUSES + from app.tz_utils import user_day_bounds"
      pattern: "Единое место истины для активных статусов и границ суток"
    - from: app/templates/tasks_leads.html
      to: app/templates/partials/task_row.html
      via: "{% include 'partials/task_row.html' %} в цикле по lead.tasks"
      pattern: "Переиспользование строки задачи"
---

# Plan 7-01 — Раскрывающееся меню «Задачи» в sidebar со счётчиками и списками лидов

**Phase:** 7 — tasks-sidebar-menu
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

Сейчас в боковом меню (`app/templates/base.html`, стр. 51) «Задачи» — плоский пункт-ссылка на `/tasks`. Пользователю нужны быстрые срезы: сколько всего активных задач, сколько на сегодня, сколько просрочено, сколько лидов без задач — с актуальными числами прямо в меню и переходом по клику на список лидов с этими задачами.

Логика «активные / на сегодня / просрочено» уже реализована TZ-корректно в тикере (`app/routes/ticker.py` + `app/tz_utils.py`). Проект использует паттерн lazy-загрузки данных sidebar через htmx/fetch (`/api/ticker` → `ticker.js`). Эту фазу делаем в том же паттерне — без общего context processor (его в проекте нет, и прокидывать счётчики в каждый view — антипаттерн).

## Архитектура (обязательно к соблюдению)

1. **Счётчики в sidebar** грузятся lazily: `fetch('/api/tasks/sidebar')` на `DOMContentLoaded` заполняет `#sidebar-tasks-counts` (как `ticker.js` грузит `#task-ticker`). Это позволяет НЕ трогать контекст ни одного существующего view.
2. **Единое место истины** для «активные статусы» и «границы суток»: `ACTIVE_STATUSES` импортируется из `app/routes/ticker.py`, `user_day_bounds()` — из `app/tz_utils.py`. **Запрещено** дублировать формулу или использовать `datetime.now()`.
3. **Счётчик и список сходятся**: и `/api/tasks/sidebar`, и `/tasks/leads?filter=...` используют общие хелперы `_task_counts()` и `_query_leads_with_tasks()` с одинаковыми WHERE-условиями. Это исключает рассинхрон «цифра 32, а в списке 30».

## Скоуп по ролям (критично)

- **manager** — видит только свои задачи (`Task.assigned_to == user.id`) и своих лидов (`Lead.assigned_manager_id == user.id`).
- **supervisor / admin** — видит задачи и лидов ВСЕХ менеджеров (без фильтра по user). Полностью повторяет логику ветвления в `ticker.py` (стр. 40: `if user.role.value == "manager"` vs else).

## Файлы

### 1. `app/routes/tasks.py` (модификация) — новые эндпоинты + хелперы

**Импорты (вверху файла):**
```python
from sqlalchemy import select, func
from app.models import Task, Lead
from app.routes.ticker import ACTIVE_STATUSES  # НЕ дублировать константу
from app.tz_utils import user_day_bounds
from app.services.funnel_service import STAGE_LABELS
```

**Хелпер `_user_scope_filters(user)`** — возвращает пару `(task_filter, lead_filter)`:
- manager: `(Task.assigned_to == user.id, Lead.assigned_manager_id == user.id)`
- supervisor/admin: `(True, True)`

**Хелпер `async def _task_counts(session, user) -> dict`** — 4 count-запроса:
```python
{
  "total": <active tasks in scope>,
  "today": <active tasks in scope, due_date IS NULL OR day_start <= due_date <= day_end>,
  "overdue": <active tasks in scope, due_date IS NOT NULL AND due_date < day_start>,
  "leads_without_tasks": <активные лиды (stage != 'lost') in lead-scope, без ни одной Task>,
}
```
`day_start, day_end = user_day_bounds(user)`. Использовать SQL `func.count()` с `.scalar()`, НЕ грузить объекты в Python.

Для `leads_without_tasks` — `NOT EXISTS` подзапрос:
```python
has_tasks = select(Task.lead_id).where(Task.lead_id == Lead.id)
leads_without = await session.scalar(
    select(func.count(Lead.id)).where(
        lead_filter,
        Lead.stage != "lost",
        ~has_tasks.exists()
    )
)
```

**Эндпоинт `GET /api/tasks/sidebar`** (response_class=HTMLResponse):
- `user = await get_current_user(...)`; 401 если нет.
- `counts = await _task_counts(session, user)`.
- Рендерит `partials/sidebar_tasks_menu.html` с `counts` (и `current_user`).

**Эндпоинт `GET /tasks/leads`** (response_class=HTMLResponse, query-параметр `filter: str = "total"`):
- `filter in ("total","today","overdue","no_tasks")`, иначе 422.
- Для `total/today/overdue`: запрос лидов, у которых есть активные задачи под фильтр, с eager-load `lead.tasks` (только подходящие задачи). Группировка по лиду.
- Для `no_tasks`: запрос активных лидов без задач (`Lead.stage != "lost"`, NOT EXISTS task).
- Для supervisor/admin — добавить join к `User` для имени менеджера в блоке лида.
- Рендерит `tasks_leads.html` с `{leads, filter, current_user, stage_labels}`.

### 2. `app/templates/partials/sidebar_tasks_menu.html` (новый) — ответ `/api/tasks/sidebar`

4 подменю. Каждое — ссылка `<a href="/tasks/leads?filter=...">` с текстом и бейджем справа. Классы для подсветки активного пункта добавляет JS (по `data-filter`).

```html
{# Рендерится в #sidebar-tasks-counts. counts = {total, today, overdue, leads_without_tasks} #}
<a href="/tasks/leads?filter=total"
   data-filter="total"
   class="sidebar-subitem flex items-center justify-between pl-6 pr-3 py-1.5 rounded-lg text-sm text-ink hover:bg-slate-100">
    <span>Всего задач</span>
    <span class="bg-slate-100 text-muted rounded-full text-xs px-2 py-0.5">{{ counts.total }}</span>
</a>
<a href="/tasks/leads?filter=today" data-filter="today" class="sidebar-subitem flex items-center justify-between pl-6 pr-3 py-1.5 rounded-lg text-sm text-ink hover:bg-slate-100">
    <span>Сегодня</span>
    <span class="bg-slate-100 text-muted rounded-full text-xs px-2 py-0.5">{{ counts.today }}</span>
</a>
<a href="/tasks/leads?filter=overdue" data-filter="overdue" class="sidebar-subitem flex items-center justify-between pl-6 pr-3 py-1.5 rounded-lg text-sm text-ink hover:bg-slate-100">
    <span>Просроченные</span>
    <span class="bg-slate-100 text-muted rounded-full text-xs px-2 py-0.5">{{ counts.overdue }}</span>
</a>
<a href="/tasks/leads?filter=no_tasks" data-filter="no_tasks" class="sidebar-subitem flex items-center justify-between pl-6 pr-3 py-1.5 rounded-lg text-sm text-ink hover:bg-slate-100">
    <span>Лиды без задач</span>
    <span class="bg-slate-100 text-muted rounded-full text-xs px-2 py-0.5">{{ counts.leads_without_tasks }}</span>
</a>
```

### 3. `app/templates/base.html` (модификация) — раскрывающаяся группа

Заменить строку 51:
```html
<a href="/tasks" class="block px-3 py-2 rounded-lg text-sm text-ink hover:bg-slate-100">Задачи</a>
```
на раскрывающуюся группу (id для JS):
```html
<div class="sidebar-group" id="tasks-sidebar-group">
    <button type="button"
            onclick="toggleSidebarSection('tasks-sidebar-group')"
            class="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium text-ink hover:bg-slate-100">
        <span>Задачи</span>
        <svg class="sidebar-chevron w-4 h-4 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
        </svg>
    </button>
    <div class="sidebar-children space-y-0.5 mt-0.5" id="sidebar-tasks-counts">
        {# Скелетон-плейсхолдеры до загрузки /api/tasks/sidebar #}
        <div class="pl-6 pr-3 py-1.5 text-sm text-muted">…</div>
    </div>
</div>
```
И подключить JS перед `</body>` рядом с ticker.js:
```html
<script src="/static/js/sidebar_tasks.js"></script>
```

### 4. `app/static/js/sidebar_tasks.js` (новый)

```js
/* Раскрывающееся меню «Задачи» в sidebar + lazy-загрузка счётчиков.
 * Паттерн как ticker.js: fetch на DOMContentLoaded, тихий фолбэк при ошибке. */
(function () {
    "use strict";

    var STORAGE_KEY = "sidebar-tasks-open";

    /* ---- Раскрытие/сворачивание ---- */
    window.toggleSidebarSection = function (groupId) {
        var group = document.getElementById(groupId);
        if (!group) return;
        var children = group.querySelector(".sidebar-children");
        var chevron = group.querySelector(".sidebar-chevron");
        var isOpen = !group.classList.contains("collapsed");

        if (isOpen) {
            group.classList.add("collapsed");
            children.style.display = "none";
            if (chevron) chevron.style.transform = "rotate(-90deg)";
            localStorage.setItem(STORAGE_KEY, "0");
        } else {
            group.classList.remove("collapsed");
            children.style.display = "";
            if (chevron) chevron.style.transform = "";
            localStorage.setItem(STORAGE_KEY, "1");
        }
    };

    /* Восстановление состояния из localStorage (по умолчанию развёрнуто) */
    function restoreState() {
        var group = document.getElementById("tasks-sidebar-group");
        if (!group) return;
        if (localStorage.getItem(STORAGE_KEY) === "0") {
            // имитация клика для сворачивания
            window.toggleSidebarSection("tasks-sidebar-group");
        }
    }

    /* ---- Lazy-загрузка счётчиков ---- */
    function loadCounts() {
        var box = document.getElementById("sidebar-tasks-counts");
        if (!box || box.dataset.loaded) return;
        fetch("/api/tasks/sidebar", { headers: { "HX-Request": "true" }, credentials: "same-origin" })
            .then(function (r) { if (!r.ok) throw new Error("sidebar HTTP " + r.status); return r.text(); })
            .then(function (html) {
                box.innerHTML = html;
                box.dataset.loaded = "1";
                highlightActive();
            })
            .catch(function () { box.dataset.loaded = "error"; /* тихо, как тикер */ });
    }

    /* ---- Подсветка активного подменю по ?filter= в URL ---- */
    function highlightActive() {
        var params = new URLSearchParams(window.location.search);
        var filter = params.get("filter");
        if (!filter) return;
        var item = document.querySelector('.sidebar-subitem[data-filter="' + filter + '"]');
        if (item) item.classList.add("bg-slate-100", "font-medium");
    }

    document.addEventListener("DOMContentLoaded", function () {
        restoreState();
        loadCounts();
    });
})();
```

### 5. `app/templates/tasks_leads.html` (новый) — страница списка лидов

```html
{% extends "base.html" %}
{% block title %}{{ page_title }} — CRM RAI{% endblock %}
{% block content %}
<h1 class="text-2xl font-medium mb-4 text-ink">{{ page_title }}</h1>

<div class="space-y-4">
    {% for lead in leads %}
    <div class="bg-white border border-black/10 rounded-2xl p-4">
        <div class="flex items-center justify-between mb-2">
            <a href="/leads/{{ lead.id }}" class="text-base font-medium text-ink hover:underline">{{ lead.name }}</a>
            <div class="flex items-center gap-2">
                {% if lead._manager_name %}<span class="text-xs text-muted">{{ lead._manager_name }}</span>{% endif %}
                <span class="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-muted">{{ stage_labels.get(lead.stage, lead.stage) }}</span>
            </div>
        </div>
        {% if filter != 'no_tasks' %}
        <div class="space-y-1">
            {% for task in lead._tasks %}
            {% include "partials/task_row.html" %}
            {% endfor %}
        </div>
        {% endif %}
    </div>
    {% else %}
    <div class="flex flex-col items-center justify-center py-12 text-center">
        <svg class="w-12 h-12 text-muted/30 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/>
        </svg>
        <div class="text-sm text-muted mb-3">Ничего не найдено</div>
    </div>
    {% endfor %}
</div>
{% endblock %}
```

**Важно по данным:** в `_query_leads_with_tasks()` (view) отфильтрованные задачи лида класть в `lead._tasks` (временный атрибут), а не читать `lead.tasks` целиком — иначе для `today` покажутся и просроченные тоже. Для supervisor/admin — `lead._manager_name` через join к User.

## Шаги выполнения

1. **Хелперы + импорты** в `tasks.py`: `_user_scope_filters`, `_task_counts`, `_query_leads_with_tasks`. Импорт `ACTIVE_STATUSES` из ticker.py, `user_day_bounds` из tz_utils.
2. **Эндпоинт `GET /api/tasks/sidebar`** + `partials/sidebar_tasks_menu.html`.
3. **Эндпоинт `GET /tasks/leads`** + `tasks_leads.html`.
4. **`base.html`** — раскрывающаяся группа + подключение `sidebar_tasks.js`.
5. **`sidebar_tasks.js`** — toggle, restoreState, loadCounts, highlightActive.
6. Проверка: manager и supervisor видят разные скоупы; счётчик и список сходятся; старый `/tasks` работает; раскрывается/сворачивается с сохранением состояния.

## Acceptance criteria (gate)

- [ ] «Задачи» в sidebar — раскрывающаяся группа с 4 подменю, у каждого бейдж с числом.
- [ ] Числа грузятся lazily (скелетон `…` → реальные числа), не требуют правок других view.
- [ ] manager видит свои счётчики, supervisor/admin — всех менеджеров.
- [ ] Клик по подменю открывает `/tasks/leads?filter=...` со списком лидов, сгруппированных по лиду.
- [ ] Число в бейдже = кол-во лидов/задач в соответствующем списке (рассинхрон = FAIL).
- [ ] «Лиды без задач» — только активные лиды (`stage != "lost"`).
- [ ] Границы суток TZ-корректны (`user_day_bounds`, не `datetime.now()`).
- [ ] `ACTIVE_STATUSES` импортирован из ticker.py (grep: определение ровно одно).
- [ ] Старый `/tasks` работает без изменений.
- [ ] Раскрытие/сворачивание сохраняется в localStorage; активное подменю подсвечивается.
- [ ] Стили консистентны с Visual Canon (font-medium, text-ink, bg-slate-100, без font-bold/bg-blue-600).

## Не делаем (YAGNI)

- НЕ вводим общий context processor для всех view.
- НЕ делаем пагинацию списков (объёмы малые; если понадобится — отдельной фазой).
- НЕ трогаем модель данных Task/Lead.
- НЕ добавляем автообновление счётчиков в реальном времени (как тикер — грузятся один раз на страницу; обновятся при следующей навигации).
