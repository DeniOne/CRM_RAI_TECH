---
phase: 9-kanban-search
plan: "01"
slice: 9-01
type: execute
wave: 1
depends_on:
  - phase-2
  - phase-8
requirements:
  - CRM-9-01
autonomous: true
files_modified:
  - app/routes/leads.py
  - app/templates/kanban.html
  - app/templates/partials/kanban_board.html
files_created: []
must_haves:
  truths:
    - "T-01: В роут /kanban (app/routes/leads.py:66-75) добавлен опциональный query-параметр `q: str = None`. После нормализации (рядом со leads.py:82-85) — `q = (q or '').strip() or None`. Поиск — доп. фильтр, НЕ отдельный режим: работает совместно с region/level/priority/manager/assigned_manager (AND-цепочка остаётся)"
    - "T-02: В тело роута kanban (после сборки `filters`, ~app/routes/leads.py:97-112) добавлен ILIKE-фильтр по совпадению в нескольких полях таблицы leads: `if q: filters.append(or_(Lead.name.ilike(f\"%{q}%\"), Lead.inn.ilike(f\"%{q}%\"), Lead.head_name.ilike(f\"%{q}%\"), Lead.site.ilike(f\"%{q}%\"), Lead.settlement.ilike(f\"%{q}%\")))`. Использовать `sqlalchemy.or_`. Регистронезависимый поиск (ilike). Точных полей по Contact (phone/email) в MVP НЕ делать — требует join и выходит за рамки задачи"
    - "T-03: В хелпере build_kanban_query (app/routes/leads.py:49-63) параметр `q` добавлен в сигнатуру последним и собирается в query-строку: `if q: params.append(f\"q={q}\")`. Без этого поиск теряется при клике на лида и возврате обратно (фаза 8 это уже regulates — q обязан жить в том же едином источнике истины, что и остальные фильтры)"
    - "T-04: В точке вызова build_kanban_query (~app/routes/leads.py:93) передаётся `q` наряду с region/level/priority/manager/assigned_manager. kanban_query (уже с q) кладётся в context ОБЕИХ веток ответа /kanban — полной (leads.py:150-165) и HTMX-фрагмента (leads.py:143-148). Это критично: HTMX-ветка сегодня отдаёт только stages + kanban_query, q пойдёт именно через kanban_query — отдельно в HTMX-context его класть НЕ надо"
    - "T-05: В полной ветке context (leads.py:150-165) добавлен ключ `\"q\": q` — чтобы инпут поиска сохранял введённое значение после сабмита (value=\"{{ q or '' }}\"). Для HTMX-ветки отдельно q не кладётся — значение инпута живёт в самой форме и не перерисовывается при swap доски"
    - "T-06: В app/templates/kanban.html внутри формы #kanban-filters (~стр. 26-65) добавлен текстовый инпут поиска ПЕРВЫМ элементом формы (слева, как основной способ фильтрации): `<input type=\"search\" name=\"q\" value=\"{{ q or '' }}\" placeholder=\"Поиск по названию, ИНН, руководителю, сайту, городу\" class=\"...\">`. Атрибут `name=\"q\"` — попадает в запрос через `hx-include=\"this\"` (форма уже сабмитит всю себя)"
    - "T-07: Инпут поиска триггерит HTMX-обновление доски при вводе, а не по blur/Enter. На форме #kanban-filters (kanban.html:26) текущий `hx-trigger=\"change\"` расширен ДО `hx-trigger=\"change, keyup changed delay:400ms from:find input[name='q']\"`. Пояснение: `change` остаётся для селектов (region/level/priority/manager), а `keyup changed delay:400ms from:find input[name='q']` даёт живой поиск с debounce 400мс ТОЛЬКО по инпуту q. НЕ ставить `keyup` на всю форму — это сломает ввод в др. полях и вызовет лишние запросы"
    - "T-08: (опционально, делает кодер если помещается без усложнения) В app/templates/partials/kanban_board.html:11 имя лида подсвечивает совпадение, если в context есть q. Jinja-фильтр или inline-логика через `{{ lead.name | replace(q, '<mark>' ~ q ~ '</mark>') | safe }}` — ТОЛЬКО когда q задано. Подсветка не должна ломать truncate. Если усложняет — пропустить (не блокер)"
    - "T-09: Серверная логика фильтрации по region/level/priority/manager/assigned_manager (leads.py:92-117) НЕ изменена — поиск только добавляет ещё один AND-фильтр. diff в этой зоне пустой за исключением新增ленного блока `if q: filters.append(...)`"
    - "T-10: Drag-and-drop смены стадии (app/static/js/kanban.js, htmx:afterSwap на #kanban-board) не сломан при живом поиске: после ввода в инпут HTMX перерисовывает #kanban-board, Sortable реинициализируется как раньше. Проверить вручную: ввести запрос → перетащить найденного лида в другую стадию → стадия меняется"
    - "T-11: Поиск доступен всем ролям (manager/supervisor/admin) одинаково — параметр q не зависит от role-based scope. Для manager поиск работает в рамках его scope (manager='my'), для supervisor/admin — в рамках выбранного scope + assigned_manager. Это гарантируется тем, что q — просто доп. AND-условие к уже собранному filters"
  artifacts:
    - path: app/routes/leads.py (модификация)
      provides: "опциональный q в сигнатуре /kanban; нормализация q; ILIKE-фильтр (or_ по name/inn/head_name/site/settlement); q в build_kanban_query; q в context полной ветки"
    - path: app/templates/kanban.html (модификация)
      provides: "инпут <input type=\"search\" name=\"q\"> первым в форме #kanban-filters; расширение hx-trigger формы до `change, keyup changed delay:400ms from:find input[name='q']`"
    - path: app/templates/partials/kanban_board.html (опциональная модификация)
      provides: "подсветка совпадения <mark> в имени лида при наличии q (только если делается тривиально)"
  key_links:
    - from: app/templates/kanban.html (инпут q)
      to: app/routes/leads.py (/kanban)
      via: "HTMX-сабмит формы с hx-include=\"this\" → query-параметр q попадает в роут"
      pattern: "Форма уже сериализует все поля; q добавляется без нового механизма"
    - from: app/routes/leads.py (build_kanban_query)
      to: app/templates/partials/kanban_board.html (ссылка лида)
      via: "q попадает в kanban_query → ссылка /leads/{id}?...&q=... → переход в лида и возврат сохраняет поиск"
      pattern: "Сквозная передача поиска через тот же механизм, что и фильтры фазы 8"
    - from: app/routes/leads.py (filters + or_)
      to: SQL
      via: "filters.append(or_(Lead.name.ilike(...), ...)) — доп. AND-условие к существующей цепочке"
      pattern: "Поиск не отдельный режим, а доп. фильтр в той же выборке"
