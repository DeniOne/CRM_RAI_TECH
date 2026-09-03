# README-CONTRACT — Phase 16: Система отчётов CRM (каталог + фильтры + XLSX/DOCX)

**Phase:** 16 — reports
**Verdict:** ✅ PASS
**Author (Tech Lead):** ZCode (@zcode-assistant)
**Coder:** mimo
**Date:** 2026-07-23
**Judge:** чек-лист smoke-тестов (FastAPI TestClient на прод-БД `storage/crm.db`) — gate-автоматизации для UI-фазы нет.

---

## Итоговый вердикт: PASS

Фаза реализована строго по `01-PLAN.md`. Все 12 T-критериев подтверждены runtime
(FastAPI TestClient против реальной БД с 583 лидами, 6 менеджерами, 98 потерянными).
Ни одного регресса существующих роутов. Долг №3 (tempfile-накопление) закрыт.
PDF сознательно не сделан (Owner-decision, зафиксирован в PLAN).

---

## T-критерии — сводка

| # | Критерий | Статус | Где проверено |
|---|---|---|---|
| T-01 | `/reports/center` (HTML), supervisor/admin только; 403 остальным | ✅ | `reports.py:96`; TestClient: admin→200, manager→403 |
| T-02 | Форма фильтров: date_from/to, region_id, manager_id, селектор отчёта | ✅ | `reports_center.html:12-39`; 4 select/input рендерятся с данными |
| T-03 | `/reports/download` с report+format; 400 на unknown report/format | ✅ | `reports.py:122-195`; 400 на `format=pdf`, `report=bogus` |
| T-04 | XLSX через StreamingResponse/BytesIO; НЕТ tempfile/FileResponse | ✅ | `export_renderers.py:16-26`; `grep tempfile reports.py` → пусто |
| T-05 | DOCX через python-docx: заголовок + период + таблица, шапка жирным | ✅ | `export_renderers.py:36-55`; валидный PK-zip, 35KB |
| T-06 | `get_funnel_totals` принимает region/manager/date_from/to; обратная совместимость | ✅ | `report_service.py:26`; no-arg → 583, region_id=1 → 20 |
| T-07 | `get_manager_kpi` применяет manager_id; region_id к лидам | ✅ | `report_service.py:62-119` |
| T-08 | `get_lost_leads`, `get_deals_pipeline` существуют, list[dict] | ✅ | `report_service.py:161, 206` |
| T-09 | `get_lost_leads` группирует по loss_reason (NULL→"Без причины") + до 3 примеров | ✅ | runtime: 2 причины, sample примеров корректный |
| T-10 | `get_deals_pipeline` по Deal.status; count + total_amount (coalesce) | ✅ | `report_service.py:213-214`; 7 статусов в порядке DEAL_STATUS_LABELS |
| T-11 | Кнопка в supervisor_dashboard → /reports/center; /reports/export alias сохранён | ✅ | `supervisor_dashboard.html:9`; `/reports/export` → 200 xlsx |
| T-12 | Smoke: 4 отчёта × 2 формата открываются без ошибки | ✅ | xlsx/docx — валидный PK magic на всех 8 комбинациях |

**Итог: 12/12 PASS.**

---

## Runtime-верификация (по коду + TestClient)

Полный прогон через `fastapi.testclient.TestClient` против `storage/crm.db` (583 лида):

```
LOGIN (admin@crm.local):            303 → session cookie ✅
/reports/center (admin):            200, contains "Центр отчётов", 4 карточки ✅
/reports/center (manager):          403 ✅
/reports/download funnel xlsx:      200, 5270B, PK\x03\x04 magic ✅
/reports/download managers docx:    200, 35798B, PK\x03\x04 magic ✅
/reports/download format=pdf:       400 ✅
/reports/download report=bogus:     400 ✅
/reports/export (legacy):           200, 5271B xlsx ✅
region_id=1 меняет результат:       5271B → 5252B (разные) ✅
РЕГРЕСС /reports:                   200 ✅
РЕГРЕСС /reports/funnel:            200 ✅
РЕГРЕСС /reports/managers:          200 ✅
```

