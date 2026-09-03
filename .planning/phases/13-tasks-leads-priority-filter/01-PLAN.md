---
phase: 13-tasks-leads-priority-filter
plan: "01"
slice: 13-01
type: execute
wave: 1
depends_on:
  - phase-7
requirements:
  - CRM-13-01
autonomous: true
files_modified:
  - app/routes/tasks.py
  - app/templates/tasks_leads.html
files_created: []
must_haves:
  truths:
    - "T-01: В сигнатуру роута tasks_leads_page (app/routes/tasks.py:340-346) добавлен НОВЫЙ параметр `priority: str = None` ПОСЛЕ `manager_id`. Сигнатура: `async def tasks_leads_page(request: Request, filter: str = \"total\", manager_id: int | None = None, priority: str = None, session: AsyncSession = Depends(get_session))`. Тип именно str (как в канбане leads.py:74) — нормализация в int делается отдельно. Это позволяет пустому значению из селекта (value=\"\") приходить как None, а невалидному ('abc') — отбрасываться без 500"
    - "T-02: Сразу после нормализации manager_id для роли manager (tasks.py:356-358) добавлена нормализация priority в int по образцу kanban (leads.py:86): `priority = int(priority) if priority and priority.isdigit() else None`. Это конвертирует '1'/'2'/'3' в int, пустую строку/None/нечисловой мусор → None. Без этого Lead.priority == priority сравнит int-колонку со строкой и не найдёт ничего"
    - "T-03: В вызове _query_leads_with_tasks (tasks.py:360) priority пробрасывается как новый позиционный/keyword-аргумент: `leads = await _query_leads_with_tasks(session, user, filter, manager_id, priority)`. Сигнатура хелпера _query_leads_with_tasks (tasks.py:78) расширена: `async def _query_leads_with_tasks(session, user, filter, manager_id=None, priority=None)`. Значение по умолчанию None сохраняет обратную совместимость (никто другой этот хелпер не вызывает — проверено grep'ом)"
    - "T-04: В ветке `if filter == \"no_tasks\"` хелпера _query_leads_with_tasks (tasks.py:83-93) к существующему `.where(lead_filter, Lead.stage != \"lost\", ~has_tasks)` ДОБАВЛЕНО условие по priority через расширение списка условий: при наличии priority — `.where(lead_filter, Lead.stage != \"lost\", ~has_tasks, Lead.priority == priority)`. Реализовать через условное расширение списка args: `conds = [lead_filter, Lead.stage != \"lost\", ~has_tasks]; if priority: conds.append(Lead.priority == priority); ... .where(*conds)`. НЕ использовать or_/and_ напрямую — конструкция `*conds` сохраняет AND-семантику как у существующего позиционного перечисления в .where()"
    - "T-05: Условие priority применяется ТОЛЬКО в ветке no_tasks. В остальных ветках (total/today/overdue) изменения НЕ вносятся — задача пользователя явно про «Лиды без задач». Если позже понадобится фильтр по priority в др. подменю — отдельная фаза. Дифф в ветках total/today/overdue = пустой"
    - "T-06: В context роута (tasks.py:377-385) добавлен ключ `\"priority\": priority,`. Это ОБЕ ветки ответа используют ОДИН context (HTMX и полная страница — tasks.py:388-396), поэтому priority попадает и в полный шаблон tasks_leads.html (для селекта), и в partials/tasks_leads_list.html (там не используется, но не мешает)"
    - "T-07: В app/templates/tasks_leads.html в форму фильтров (~стр. 9-19, тег `<form ... hx-get=\"/tasks/leads\" hx-target=\"#tasks-leads-list\" hx-trigger=\"change\" hx-include=\"this\">`) ДОБАВЛЕН второй `<select name=\"priority\">` ПОСЛЕ `<select name=\"manager_id\">`. Содержимое — точная копия kanban-селекта (kanban.html:48-54): option value=\"\" (Все приоритеты) + цикл `{% for p in [1, 2, 3] %}` с `{% if priority == p %}selected{% endif %}`. Класс Tailwind — идентичный существующему manager-селекту (`border border-black/10 rounded-lg px-3 py-1.5 text-sm text-ink bg-white`)"
    - "T-08: select priority НЕ обёрнут в role-gate — он виден ВСЕМ ролям (manager/supervisor/admin), как и в kanban.html:48-54 (там тоже нет role-gate на priority). Это сознательное решение для консистентности с канбаном: priority — бизнес-атрибут лида, а не ролевое ограничение. Только вся форма с manager_id обёрнута в `{% if current_user.role.value in ('supervisor', 'admin') %}` — это сохраняется как есть, НО select priority должен оказаться ВНЕ этого role-gate, иначе manager не увидит priority-фильтр. Решение: либо вынести select priority за пределы role-gate'а формы (в отдельную форму или до неё), либо снять role-gate с формы целиком и у manager_id сделать свой персональный role-gate. Рекомендация кодеру — ВАРИАНТ B: оставить форму с role-gate для supervisor/admin как есть, а select priority вынести в ОТДЕЛЬНУЮ мини-форму перед ней БЕЗ role-gate (меньше дифф, не ломает существующий UX)"
    - "T-09: Обе формы (priority без role-gate, manager_id+hidden filter с role-gate для supervisor/admin) имеют идентичные hx-атрибуты: `hx-get=\"/tasks/leads\"`, `hx-target=\"#tasks-leads-list\"`, `hx-swap=\"outerHTML\"`, `hx-trigger=\"change\"`, `hx-include=\"this\"`. Hidden input `name=\"filter\" value=\"{{ filter }}\"` повторяется в КАЖДОЙ форме (или используется общий — НО htmx `hx-include=\"this\"` сабмитит только свою форму, поэтому hidden filter обязан быть в каждой). Без этого смена priority без filter в URL сбросит подменю на дефолт (total)"
    - "T-10: При пустом значении priority (value=\"\" → None) выборка возвращает лидов ВСЕХ приоритетов, ВКЛЮЧАЯ лидов с priority=NULL в БД (Lead.priority nullable — models.py:82). Условие `if priority: conds.append(Lead.priority == priority)` при priority=None просто не добавляется — NULL-приоритетные лиды остаются в выдаче. Это правильно: «Все приоритеты» = буквально все, в т.ч. непроинициализированные"
  artifacts:
    - path: app/routes/tasks.py (модификация)
      provides: "параметр priority: str = None в tasks_leads_page; нормализация в int; проброс в _query_leads_with_tasks; расширение сигнатуры хелпера; WHERE Lead.priority == priority в ветке no_tasks через расширение списка условий; \"priority\": priority в context (обе ветки ответа)"
    - path: app/templates/tasks_leads.html (модификация)
      provides: "select name=\"priority\" (1/2/3 + Все приоритеты), виден всем ролям; либо отдельная мини-форма без role-gate перед формой manager_id, либо вынос select priority за пределы role-gate; идентичные hx-атрибуты; дублированный hidden input filter в каждой форме"
  key_links:
    - from: app/templates/tasks_leads.html (select priority)
      to: app/routes/tasks.py (tasks_leads_page)
      via: "HTMX-сабмит формы с hx-include=\"this\" → query-параметр priority попадает в роут"
      pattern: "Тот же механизм, что у manager_id — htmx сериализует поля формы автоматически, новый select добавляется без нового механизма"
    - from: app/routes/tasks.py (нормализация priority)
      to: app/routes/tasks.py (_query_leads_with_tasks WHERE)
      via: "priority (str) → int → проброс в хелпер → добавление Lead.priority == priority в список условий WHERE в ветке no_tasks"
      pattern: "Идентичен kanban (leads.py:74→86→109): str из URL → int-нормализация → AND-условие в WHERE"
    - from: app/routes/tasks.py (context)
      to: app/templates/tasks_leads.html (select priority)
      via: "\"priority\": priority в context → {% if priority == p %}selected{% endif %} в option — сохранение выбранного значения после HTMX-сабмита"
      pattern: "Сквозное сохранение фильтра через server-render, как в kanban.html:48-54"