---

# Plan 9-01 — Поиск лида в канбане

**Phase:** 9 — kanban-search
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

Менеджер в канбане (583+ лидов) не может быстро найти конкретного контрагента: надо прокрутить горизонтально 9 колонок и визуально искать по названиям. Фильтры (region/level/priority/manager) сужают выборку, но не ищут по тексту. Нужно текстовое поле «Поиск», которое живо фильтрует канбан-доску по названию, ИНН, руководителю, сайту или населённому пункту.

**Root cause (подтверждено чтением кода):**
- Серверного текстового поиска лидов (ILIKE/like) в проекте **нет вообще** — `grep -rni "ilike|func.lower|\.like("` по `app/*.py` пусто.
- В форме `#kanban-filters` (`app/templates/kanban.html:26-65`) **нет ни одного текстового инпута** — только 4-6 `<select>`.
- Форма уже HTMX-сабмитит себя (`hx-get="/kanban" hx-target="#kanban-board" hx-trigger="change" hx-include="this"`), значит новый инпут с тем же механизмом попадёт в запрос автоматически — **новый механизм не нужен**.
- Хелпер `build_kanban_query` (`app/routes/leads.py:49-63`) уже обеспечивает сквозную передачу фильтров через переход «канбан → лид → канбан» (фаза 8). Поиск обязан пользоваться тем же каналом, иначе потеряется.

