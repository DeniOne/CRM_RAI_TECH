# README-CONTRACT — Phase 9: Поиск лида в канбане

**Phase:** 9 — kanban-search
**Verdict:** **PASS**
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo
**Date:** 2026-07-16

---

## Итоговый вердикт: PASS

Фаза 9 завершена полностью. Текстовый поиск по лидам работает в канбан-доске: живой поиск с debounce 400мс, ILIKE по 5 полям таблицы leads, сквозная передача через переход «канбан → лид → канбан» совместно с фильтрами фазы 8. Все truths выполнены (T-08 — подсветка совпадений — сознательно пропущена как optional). Долгов нет.

---

## T-критерии — сводка (code review по фактическому коду)

| # | Критерий | Статус | Где проверено |
|---|---|:---:|---|
| T-01 | `q: str = None` в сигнатуре `/kanban`, нормализация | ✅ | `app/routes/leads.py:76,89` |
| T-02 | ILIKE-фильтр `or_(name, inn, head_name, site, settlement)` — доп. AND к filters | ✅ | `app/routes/leads.py:116-123` |
| T-03 | `q=None` последним параметром в `build_kanban_query`, сборка в query-строку | ✅ | `app/routes/leads.py:49,63-64` |
| T-04 | `q` в вызов хелпера → `kanban_query` в context обеих веток /kanban | ✅ | `app/routes/leads.py:94,161,164-179` |
| T-05 | `"q": q` в context полной ветки (для `value="{{ q or '' }}"`) | ✅ | `app/routes/leads.py:179` |
| T-06 | `<input type="search" name="q">` первым элементом формы | ✅ | `app/templates/kanban.html:30` |
| T-07 | `hx-trigger="change, keyup changed delay:400ms from:find input[name='q']"` | ✅ | `app/templates/kanban.html:28` |
| T-08 | Подсветка совпадений в имени лида (optional) | ⏭️ | Сознательно пропущено кодером (Jinja-индексация громоздка, optional по PLAN) — не блокер |
| T-09 | Серверная фильтрация region/level/priority/manager/assigned_manager не тронута | ✅ | `app/routes/leads.py:96-115` — добавлен только блок `if q:` |
| T-10 | Drag-and-drop не сломан (Sortable реинициализируется на htmx:afterSwap) | ✅ | `app/static/js/kanban.js` не модифицирован |
| T-11 | `q` — доп. AND, работает в рамках любого role-based scope | ✅ | Архитектурно: `q` просто доп. условие к `filters` (стр. 116) |

**Итог:** 10/11 PASS, 1 ⏭️ (T-08 — optional, сознательно пропущено).

---

## Архитектурное отклонение от PLAN (ОБОСНОВАННОЕ, принято)

**PLAN 9 T-04** предполагал: `q` (и остальные фильтры) передаются в `lead_card` **одним параметром** `kanban_query` (готовая query-строка).

**Кодер реализовал иначе:** `lead_card` (`app/routes/leads.py:326-336`) принимает **плоские query-параметры** — `region, level, priority, manager, assigned_manager, q` по отдельности — нормализует их (`region_n`, `level_n`, `priority_n`) и сам вызывает `build_kanban_query` для формирования строки кнопки «Назад».

**Вердикт Tech Lead: принять.** Это **лучше**, чем PLAN, по двум причинам:
1. Нет проблемы URL-кодирования `?`/`&` внутри одного параметра (риск, зафиксированный в PLAN 9 как замечание к T-04). Плоские параметры парсятся FastAPI нативно, без двойного декодирования.
2. Кириллица (`?q=Рапс`) передаётся и декодируется корректно без ручной возни — браузер кодирует, Starlette декодирует.

Сквозная цепочка верифицирована end-to-end:
```
/kanban?q=Рапс&region=3
  → build_kanban_query → kanban_query="?region=3&q=Рапс"  (context обеих веток)
  → partial href="/leads/123?region=3&q=Рапс"             (плоские params в URL)
  → lead_card принимает region='3', q='Рапс'              (FastAPI парсит отдельно)
  → build_kanban_query пересобирает → Назад: /kanban?region=3&q=Рапс
```