---

# Plan 13-01 — Фильтр по приоритету в подменю «Лиды без задач»

**Phase:** 13 — tasks-leads-priority-filter
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

В разделе «Задачи» есть подменю «Лиды без задач» (`/tasks/leads?filter=no_tasks`) — список лидов без привязанных задач. Для ролей supervisor/admin там уже работает фильтр по менеджеру (`<select name="manager_id">` внутри HTMX-формы). На этой странице могут быть десятки лидов разных уровней важности, и менеджер/руководитель хочет быстро сузить выборку: «покажи только приоритет-1 лидов без задач» — чтобы первыми разобрать самые важные. Сейчас этого фильтра нет.

Задача (требование пользователя): **добавить в «Лиды без задач» фильтр по приоритету** (по аналогии с уже существующим фильтром по менеджеру).

**Root cause (подтверждено чтением кода):**
- Роут `tasks_leads_page` (`app/routes/tasks.py:340`) — единый для всех 4 подменю «Задачи», ветвление через query-параметр `filter`. Подменю «Лиды без задач» = `filter=no_tasks`, логика выбора в хелпере `_query_leads_with_tasks` (`tasks.py:78-94`).
- Существующий фильтр по менеджеру: query-параметр `manager_id: int | None` (`tasks.py:344`) → нормализация для роли manager → прокидывается в `_user_scope_filters(user, manager_id)` (`tasks.py:22-31`) → превращается в `Lead.assigned_manager_id == manager_id`. В шаблоне — `<select name="manager_id">` внутри HTMX-формы с `hx-get/hx-target/hx-trigger="change"/hx-include="this"` (`tasks_leads.html:11-17`).
- **Priority-фильтр уже реализован в канбане как готовый эталон** — `priority: str = None` в сигнатуре (`leads.py:74`) → нормализация `int(priority) if priority and priority.isdigit() else None` (`leads.py:86`) → `if priority: filters.append(Lead.priority == priority)` (`leads.py:109-110`) → `"priority": priority` в context (`leads.py:176`) → `<select name="priority">` (`kanban.html:48-54`). Можно скопировать схему 1-в-1.
- `Lead.priority` — `Mapped[Optional[int]]`, колонка `Integer`, nullable=True, значения 1/2/3 (`models.py:82`). Индекса нет (для объёмов CRM это не критично).
- **Мапинга priority → человекочитаемый текст в проекте НЕТ** (`grep` по priority_map/PRIORITY_MAP пусто). В kanban options рендерят сами числа (`{{ p }}` → «1/2/3»). Новая фаза НЕ вводит мапинг — оставляет числа, чтобы остаться консистентной с канбаном.