**Ключевое наблюдение:** поиск — это **не отдельный режим, а ещё один AND-фильтр** в уже существующей выборке. Архитектура роута (`filters = [base_filter]` + серия `if X: filters.append(...)`) прямо для этого и устроена. Добавление — 3 строки в теле роута + инпут в шаблоне.

## Архитектура (обязательно к соблюдению)

**Query-параметр `q` как единственный способ передачи поиска, вписанный в существующий конвейер канбана.** Принципы:

1. `q` живёт в URL query string — тот же источник истины, что и фильтры фазы 8 (`region/level/priority/manager/assigned_manager`). Это даёт: сохранение при перезагрузке, шарябельную ссылку с поиском, работу кнопки «назад» браузера, передачу в карточку лида и обратно через `kanban_query`.
2. Поиск работает **совместно** с другими фильтрами (AND). «Показать лидов региона 3 уровня A с именем, содержащим Рапс» — корректный кейс.
3. Живой поиск через HTMX `keyup changed delay:400ms` — НЕ через отдельный endpoint/JSON/dropdown. Доска перерисовывается на месте, как при смене селекта.
4. ILIKE по полям **только таблицы leads** (без join на Contact). Поля телефона/email лежат в `Contact` (`models.py:123-126`), поиск по ним требует EXISTS-подзапроса и выходит за рамки MVP. Для MVP достаточно `name` (главное, уже проиндексировано `models.py:55`) + `inn`, `head_name`, `site`, `settlement`.

Сквозная передача поиска (поверх фазы 8):
```
/kanban?q=Рапс&region=3  (build_kanban_query уже содержит q)
  └─ partials/kanban_board.html: ссылка лида несёт ...&q=Рапс
       └─ /leads/{id}?kanban_query=%3F...%26q%3DРапс
            └─ Назад к канбану → поиск восстановлен
```

## Файлы

### 1. `app/routes/leads.py` (модификация)

**(a) Сигнатура роута kanban (~стр. 66-75)** — добавить параметр:
```python
async def kanban(
    request: Request,
    manager: str = None,
    region: str = None,
    level: str = None,
    priority: str = None,
    assigned_manager: str = None,
    q: str = None,                          # ← НОВОЕ
    session: AsyncSession = Depends(get_session),
):
```

**(b) Нормализация q (сразу после нормализации region/level/priority, ~стр. 82-85):**
```python
q = (q or "").strip() or None
```

**(c) Фильтр (в блоке сборки filters, ПОСЛЕ строки ~97, до формирования запроса):**
```python
if q:
    filters.append(
        or_(
            Lead.name.ilike(f"%{q}%"),
            Lead.inn.ilike(f"%{q}%"),
            Lead.head_name.ilike(f"%{q}%"),
            Lead.site.ilike(f"%{q}%"),
            Lead.settlement.ilike(f"%{q}%"),
        )
    )
```
> `or_` импортировать из `sqlalchemy` (проверить, что уже есть; если нет — добавить в импорт рядом с `select`). Все поля — колонки `Lead` (`models.py:55,59,60,61,57`), join не нужен. `ilike` даёт регистронезависимый поиск и в SQLite работает корректно.

**(d) build_kanban_query (~стр. 49-63)** — добавить `q` последним параметром:
```python
def build_kanban_query(region, level, priority, manager, assigned_manager, q=None) -> str:
    params = []
    if region:
        params.append(f"region={region}")
    if level:
        params.append(f"level={level}")
    if priority:
        params.append(f"priority={priority}")
    if manager:
        params.append(f"manager={manager}")
    if assigned_manager:
        params.append(f"assigned_manager={assigned_manager}")
    if q:
        params.append(f"q={q}")
    return ("?" + "&".join(params)) if params else ""
```