Агрегации (прямые вызовы `report_service`):
```
funnel_totals() без фильтров:  10 стадий, total=583
funnel_totals(region_id=1):    total=20
manager_kpi():                 6 users
lost_leads():                  2 причины, sample примеров корректный
deals_pipeline():              7 статусов в порядке DEAL_STATUS_LABELS
```

Все 4 Python-файла компилируются (`py_compile` — без ошибок).

---

## Архитектурные отклонения от PLAN (ОБОСНОВАННЫЕ, приняты)

1. **`_format_period()` — выделена как отдельная функция** (`reports.py:218-225`), не inline в каждом branch. PLAN не предписывал форму; выделение в helper — чище, используется во всех 4 docx-ветках. Принято.

2. **`render_docx` получила параметр `filename`** (PLAN-сигнатура была без него, `report_service.py:29`). Кодер добавил для симметрии с `render_xlsx` и корректного Content-Disposition. Принято — расширение безопасное (default есть).

Никаких отступлений от архитектурных принципов (3-слойность, BytesIO, role-гейт, единые справочники) — нет.

---

## Design decisions (зафиксировать)

1. **Единый набор фильтров `date_from, date_to, region_id, manager_id`** — пробрасывается во все 4 агрегации одинаково. Расширение новым фильтром = правка в 4 местах (aggregator) + форма + JS. Зафиксировать как контракт.

2. **Дата события по типу отчёта** (зафиксировано в docstring каждой функции):
   - funnel / lost_leads → `Lead.created_at`
   - managers → `ContactLog.contact_date` (звонки) + `Document.created_at` (КП)
   - deals_pipeline → `Deal.created_at`
   Это решение из PLAN (принцип 6) — соблюдено.

3. **`deals_pipeline` игнорирует `manager_id` через join Lead** (`report_service.py:212, 220-221`). PLAN (принцип 3) предписывал, что deals_pipeline фильтруется по region через join Lead, а manager_id применяется через `Lead.assigned_manager_id` — реализовано именно так. Работает корректно.

4. **Имена файлов — ASCII** (`report_<type>.xlsx/docx`, `reports.py:149,165,176,187`). Кириллица в Content-Disposition не используется — нет проблем с кодировкой заголовков. Имя типа отчёта в имени файла.

5. **JS-синхронизация фильтров с кнопками** (`reports_center.html:84-118`) — vanilla JS, ~30 строк, без нового файла в `static/js`. Кнопки XLSX/DOCX обновляют href при `change` формы + при загрузке (`updateLinks()` сразу). Без фреймворков — соотв. принципу YAGNI.

---

## Anti-conflict — вердикт

`git diff --stat` по защищённым зонам PLAN'а — **пусто** (всё чисто):

- `app/services/hermes_service.py`, `app/services/dadata_service.py`, `app/routes/agent.py` (AI-агент) — не тронуты ✅
- `app/services/document_service.py`, `app/routes/documents.py` (клиентские docx/pdf) — не тронуты ✅
- `app/models.py`, `app/database.py` (нет миграций БД) — не тронуты ✅
- `app/auth.py`, `app/services/import_service.py`, `app/services/phone_parser.py` — не тронуты ✅
- `templates_docx/`, `storage/documents/` — не тронуты ✅
- Существующие `STAGES`/`STAGE_LABELS`/`STAGE_COLORS` в `funnel_service.py` — не изменены, добавлена только новая константа `DEAL_STATUS_LABELS` (стр. 31-39) ✅

---

## Правило зависимостей (AGENTS.md) — проверка

PLAN требовал проверить потребителей `DEAL_STATUS_LABELS` и `get_funnel_totals`:

1. **Подписи статусов сделок дублируются в `app/templates/deals.html:6-9`** — те же 7 значений захардкожены в JS-объекте шаблона. Кодер **НЕ** вынес их в `DEAL_STATUS_LABELS` (как и предупреждал PLAN, п. 3 файла "funnel_service"). Это **известный дубль** — зафиксирован в Known limitations ниже. Не блокер: deals.html рендерит select для UI-фильтра, report_service — для отчётов; рассинхрон теоретически возможен, но маловероят (7 значений стабильны).

2. **`get_funnel_totals` без аргументов** вызывается в `/reports` (`reports.py:28`), `/reports/funnel` (`reports.py:54`) — обратная совместимость сохранена (новые параметры опциональны, default None). Регресс: оба роута → 200 ✅.