**Ключевое наблюдение:** задача — точное повторение существующего фильтра priority из канбана в новом месте. Готовых строительных блоков достаточно, новых архитектурных решений не требуется.

## Архитектура (обязательно к соблюдению)

**Фильтр priority в «Лидах без задач» по образцу канбана, применённый ТОЛЬКО к ветке `filter == "no_tasks"`.** Принципы:

1. **Параметр priority: str = None, не int.** Пустое значение из селекта (`value=""`) приходит как None, невалидное — отбрасывается нормализацией без 500. Это копия подхода из канбана (`leads.py:74,86`).

2. **Нормализация в int перед WHERE.** `Lead.priority == priority` сравнивает Integer-колонку; сравнение со строкой '1' ничего не найдёт. Нормализация идентична kanban: `int(priority) if priority and priority.isdigit() else None`.

3. **AND-семантика фильтра.** Priority работает совместно с `lead_filter` (менеджер/role-scope), `Lead.stage != "lost"`, `~has_tasks`. «Показать приоритет-1 лидов без задач моего региона» — корректный кейс. Расширение через список условий `conds.append(Lead.priority == priority)` и `*conds` в `.where()` сохраняет AND как у существующего кода.

4. **Только ветка `no_tasks`.** В задаче пользователя речь явно про подменю «Лиды без задач». В остальных 3 ветках (total/today/overdue) priority не вводим — это расширило бы scope без запроса. Дифф в тех ветках пустой.

5. **Селект priority виден всем ролям.** В kanban.html priority-селект не обёрнут в role-gate (доступен manager/supervisor/admin одинаково). Здесь повторяем: priority — бизнес-атрибут, не ролевое ограничение. Существующая форма с manager_id обёрнута в `{% if current_user.role.value in ('supervisor', 'admin') %}` — это сохраняется, но select priority должен оказаться вне этого role-gate (см. T-08 про реализацию).