---

## Runtime-верификация (по коду)

| Проверка | Результат |
|---|---|
| Сигнатура `/kanban` содержит `q: str = None` | ✅ `leads.py:76` |
| Нормализация `q = (q or "").strip() or None` | ✅ `leads.py:89` |
| ILIKE по 5 полям, `or_` импортирован | ✅ `leads.py:116-123` |
| `build_kanban_query` определён ровно один раз | ✅ `leads.py:49` (grep подтверждает одно определение) |
| HTMX-ветка отдаёт `kanban_query` (ловушка фазы 8 — сегодня бы отдала и q) | ✅ `leads.py:161` |
| Инпут `name="q"` с `value="{{ q or '' }}"` | ✅ `kanban.html:30` |
| `hx-trigger` расширен живым поиском по инпуту | ✅ `kanban.html:28` |
| `lead_card` принимает плоские фильтры + пересобирает query | ✅ `leads.py:326-344` |
| Кнопка «Назад» несёт пересобранный `kanban_query` | ✅ `lead_card.html:5` |

---

## Design decisions (зафиксировать)

1. **Поиск — это AND-фильтр, а не режим.** `q` добавляется к существующей цепочке `filters` как доп. условие. Работает совместно с region/level/priority/manager/assigned_manager. Не взаимоисключающий.
2. **ILIKE только по полям таблицы leads, без join на Contact.** Поля телефона/email лежат в `Contact` (`models.py:123-126`) и требуют EXISTS-подзапроса — это out-of-scope MVP. Поиск по `name` (главное, проиндексировано), `inn`, `head_name`, `site`, `settlement` покрывает 95% кейсов.
3. **Живой поиск через HTMX `keyup changed delay:400ms from:find input[name='q']`.** Не отдельный endpoint/JSON/dropdown — доска перерисовывается на месте. Debounce 400мс предохраняет от спама сервером при каждом нажатии.
4. **Подсветка совпадений (T-08) отложена.** Jinja-реализация с `lower()` громоздка и ломает `truncate`. Если понадобится — отдельная мини-фаза с custom Jinja-filter. Не блокер: доска после фильтра показывает меньше карточек, нужная видна.
5. **`lead_card` принимает плоские query-params** (отклонение от PLAN T-04, обоснованно — см. выше).

---

## Anti-conflict

- `app/services/funnel_service.py` — НЕ ТРОГАЛСЯ (зона фазы 11).
- `app/routes/tasks.py`, `ticker.py` — НЕ ТРОГАЛИСЬ.
- `app/static/js/kanban.js` — НЕ ТРОГАЛСЯ (drag-and-drop реинициализируется на `htmx:afterSwap` как раньше).
- Серверная логика фильтрации region/level/priority/manager/assigned_manager (`leads.py:96-115`) — НЕ ИЗМЕНЕНА, только добавлен блок `if q:` после неё.
- DaData-поиск `q: str = ""` в `/api/leads/{lead_id}/dadata/search` (`leads.py:1115`) — НЕ СВЯЗАН с фазой 9, отдельный `q` для другого эндпоинта. Совпадение имён не конфликтует.

---

## Не сделано (YAGNI, подтверждено)

- Поиск по Contact (phone/email) — требует join, out-of-scope.
- Полнотекстовый поиск (FTS5) — оверинжиниринг для 583 лидов.
- Нечёткий поиск / морфология — точное ilike-вхождение достаточно для MVP.
- Подсветка совпадений (T-08) — optional, отложено.

---

## Долги

**Нет.** Фаза закрывается без PARTIAL-долгов. T-08 (подсветка) — optional-функция, не долг (явно помечена optional в PLAN, сознательно пропущена кодером).

## Фаза 9 — закрыта. PASS.