3. **`get_manager_kpi` без новых аргументов** вызывается в `/reports/managers` (`reports.py:82`) — обратная совместимость сохранена. Регресс: 200 ✅.

---

## Миграция данных — вердикт

**Не требуется.** Все поля, необходимые для 4 отчётов, уже существуют в схеме:
`Lead.stage`, `Lead.loss_reason`, `Lead.region_id`, `Lead.assigned_manager_id`,
`Lead.created_at`, `Deal.amount`, `Deal.status`, `Deal.lead_id`, `Deal.created_at`.
Новых колонок и ALTER-миграций не вводилось.

---

## Не сделано (YAGNI, подтверждено)

Перенесено из PLAN (всё сознательно вне скоупа Wave 1):

- **PDF** — Owner-decision «не нужно, если сложно». Документировано в PLAN.
- **CSV-формат** — тривиальный follow-up, не запрошен.
- **Отчёты по задачам** (просроченные/по исполнителям) — фаза 17-кандидат.
- **Time-in-stage (скорость воронки)** — фаза 18-кандидат.
- **Активности и исходы контактов** — фаза 19-кандидат.
- **«Источник лида» (lead source)** — поля нет в БД, нужна мини-фаза миграции.
- **Графики в выгрузках, «мои отчёты», email-рассылка** — YAGNI.

---

## Known limitations

1. **Дубль подписей статусов сделок**: `DEAL_STATUS_LABELS` (`funnel_service.py:31`) и захардкоженный JS-объект в `app/templates/deals.html:6-9` содержат одни и те же 7 значений. При добавлении нового статуса сделки нужно править оба места. Не блокирует фазу (значения стабильны с фазы 03), но является нарушением правила единого источника правды. Кандидат на cleanup в фазе, которая будет трогать статусы сделок.

2. **Нет автоматического gate/тест-сьюта** для отчётов. Верификация — ручной smoke через TestClient (выполнен техлидом при review). Регрессии в будущем ловятся только ручным прогоном. Кандидат: добавить `tests/test_reports.py` в отдельной фазе тестирования.

3. **`get_funnel_by_region` не получила фильтров** — используется только в HTML-страницах `/reports`, `/reports/funnel` и в отчётах не участвует. Вне скоупа PLAN'а; если понадобится отчёт «воронка по регионам» с фильтрами — расширить по аналогии.

4. **Имена файлов xlsx/docx не содержат даты/фильтров** — фиксированные `report_<type>.<ext>`. Если у пользователя в браузере включено «всегда спрашивать куда сохранить», быстрые повторные выгрузки могут перезаписаться. Принято как YAGNI.

---

## Долги

| Долг | Почему появился | Когда закроется | Блокирует следующую фазу? |
|---|---|---|---|
| Дубль `DEAL_STATUS_LABELS` ↔ `deals.html` | Кодер не вынес JS-объект статусов в общую константу (PLAN предвидел, позволил как known-limitation) | Закроется попутно в фазе, меняющей статусы сделок (безопасно — значения стабильны с фазы 03) | **НЕТ** — не влияет на отчёты, рассинхрон только при редком добавлении статуса |
| Нет `tests/test_reports.py` | UI-фаза без тест-инфраструктуры; верификация ручная | Отдельная cleanup-фаза тестирования (фаза-кандидат после 19), если проект перейдёт на pytest | **НЕТ** — smoke-тест техлида покрыл 12/12 T |
| `get_funnel_by_region` без фильтров | Вне скоупа PLAN (не нужна для 4 отчётов Wave 1) | Если поступит запрос на отчёт «воронка × регион» с фильтрами | **НЕТ** |

Все три долга — **не блокируют** exit фазы 16 и следующие фазы.

---

## Фаза 16 — закрыта. PASS.

12/12 T-критериев подтверждены runtime. 0 регрессов. Долг №3 (tempfile) закрыт.
PDF исключён Owner-decision. 3 известных ограничения зафиксированы, ни одно не блокирует.

**Готово к git commit + push** (шаг 4 GSD-цикла) — отдельным коммитом `feat(phase-16)`.