**(e) Вызов build_kanban_query в теле роута (~стр. 93)** — передать q:
```python
kanban_query = build_kanban_query(region, level, priority, manager, assigned_manager, q)
```

**(f) Context полной ветки (~стр. 150-165)** — добавить `"q": q,`:
```python
context={
    "current_user": user,
    "stages": stages_data,
    "regions": regions,
    "regions_scoped": regions_scoped,
    "users": users,
    "manager": manager,
    "level": level,
    "priority": priority,
    "region_id": region,
    "assigned_manager_id": assigned_manager,
    "q": q,                                 # ← НОВОЕ
    "kanban_query": kanban_query,
},
```
> HTMX-ветка (~стр. 143-148) отдельно `q` НЕ получает — и не нужно: значение инпута живёт в самой форме (форма не перерисовывается при swap, перерисовывается только `#kanban-board`), а при перерисовке полной страницы q берётся из context. Сквозная передача в карточку лида идёт через `kanban_query`, который уже содержит q.

### 2. `app/templates/kanban.html` (модификация)

**(a) Расширить hx-trigger формы (~стр. 26-28):**
```html
<form id="kanban-filters" class="flex gap-3 mb-4 flex-wrap"
      hx-get="/kanban" hx-target="#kanban-board" hx-swap="innerHTML"
      hx-trigger="change, keyup changed delay:400ms from:find input[name='q']"
      hx-include="this">
```
> Пояснение HTMX: `change` — как и раньше, для селектов. `keyup changed delay:400ms from:find input[name='q']` — живой поиск ТОЛЬКО по инпуту q, с debounce 400мс (чтобы не спамить сервер на каждое нажатие). `from:find ...` ограничивает триггер конкретным элементом. `hx-push-url="true"` (добавлен в фазе 8) остаётся — URL будет содержать `?q=...`.

**(b) Инпут поиска — первым элементом внутри формы (перед select region, ~стр. 29):**
```html
<input type="search" name="q" value="{{ q or '' }}"
       placeholder="Поиск: название, ИНН, руководитель, сайт, город"
       autocomplete="off"
       class="border border-black/10 rounded-md px-3 py-1.5 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-500">
```
> `type="search"` даёт нативную кнопку «✕» очистки в браузере — при очистке срабатывает `change` (а не keyup), форма сабмитится, доска сбрасывается. `autocomplete="off"` — не тащим историю предыдущих поисков браузера. Ширина `w-64` — на уровне селектов. Если кодер видит, что на узких экранах ломается layout — можно сделать flex-wrap (он уже есть на форме `flex-wrap`).

### 3. `app/templates/partials/kanban_board.html` (опциональная модификация, стр. 11)

Если `q` передаётся в partial context — подсветка совпадения в имени лида:
```html
{% set highlighted = q and (q in lead.name) %}
<a href="/leads/{{ lead.id }}{{ kanban_query }}" class="font-medium text-sm text-blue-500 hover:underline block truncate">
  {% if highlighted %}{{ lead.name[:lead.name.lower().index(q.lower())] }}<mark class="bg-yellow-200 rounded px-0.5">{{ lead.name[lead.name.lower().index(q.lower()):lead.name.lower().index(q.lower())+q|length] }}</mark>{{ lead.name[lead.name.lower().index(q.lower())+q|length:] }}{% else %}{{ lead.name }}{% endif %}
</a>
```
> ⚠️ Jinja-индексация со `lower()` громоздка. Если реализация выглядит уродливо или ломает `truncate` — **пропустить подсветку** (T-08 явно optional). Простой альтернативный вариант: не подсвечивать, оставить `{{ lead.name }}` как есть. Поиск и так работает (карточек меньше, нужная видна). Подсветка — косметика, не блокер.

