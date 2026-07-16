---
phase: 8-kanban-filter-persist
plan: "01"
slice: 8-01
type: execute
wave: 1
depends_on:
  - phase-2
requirements:
  - CRM-8-01
autonomous: true
files_modified:
  - app/routes/leads.py
  - app/templates/kanban.html
  - app/templates/partials/kanban_board.html
  - app/templates/lead_card.html
files_created: []
must_haves:
  truths:
    - "T-01: Состояние фильтров канбана (region, level, priority, manager, assigned_manager) хранится в URL query string как единственный источник истины. Никакого localStorage/sessionStorage/cookies для фильтров канбана НЕ вводить"
    - "T-02: На форме фильтров app/templates/kanban.html:26 добавлен атрибут hx-push-url=\"true\" — после каждого change (HTMX-обновление #kanban-board) адресная строка браузера отражает актуальный набор фильтров"
    - "T-03: В роуте /kanban (app/routes/leads.py:49) собрана строка kanban_query (вида ?region=3&level=A&manager=my или пустая, если фильтров нет) через единый хелпер build_kanban_query(region, level, priority, manager, assigned_manager). Параметры со значением None/'' пропускаются. Эта строка кладётся в context ОБЕИХ веток ответа: и полной kanban.html (leads.py:131-146), и HTMX-фрагмента partials/kanban_board.html (leads.py:124-129) — без этого ссылка на лида внутри partial не получит фильтр"
    - "T-04: В app/templates/partials/kanban_board.html:11 ссылка на лида несёт текущий query канбана: href=\"/leads/{{ lead.id }}{{ kanban_query }}\". kanban_query уже содержит ведущий '?', при пустом фильтре ссылка остаётся чистой /leads/{id}"
    - "T-05: Роут карточки лида GET /leads/{lead_id} (app/routes/leads.py:290) принимает опциональный query-параметр kanban_query: str = '' и кладёт его в context рендера lead_card.html. НЕ использовать Referer (ненадёжен за HTMX)"
    - "T-06: Кнопка «Назад к канбану» в app/templates/lead_card.html:5 использует переменную: href=\"/kanban{{ kanban_query }}\". Возврат из лида восстанавливает ровно тот набор фильтров, с которого пришли"
    - "T-07: Хелпер build_kanban_query определён ровно в одном месте (рядом с роутами канбана в app/routes/leads.py) и используется и в /kanban, и косвенно (через context) в /leads/{id}. Запрещено дублировать построение query-строки в шаблонах или в нескольких функциях"
    - "T-08: Серверная логика фильтрации (app/routes/leads.py:64-93) НЕ ТРОГАЕТСЯ — она уже корректна. Меняются только: сбор kanban_query, прокидывание в context обеих веток, новый параметр роута лида, три шаблона"
    - "T-09: Drag-and-drop смены стадии (app/static/js/kanban.js, слушатель htmx:afterSwap на #kanban-board) не сломан после добавления hx-push-url: после swap partial Sortable реинициализируется как раньше. Это главный регрессионный риск — проверить вручную"
    - "T-10: Параметр kanban_query не зависит от роли: прокидывается одинаково для manager / supervisor / admin. Для supervisor/admin в query входят assigned_manager и manager (my/all), для manager — только region/level/priority (assigned_manager/select скрыты, но их пустые значения в query допустимы и обрабатываются сервером как None)"
  artifacts:
    - path: app/routes/leads.py (модификация)
      provides: "build_kanban_query(region, level, priority, manager, assigned_manager) — единый хелпер построения query-строки фильтров канбана; kanban_query в context обеих веток /kanban; опциональный параметр kanban_query в GET /leads/{lead_id}"
    - path: app/templates/kanban.html (модификация)
      provides: "hx-push-url=\"true\" на форме #kanban-filters — URL браузера обновляется при фильтрации"
    - path: app/templates/partials/kanban_board.html (модификация)
      provides: "Ссылка на лида с текущим фильтром: href=\"/leads/{{ lead.id }}{{ kanban_query }}\""
    - path: app/templates/lead_card.html (модификация)
      provides: "Кнопка «Назад к канбану» восстанавливает фильтры: href=\"/kanban{{ kanban_query }}\""
  key_links:
    - from: app/routes/leads.py (/kanban)
      to: app/templates/partials/kanban_board.html
      via: "context={'stages': stages_data, 'kanban_query': kanban_query} в HTMX-ветке (leads.py:124-129)"
      pattern: "Фильтр в ссылке лида внутри partial — критично: HTMX-ветка сегодня отдаёт ТОЛЬКО stages"
    - from: app/routes/leads.py (/kanban)
      to: app/templates/kanban.html
      via: "context с kanban_query в полной ветке (leads.py:131-146)"
      pattern: "Фильтр в ссылке лида при первичной загрузке канбана"
    - from: app/routes/leads.py (/leads/{lead_id})
      to: app/templates/lead_card.html
      via: "опциональный kanban_query в сигнатуре → context кнопки «Назад»"
      pattern: "Возврат из лида с восстановлением фильтров"
    - from: app/templates/partials/kanban_board.html
      to: app/templates/lead_card.html
      via: "href=\"/leads/{id}{kanban_query}\" → роут лида читает kanban_query → кнопка «Назад»"
      pattern: "Сквозная передача фильтра канбан → лид → канбан"