6. **Сохранение выбранного значения после HTMX-сабмита.** В context кладётся `"priority": priority`, в шаблоне — `{% if priority == p %}selected{% endif %}`. После смены priority список перерисовывается HTMX, селект сохраняет выбранное значение (server-render, как в kanban).

7. **Hidden `filter` в каждой форме.** HTMX `hx-include="this"` сабмитит только свою форму. При смене priority обязательно прокинуть `filter=no_tasks` через `<input type="hidden" name="filter" value="{{ filter }}">` — иначе смена priority сбросит подменю на дефолт (total).

## Файлы

### 1. `app/routes/tasks.py` (модификация)

**(a) Сигнатура роута (~стр. 340-346)** — добавить `priority: str = None`:
```python
@router.get("/tasks/leads", response_class=HTMLResponse)
async def tasks_leads_page(
    request: Request,
    filter: str = "total",
    manager_id: int | None = None,
    priority: str = None,                              # ← НОВОЕ
    session: AsyncSession = Depends(get_session),
):
```

**(b) Нормализация priority** — сразу после блока нормализации manager для роли manager (~стр. 356-358):
```python
    # Менеджер всегда видит только свои задачи — игнорируем переданный manager_id
    if user.role.value == "manager":
        manager_id = None

    # Нормализация priority (как в kanban — leads.py:86)
    priority = int(priority) if priority and priority.isdigit() else None
```

**(c) Проброс priority в хелпер** — в вызове `_query_leads_with_tasks` (~стр. 360):
```python
    leads = await _query_leads_with_tasks(session, user, filter, manager_id, priority)
```

**(d) Расширение сигнатуры и логики хелпера** — `_query_leads_with_tasks` (~стр. 78-94):
```python
async def _query_leads_with_tasks(session, user, filter, manager_id=None, priority=None):
    task_filter, lead_filter = _user_scope_filters(user, manager_id)
    day_start, day_end = user_day_bounds(user)

    if filter == "no_tasks":
        has_tasks = exists(select(Task.id).where(Task.lead_id == Lead.id))
        conds = [lead_filter, Lead.stage != "lost", ~has_tasks]
        if priority:
            conds.append(Lead.priority == priority)
        result = await session.execute(
            select(Lead)
            .where(*conds)
            .options(selectinload(Lead.assigned_manager))
            .order_by(Lead.name)
        )
        return result.scalars().all()
    # ... остальные ветки (total/today/overdue) — БЕЗ ИЗМЕНЕНИЙ
```
> ⚠️ Рефакторить существующий `.where(lead_filter, Lead.stage != "lost", ~has_tasks)` в форму со списком `conds` + `*conds` — обязательно, иначе непонятно, куда добавлять priority. Это минимальный и читаемый способ. В остальных ветках хелпера priority НЕ применяется — дифф там пустой.

**(e) В context** — добавить `"priority": priority,` (~стр. 377-385):
```python
    context = {
        "current_user": user,
        "leads": leads,
        "filter": filter,
        "page_title": titles[filter],
        "stage_labels": STAGE_LABELS,
        "manager_id": manager_id,
        "priority": priority,                          # ← НОВОЕ
        "users": users,
    }
```
> Context один на обе ветки ответа (полная страница + HTMX-partial — tasks.py:388-396), поэтому priority попадает и в полный шаблон (для селекта), и в partial (там не используется, но не мешает).

### 2. `app/templates/tasks_leads.html` (модификация)

**Проблема структуры:** текущая форма с manager_id обёрнута в `{% if current_user.role.value in ('supervisor', 'admin') %}`. Если положить select priority внутрь неё — manager его не увидит (нарушит T-08). Поэтому **ВАРИАНТ B** (минимальный дифф, рекомендуется): form с manager_id остаётся как есть под role-gate, а select priority выносится в **отдельную мини-форму ПЕРВЫМ** — без role-gate, со своим hidden-filter:

```html
{% extends "base.html" %}
{% block title %}{{ page_title }} — CRM RAI{% endblock %}
{% block content %}
<h1 class="text-2xl font-medium mb-4 text-ink">{{ page_title }}</h1>

{# Фильтр по приоритету — ВИДЕН ВСЕМ ролям (как в kanban.html:48-54) #}
<form class="flex gap-3 mb-4 flex-wrap"
      hx-get="/tasks/leads" hx-target="#tasks-leads-list" hx-swap="outerHTML" hx-trigger="change"
      hx-include="this">
    <input type="hidden" name="filter" value="{{ filter }}">
    <select name="priority"
        class="border border-black/10 rounded-lg px-3 py-1.5 text-sm text-ink bg-white">
        <option value="">Все приоритеты</option>
        {% for p in [1, 2, 3] %}
        <option value="{{ p }}" {% if priority == p %}selected{% endif %}>{{ p }}</option>
        {% endfor %}
    </select>
</form>

{# Фильтр по менеджеру — только supervisor/admin (как и раньше) #}
{% if current_user.role.value in ('supervisor', 'admin') %}
<form class="flex gap-3 mb-4 flex-wrap"
      hx-get="/tasks/leads" hx-target="#tasks-leads-list" hx-swap="outerHTML" hx-trigger="change"
      hx-include="this">
    <input type="hidden" name="filter" value="{{ filter }}">
    <select name="manager_id"
        class="border border-black/10 rounded-lg px-3 py-1.5 text-sm text-ink bg-white">
        <option value="">Все менеджеры</option>
        {% for u in users %}
        <option value="{{ u.id }}" {% if manager_id == u.id %}selected{% endif %}>{{ u.full_name }}</option>
        {% endfor %}
    </select>
</form>
{% endif %}

{% include "partials/tasks_leads_list.html" %}
{% endblock %}
```

> **Пояснения:**
> - Две отдельные формы — потому что htmx `hx-include="this"` сабмитит только свою форму. Объединить их в одну можно ТОЛЬКО если снять role-gate с manager_id (тогда manager увидит чужих лидов через фильтр — **нарушит бизнес-логику**, НЕЛЬЗЯ). Вариант B — два независимых HTMX-селекта, каждый сабмитит `filter + своё поле`, роут собирает оба query-параметра при каждом запросе (несуществующие параметры приходят как None).
> - Hidden `<input type="hidden" name="filter" value="{{ filter }}">` — в КАЖДОЙ форме обязателен. При смене priority сервер должен знать, что мы в `filter=no_tasks`, иначе вернёт дефолт `total` (пустой список, т.к. total — задачи на сегодня, а в no_tasks лиды без задач).
> - Class Tailwind на select priority — идентичный manager-селекту и kanban priority-селекту: визуальная консистентность.
> - `{% if priority == p %}selected{% endif %}` — сохранение выбранного значения после HTMX-сабмита. priority из context приходит как int (после нормализации) или None; сравнение `priority == 1/2/3` работает корректно.

> ⚠️ **Альтернатива (если кодер считает две формы уродливыми):** можно сделать ОДНУ форму без role-gate, в ней оба select'а, а manager_id-селект дополнительно обернуть в inline `{% if current_user.role.value in ('supervisor', 'admin') %}...{% endif %}`. Тогда manager видит форму, но manager_id-селект отсутствует — и при сабмите он не придёт (_htmx отправляет только существующие поля формы_). Этот вариант тоже валиден, выберет кодер по читаемости. Главное требование: select priority доступен всем ролям.

## Шаги выполнения

1. `app/routes/tasks.py`:
   - Добавить `priority: str = None` в сигнатуру `tasks_leads_page`.
   - Добавить нормализацию `priority = int(...) if ... else None` после блока manager-нормализации.
   - Расширить сигнатуру `_query_leads_with_tasks(..., priority=None)`.
   - В ветке `no_tasks` собрать `conds = [...]`, при `priority` добавить `Lead.priority == priority`, передать `.where(*conds)`. Остальные ветки НЕ трогать.
   - Прокинуть `priority` в вызов `_query_leads_with_tasks`.
   - Добавить `"priority": priority` в context.
2. `app/templates/tasks_leads.html`:
   - Добавить отдельную HTMX-форму с select priority (без role-gate) ПЕРВЫМ, перед формой manager_id. Hidden-filter в каждой форме.
   - (Альтернатива — inline role-gate на manager_id внутри общей формы.)
3. Ручная проверка сценариев (см. Acceptance).

## Acceptance criteria (gate)