> ВАЖНО: для работы q в partial нужно передать его в HTMX-context. Но см. T-04 — в HTMX-ветке мы намеренно НЕ кладём q отдельно (он в kanban_query). Если кодер решит делать подсветку — надо добавить `"q": q` в HTMX-context `leads.py:143-148` рядом с `kanban_query`. Это единственное обоснованное добавление q в HTMX-ветку.

## Шаги выполнения

1. `app/routes/leads.py` — параметр `q` в сигнатуре, нормализация, `or_`-фильтр в блоке filters, `q` в `build_kanban_query`, передача `q` в вызов хелпера, `"q": q` в context полной ветки. Проверить импорт `or_`.
2. `app/templates/kanban.html` — инпут `name="q"` первым в форме, расширение `hx-trigger`.
3. (опц.) `app/templates/partials/kanban_board.html` — подсветка `q` в имени. Если делается — добавить `"q": q` в HTMX-context `leads.py:143-148`.
4. Ручная проверка сценариев (см. Acceptance) — особенно: живой поиск с debounce, совместная работа с селектами, drag-and-drop после живого поиска, сохранение поиска при переходе в лида и обратно.

## Acceptance criteria (gate)

- [ ] Инпут поиска виден в канбане первым полем формы, с placeholder про название/ИНН/руководителя/сайт/город.
- [ ] Ввод текста → через ~400мс доска перерисовывается, остаются только лиды с совпадением хотя бы в одном из 5 полей.
- [ ] Поиск регистронезависимый («рапс» и «РАПС» находят одно и то же).
- [ ] Очистка инпута (кнопка ✕ или вручную) → доска возвращается к полному набору (с учётом остальных фильтров).
- [ ] Поиск работает совместно с селектами: регион + уровень + строка поиска → AND. Например, `region=3&q=Рапс` показывает только лидов региона 3 со словом «Рапс».
- [ ] URL обновляется и содержит `?q=...` (через `hx-push-url` из фазы 8).
- [ ] Перезагрузка страницы с `?q=Рапс` в URL сохраняет поиск и значение в инпуте.
- [ ] Сценарий «канбан → ввод поиска → клик на найденного лида → Назад к канбану»: поиск восстанавливается, инпут содержит текст, доска отфильтрована.
- [ ] Drag-and-drop смены стадии работает после живого поиска: нашли лида → перетащили в другую колонку → стадия сохранилась, счётчики пересчитались.
- [ ] Для supervisor/admin: поиск работает в рамках выбранного scope + assigned_manager (не ломает ролевую видимость).
- [ ] Нет поиска по телефону/email — это явно out-of-scope (поля в Contact, нужен join); в PLAN не заложено.
- [ ] Логика фильтрации region/level/priority/manager/assigned_manager (`leads.py:92-117`) не изменена — diff пустой в этой зоне кроме нового блока `if q:`.

## Не делаем (YAGNI)

- НЕ делаем отдельный endpoint `/api/leads/search` с JSON/dropdown — поиск фильтрует саму доску на месте, это правильнее UX.
- НЕ ищем по Contact (phone/email/name контактного лица) — требует EXISTS-подзапроса/join, выходит за рамки MVP. Если понадобится — отдельная фаза.
- НЕ вводим полнотекстовый поиск (FTS5 и т.п.) — для 583 лидов ILIKE по индексированному name достаточно, FTS — оверинжиниринг.
- НЕ трогаем `app/static/js/kanban.js` — drag-and-drop и так реинициализируется на `htmx:afterSwap`. Трогаем только если ручная проверка выявит регрессию.
- НЕ делаем «нечёткий поиск» / опечатки / морфологию — точное ilike-вхождение достаточно для MVP.
- НЕ добавляем q в другие страницы кроме канбана (в карточке лида он не нужен, поиск — на канбан-доске).
- Подсветку совпадений (T-08) делаем только если тривиально и не ломает вёрстку — иначе пропускаем.