---

# Plan 8-01 — Сохранение фильтров канбана при переходе в лида и обратно

**Phase:** 8 — kanban-filter-persist
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

Менеджер/руководитель/админ в канбане выставляет фильтр по региону (и/или уровню, приоритету, менеджеру), проваливается в карточку лида, делает там изменения и возвращается в канбан. Сейчас фильтры **слетают** — возвращается чистый `/kanban` без параметров, селект региона сбрасывается.

**Root cause (подтверждено чтением кода):**
- Фильтры применяются через HTMX-форму `#kanban-filters` (`app/templates/kanban.html:26`) с `hx-get="/kanban"` → `hx-target="#kanban-board"`. При этом **нет `hx-push-url`** — адресная строка браузера не обновляется.
- Состояние фильтра живёт ровно до ответа одного HTMX-запроса и нигде не сохраняется (URL пустой, localStorage/sessionStorage/cookies для канбана не используются).
- Ссылка на лида захардкожена без фильтра: `app/templates/partials/kanban_board.html:11` → `/leads/{{ lead.id }}`.
- Кнопка «Назад к канбану» захардкожена без фильтра: `app/templates/lead_card.html:5` → `/kanban`.
- При возврате открывается голый `/kanban`, роут отдаёт дефолты (`manager=my` для manager, `region/level/priority/assigned_manager=None`) — выбор пользователя потерян.

**Ключевое наблюдение:** серверная часть менять **не нужно** — роут `/kanban` (`app/routes/leads.py:49-146`) уже принимает все query-параметры (`region, level, priority, manager, assigned_manager`) и возвращает их же в context для выставления `selected` в селектах. Нужно лишь сделать так, чтобы эти параметры переживали переход в лида и обратно.

## Архитектура (обязательно к соблюдению)

**URL query string как единственный источник истины для фильтров канбана.** Это даёт автоматически и бесплатно:

1. Сохранение фильтра при переходе канбан → лид → канбан (через сквозной параметр `kanban_query`).
2. Шарябельную ссылку на канбан с фильтром.
3. Работу кнопки «назад» браузера между канбаном и карточкой лида.
4. Перезагрузку страницы канбана с сохранением фильтра.

Сквозная передача устроена так:
```
/kanban (build_kanban_query → context, в обе ветки)
  └─ partials/kanban_board.html: href="/leads/{id}{kanban_query}"
       └─ /leads/{lead_id}?kanban_query=<...>  (новый опц. параметр роута)
            └─ lead_card.html: href="/kanban{kanban_query}"  ← возврат с фильтром
```

Имя параметра `kanban_query` выбрано осознанно (а не `?from=`/`?next=`): он несёт **содержимое** фильтра канбана в виде готовой query-строки, а не указатель на «откуда пришли». Так кнопка «Назад» читает ровно то, что было, а не реинтерпретирует Referer.

## Файлы

### 1. `app/routes/leads.py` (модификация) — хелпер + context в обе ветки + параметр роута лида

**Хелпер `build_kanban_query`** (рядом с роутом `kanban`, после него или перед ним):
```python
def build_kanban_query(region, level, priority, manager, assigned_manager) -> str:
    """Готовит query-строку фильтров канбана для ссылок (вида '?region=3&level=A'
    или '', если фильтров нет). Единое место построения — используется в /kanban
    (для ссылок на лидов) и косвенно в /leads/{id} (кнопка «Назад»)."""
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
    return ("?" + "&".join(params)) if params else ""
```

> Примечание: `region`/`priority` здесь уже приведены к int/None в теле роута (стр. 65-66), `level` — к чистой строке/None (стр. 68). Использовать значения **после нормализации**, а не сырые строки из query — иначе в ссылку попадёт мусор. Проверяемое условие `if region:` корректно отсекает 0/None/'' (id регионов начинаются с 1).

**В теле роута `kanban` (после нормализации параметров, ~стр. 93)** — собрать query:
```python
kanban_query = build_kanban_query(region, level, priority, manager, assigned_manager)
```

**HTMX-ветка (`leads.py:124-129`)** — добавить `kanban_query` в context (СЕГОДНЯ там только `stages` — это баг для нашей задачи, без правки ссылка в partial не получит фильтр):
```python
if request.headers.get("hx-request"):
    return templates.TemplateResponse(
        request=request,
        name="partials/kanban_board.html",
        context={"stages": stages_data, "kanban_query": kanban_query},
    )
```