- [ ] В подменю «Лиды без задач» (`/tasks/leads?filter=no_tasks`) появился селект «Все приоритеты / 1 / 2 / 3».
- [ ] Селект priority виден ВСЕМ ролям — проверить логином manager, supervisor, admin. У manager он ЕСТЬ (в отличие от manager_id-селекта, которого у manager нет).
- [ ] Выбор «1» → список содержит только лидов с `priority=1` (и без задач). Проверить в DevTools/Network, что запрос ушёл с `?filter=no_tasks&priority=1`, и в ответе только priority=1 лиды.
- [ ] Выбор «Все приоритеты» (value="") → список возвращается к полному набору, ВКЛЮЧАЯ лидов с priority=NULL в БД (Lead.priority nullable — models.py:82). Проверить: если в БД есть лид без задач и с priority=NULL, он виден при «Все приоритеты».
- [ ] Селект сохраняет выбранное значение после HTMX-сабмита (selected подсвечивается правильно). Проверить для каждого из 1/2/3.
- [ ] Фильтр priority работает СОВМЕСТНО с manager_id для supervisor/admin: выбрать manager_id=X + priority=1 → только лиды менеджера X приоритета 1 без задач. Оба селекта сохраняют свои значения после перерисовки.
- [ ] Смена priority НЕ сбрасывает `filter` в URL — в Network всегда `filter=no_tasks`. Проверить: на странице `/tasks/leads?filter=no_tasks` сменить priority → URL/запрос остаётся `filter=no_tasks`.
- [ ] Смена manager_id НЕ сбрасывает priority (и наоборот): выбрать priority=2, потом сменить менеджера → priority=2 сохраняется.
- [ ] Подменю total/today/overdue НЕ сломаны: селект priority на них НЕ появляется (он только в no_tasks — по архитектуре), ИЛИ если кодер сделал его видимым везде — то он корректно применяется только в no_tasks, а в остальных ветках игнорируется. Дифф в total/today/overdue ветках `_query_leads_with_tasks` — пустой.
- [ ] URL `/tasks/leads?filter=no_tasks&priority=2` открытый напрямую (не через HTMX) — отдаёт страницу с priority=2 в селекте и отфильтрованным списком (server-render корректный).
- [ ] Невалидный `priority=abc` в URL — не падает с 500, отдаёт «Все приоритеты» (нормализация → None).
- [ ] В канбане фильтр priority (`/kanban?priority=...`) остался рабочим — изменения НЕ задели `leads.py` (эта фаза правит только `tasks.py`).

## Не делаем (YAGNI)

- **НЕ применяем priority в ветках total/today/overdue** — задача явно про «Лиды без задач». Расширение на остальные подменю — отдельная фаза, если будет запрос.
- **НЕ вводим priority_map / человекочитаемые подписи** («Высокий/Средний/Низкий») — в kanban priority отображается числами 1/2/3, новая фаза остаётся консистентной. Если заказчик захочет подписи — это затронет и kanban, отдельная фаза.
- **НЕ делаем сохранение фильтров при переходе в карточку лида и обратно** (аналог `build_kanban_query` из фаз 8-9). Сейчас в `partials/tasks_leads_list.html` ссылки `<a href="/leads/{{ lead.id }}">` вообще не несут query-параметров — это существующее поведение, не часть текущей задачи. Если понадобится persist — отдельная фаза с `build_tasks_leads_query` хелпером по образцу kanban.
- **НЕ добавляем индекс на Lead.priority** — для текущих объёмов CRM Sequential scan в WHERE приемлем, это over-engineering для MVP.
- **НЕ добавляем priority-фильтр в канбан** — там он уже есть (`kanban.html:48-54`, `leads.py:74,86,109`). Эта фаза его НЕ трогает.
- **НЕ трогаем** `partials/tasks_leads_list.html`, `sidebar_tasks_menu.html`, `sidebar_tasks.js`, `base.html` — изменения только в `tasks.py` и `tasks_leads.html`.
- **НЕ добавляем priority в счётчики сайдбара** (`{{ counts.leads_without_tasks }}` в `sidebar_tasks_menu.html`) — счётчик остаётся общим, фильтр priority — только на самой странице.
- **НЕ делаем multi-select priority** (1+3 одновременно) — один select = одно значение, как в kanban. Multi — отдельная UX-задача.