**Полная ветка (`leads.py:131-146`)** — добавить `kanban_query` в context:
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
    "kanban_query": kanban_query,
},
```

**Роут карточки лида (`leads.py:290-291`)** — принять опциональный параметр и положить в context:
```python
@router.get("/leads/{lead_id}", response_class=HTMLResponse)
async def lead_card(
    request: Request,
    lead_id: int,
    kanban_query: str = "",
    session: AsyncSession = Depends(get_session),
):
```
И в context рендера (`leads.py:320-326`) добавить `"kanban_query": kanban_query,`.

> FastAPI/FastAPI-Starlette декодирует `%3Fregion%3D3` из query в строку как есть. Поскольку мы передаём `kanban_query` уже с ведущим `?`, он в шаблоне просто конкатенируется. Если кодер видит проблемы с кодировкой спецсимволов в `?`/`&` — допускается передавать query **без** ведущего `?` и добавлять его в шаблонах (`{{ '?'+kanban_query if kanban_query }}`). Решение за кодером, главное — единый формат во всех трёх точках применения.

### 2. `app/templates/kanban.html` (модификация, ~стр. 26-28) — `hx-push-url`

Добавить `hx-push-url="true"` на форму, чтобы URL браузера обновлялся при фильтрации:
```html
<form id="kanban-filters" class="flex gap-3 mb-4 flex-wrap"
      hx-get="/kanban" hx-target="#kanban-board" hx-swap="innerHTML"
      hx-trigger="change" hx-include="this" hx-push-url="true">
```

> `hx-push-url="true"` пишет в URL все поля формы, включая пустые селекты (`region=&level=`). Это нормально и сервером обрабатывается (приведение пустых к None, стр. 64-68). Чистка пустых параметров из URL — необязательна (YAGNI); если кодер хочет — можно очистить, но это не блокер задачи и не должно её усложнять.

### 3. `app/templates/partials/kanban_board.html` (модификация, стр. 11) — ссылка на лида с фильтром

```html
<a href="/leads/{{ lead.id }}{{ kanban_query }}" class="font-medium text-sm text-blue-500 hover:underline block truncate">{{ lead.name }}</a>
```

### 4. `app/templates/lead_card.html` (модификация, стр. 5) — кнопка «Назад» с фильтром

```html
<a href="/kanban{{ kanban_query }}" class="text-ink text-sm hover:underline">&larr; Назад к канбану</a>
```

## Шаги выполнения

1. **Хелпер** `build_kanban_query` в `app/routes/leads.py` (единое место).
2. В теле `kanban` — вызов хелпера после нормализации параметров; добавить `kanban_query` в context **обеих** веток (HTMX + полная).
3. В `lead_card` — опциональный параметр `kanban_query: str = ""` + в context.
4. `kanban.html` — `hx-push-url="true"` на форме.
5. `partials/kanban_board.html` — `{{ kanban_query }}` в href ссылки лида.
6. `lead_card.html` — `{{ kanban_query }}` в href кнопки «Назад».
7. Ручная проверка сценариев (см. Acceptance) — особенно drag-and-drop после добавления `hx-push-url`.

## Acceptance criteria (gate)

- [ ] После установки любого фильтра в канбане URL браузера обновляется (виден `?region=...&...`).
- [ ] Перезагрузка страницы канбана сохраняет все фильтры (селекты остаются выбранными).
- [ ] Сценарий «канбан → фильтр по региону → клик на лида → Назад к канбану»: возврат на `/kanban?region=...`, фильтр на месте, селект региона подсвечен.
- [ ] То же для supervisor/admin с дополнительными фильтрами `assigned_manager` и `manager` (my/all).
- [ ] Кнопка «Назад» браузера корректно ходит между канбаном и карточкой лида (фильтр не теряется).
- [ ] `build_kanban_query` определён ровно один раз (grep: одно определение).
- [ ] HTMX-ветка `/kanban` отдаёт `kanban_query` в context partial (главная ловушка задачи — сегодня отдаёт только `stages`).
- [ ] Drag-and-drop смены стадий работает после `hx-push-url` (картинку перетаскиваем, стадия меняется, после swap Sortable реинициализируется).
- [ ] Ссылки на лидов при отсутствии фильтров остаются чистыми (`/leads/123`, не `/leads/123?`).
- [ ] Серверная логика фильтрации (`leads.py:64-93`) не изменена — diff пустой в этой зоне.

## Не делаем (YAGNI)

- НЕ вводим localStorage/sessionStorage/cookies для фильтров канбана — URL query достаточен и даёт больше (шаринг, кнопка браузера, перезагрузка).
- НЕ чистим пустые параметры из URL (region=&level=) — работает корректно, чистка лишь усложнит.
- НЕ трогаем `app/static/js/kanban.js` — drag-and-drop и так реинициализируется на `htmx:afterSwap`. Трогаем только если ручная проверка выявит регрессию.
- НЕ вводим отдельный механизм «памяти фильтра» на сервере (сессия/БД) — избыточно для текущей задачи.
- НЕ трогаем роуты редактирования лида (`/leads/{id}/edit` и т.п.) — возврат всё равно идёт через кнопку «Назад» с `kanban_query`.
- НЕ добавляем `kanban_query` в другие страницы/роуты, кроме канбана и карточки лида.
