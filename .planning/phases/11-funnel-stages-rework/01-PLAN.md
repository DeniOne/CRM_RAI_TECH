---
phase: 11-funnel-stages-rework
plan: "01"
slice: 11-01
type: execute
wave: 1
depends_on:
  - phase-1
requirements:
  - CRM-11-01
autonomous: true
files_modified:
  - app/services/funnel_service.py
  - app/services/report_service.py
  - app/services/import_service.py
  - app/templates/funnel_report.html
  - app/schemas.py
files_created:
  - scripts/migrate_stages_v11.py
must_haves:
  truths:
    - "T-01: В app/services/funnel_service.py обновлены три константы (единый источник истины стадий). Новая STAGES (порядок колонок): [\"0\",\"1\",\"2\",\"3\",\"4\",\"5\",\"6\",\"7\",\"postponed\",\"lost\"]. Новые STAGE_LABELS: {\"0\":\"Серые лиды\", \"1\":\"В работе\", \"2\":\"Квалифицирован\", \"3\":\"КП отправлено\", \"4\":\"Переговоры\", \"5\":\"Договор + Счёт\", \"6\":\"Оплачено\", \"7\":\"Доставлено\", \"postponed\":\"Отложенный спрос\", \"lost\":\"Потерян\"}. Новые STAGE_COLORS содержат ключ для каждого кода из STAGES (для \"postponed\" — подобрать нейтральный, напр. \"amber\"; для остальных сохранить существующие, со сдвигом семантики: 6→green/Оплачено, 7→teal/Доставлено — финальные цвета по вкусу кодера в рамках палитры)"
    - "T-02: Коды стадий переиспользуются (переименование семантики, НЕ введение новых цифровых кодов для существующих бизнес-смыслов): «Договор + Счёт» занимает код \"5\" (вбирает бывшие 5 «Договор» + 6 «Счёт выставлен»); «Оплачено» переезжает с кода \"7\" на \"6\"; освободившийся \"7\" становится «Доставлено»; «Отложенный спрос» — НОВЫЙ строковый код \"postponed\". Коды \"0\"-\"4\" и \"lost\" семантически unchanged («Серые лиды» = rename label для кода \"0\", был «Сырые лиды»)"
    - "T-03: validate_transition (funnel_service.py:30-53) остаётся корректным после переноса смыслов. Проверка `from_stage=='0' and to_stage=='1'` (требует assigned_manager) — unchanged, т.к. коды 0/1 не двигались. Проверка `from_stage=='1' and to_stage=='2'` (ЛПР + рапс) — unchanged. Если кодер видит, что для «Отложенный спрос» (postponed) нужен переход в/из without gates — добавить явные правила; минимум: `to_stage=='postponed'` возвращает True без проверок (как lost). Потеря не должна требовать gate"
    - "T-04: app/services/report_service.py:85 — KPI «конверсия» `Lead.stage.in_([\"3\",\"4\",\"5\",\"6\",\"7\"])` ОБНОВЛЁН под новую семантику: это «лиды, дошедшие до КП и дальше» = stages 3,4,5,6,7 (КП отправлено, Переговоры, Договор+Счёт, Оплачено, Доставлено). Код literally не меняется (3..7), но кодер обязан сверить что семантика корректна — postponed и lost НЕ входят. Если кодер решит включить postponed — это OWNER-decision, по умолчанию НЕ входит (отложенный спрос — не конверсия)"
    - "T-05: app/services/report_service.py:110 — `linear_stages` ОБНОВЛЁН под новый порядок и состав: [\"0\",\"1\",\"2\",\"3\",\"4\",\"5\",\"6\",\"7\"]. Коды \"postponed\" и \"lost\" сюда НЕ входят (это расчёт узких мест ЛИНЕЙНОЙ воронки; postponed/lost — нелинейные исходы). Без этой правки `STAGE_LABELS[from_stage]` (стр. 119,121) упадёт с KeyError, т.к. после миграции данных код 7 у некоторых лидов будет означать «Доставлено», а Label возьмётся новый — но linear_stages как список кодов unchanged по составу, главное что он покрывает 0..7. Проверить что labels для 6=«Оплачено», 7=«Доставлено» подставляются корректно"
    - "T-06: app/services/import_service.py:88-99 (determine_stage) возвращает только коды из нового STAGES. Сегодня возвращает \"0\",\"1\",\"3\",\"4\". Проверить: эти коды остались в новом наборе (да, 0=Серые, 1=В работе, 3=КП отправлено, 4=Переговоры). Функция БЕЗ ИЗМЕНЕНИЙ, т.к. возвращаемые коды сохранили семантику. Но кодер обязан сверить, что determine_stage не возвращает удалённых кодов (не возвращает). app/services/import_service.py:165 (`lead.stage='lost'`) — unchanged, код 'lost' действует"
    - "T-07: app/templates/funnel_report.html:15-39 — заголовки колонок и ключи `r.get('stage_X')` ОБНОВЛЕНЫ под новый набор. Новые <th> по порядку: Серые, В работе, Квалиф., КП, Перег., Договор+Счёт, Оплата, Доставка, Отлож., Потерян, Всего. Новые ячейки: r.get('stage_0')..r.get('stage_7'), r.get('stage_postponed'), r.get('stage_lost'). Без этого отчёт по регионам либо не покажет новые стадии, либо упустит данные"
    - "T-08: app/schemas.py:27 — `stage: str = \"0\"` unchanged (код «Серые лиды» остался \"0\"). app/routes/leads.py:250 (создание лида `stage=\"0\"`) — unchanged. app/routes/leads.py:439 (ветка потери `if lead.stage=='lost'`) — unchanged. app/routes/tasks.py:65,90 (`Lead.stage != 'lost'` — фильтр активных) — unchanged. Все эти точки корректны БЕЗ правок, т.к. используют unchanged коды; кодер обязан сверить их и явно отметить в SUMMARY что они проверены и unchanged"
    - "T-09: Создан scripts/migrate_stages_v11.py — одноразовая миграция данных leads.stage и stage_history.{from,to}_stage. Порядок SQL-операций КРИТИЧЕН (использовать временную кодировку во избежание коллизий при сдвиге): (1) UPDATE leads SET stage='_tmp_paid' WHERE stage='7'; (2) UPDATE stage_history SET from_stage='_tmp_paid' WHERE from_stage='7'; UPDATE stage_history SET to_stage='_tmp_paid' WHERE to_stage='7'; (3) UPDATE ... SET stage='5' WHERE stage IN ('5','6'); (4) UPDATE ... SET stage='6' WHERE stage='_tmp_paid'; (5) аналогично для stage_history. Проверить: после миграции НЕТ записей со stage='_tmp_paid' и НЕТ записей со stage='6' в значении «Счёт выставлен» (теперь это «Оплачено»). Лидов с кодом 6 было 0, кода 5 было 1, кода 7 было 1 — миграция переносит ровно эти записи"
    - "T-10: scripts/migrate_stages_v11.py идемпотентен в части переименования «Оплачено» (7→6): повторный запуск НЕ должен портить данные. Защита: пропускать миграцию если код '7' уже не означает «Оплачено» (проверить через отсутствующий маркер). На практике — миграция одноразовая, перед запуском скрипт делает БЭКАП storage/crm.db (копия с timestamp в имени, паттерн как существующие backups в storage/), и пишет отчёт сколько записей мигрировано. Бэкап обязателен"
    - "T-11: Канбан-доска (app/templates/partials/kanban_board.html, app/routes/leads.py:119,132-140) — дата-драйвен из STAGES/STAGE_LABELS/STAGE_COLORS, ПРАВИТЬ НЕ НАДО: после обновления констант в funnel_service.py доска автоматически покажет 10 колонок в новом порядке. Главное проверить вручную что 10 колонок рендерятся, счётчики на местах, drag-and-drop работает (Sortable не завязан на кол-во колонок)"
    - "T-12: app/templates/lead_card.html и partials/lead_form.html — stage_label берётся из context (STAGE_LABELS.get), дата-драйвен, править НЕ НАДО. app/templates/partials/lead_info_form.html:5 — текст тултипа упоминает «Квалифицирован», unchanged. Кодер проверяет что нигде в шаблонах нет ЗАХАРДКОЖЕННЫХ названий стадий кроме funnel_report.html:15-23 (это единственное захардкоженное место — правится по T-07)"
    - "T-13: Поле Lead.stage (app/models.py:83, String(10)) вмещает новые коды (макс длина 'postponed'=10 символов — РОВНО String(10), влезает; но проверить что SQLite String(10) не режет до 10 — SQLAlchemy String(10) для SQLite создаёт VARCHAR без жёсткого лимита, так что безопасно). Если кодер видит риск усечения — миграция схемы НЕ требуется, но проверить на практике одной записью"
  artifacts:
    - path: app/services/funnel_service.py (модификация)
      provides: "новые STAGES (10 кодов), STAGE_LABELS (переименования + postponed), STAGE_COLORS, validate_transition (добавлен postponed)"
    - path: app/services/report_service.py (модификация)
      provides: "linear_stages проверен под новые labels; KPI stage.in_(3..7) семантически сверен"
    - path: app/templates/funnel_report.html (модификация)
      provides: "10 заголовков колонок + 10 ячеек stage_* под новый набор"
    - path: scripts/migrate_stages_v11.py (новый)
      provides: "одноразовая миграция leads.stage и stage_history: 6→5, 7→6 через _tmp_paid, бэкап БД"
  key_links:
    - from: app/services/funnel_service.py (STAGES/STAGE_LABELS)
      to: app/routes/leads.py (сборка stages_data, kanban)
      via: "импорт STAGES, STAGE_LABELS, STAGE_COLORS в leads.py:119,132-140"
      pattern: "Канбан дата-драйвен, подтянется автоматически — главное не сломать импорт"
    - from: app/services/funnel_service.py
      to: app/services/report_service.py
      via: "STAGES (стр.34), STAGE_LABELS (стр.41,119,121) — дата-драйвен; но linear_stages (стр.110) захардкожен"
      pattern: "Захардкоженный linear_stages — главная ловушка; labels берутся динамически"
    - from: scripts/migrate_stages_v11.py
      to: storage/crm.db (leads.stage, stage_history)
      via: "UPDATE с временной кодировкой _tmp_paid для безопасного сдвига 7→6"
      pattern: "Сдвиг кодов с коллизией (6 и 7 оба валидны) — нужен temp-маркер"
---

# Plan 11-01 — Реворк стадий воронки продаж

**Phase:** 11 — funnel-stages-rework
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

Текущая воронка (`app/services/funnel_service.py:9-21`) имеет 9 стадий: «Сырые лиды, В работе, Квалифицирован, КП отправлено, Переговоры, Договор, Счёт выставлен, Оплачено, Потерян». Бизнес требует привести к новому составу и порядку:

**Целевая воронка (10 стадий, по решению Owner):** Серые лиды → В работе → Квалифицирован → КП отправлено → Переговоры → Договор + Счёт → **Оплачено → Доставлено** → Отложенный спрос → Потерян.

Изменения vs текущего:
1. «Сырые лиды» → **«Серые лиды»** (rename).
2. «Договор» + «Счёт выставлен» → **«Договор + Счёт»** (объединение двух в одну).
3. После «Оплачено» добавляется **«Доставлено»** (новая стадия).
4. Добавляется **«Отложенный спрос»** (новая стадия, нелинейный исход).
5. «Переговоры» **остаётся** (Owner: случайно пропустили в первоначальном списке, оставляем как есть после «КП отправлено»).
6. Порядок: «Оплачено» ПЕРЕД «Доставлено» (явное решение Owner в этой сессии).

**Root cause (подтверждено чтением кода и данных):**
- Стадии определены в **едином месте** `app/services/funnel_service.py:9-27` (STAGES, STAGE_LABELS, STAGE_COLORS), импортируются everywhere.
- Канбан-доска и карточка лида — **дата-драйвены** из этих констант (править не надо).
- **Но есть захардкоженные дубликаты**, которые рассинхронизируются без правки: `report_service.py:85` (KPI in_), `report_service.py:110` (`linear_stages`), `funnel_report.html:15-39` (заголовки и `stage_*` ключи).
- В БД **583 лида с реальными стадиями** (`storage/crm.db`): коды 5 (1 лид), 7 (1 лид) затронуты миграцией; код 6 пуст; postponed — нет; код «lost» = 118 лидов unchanged.

**Ключевое архитектурное решение:** переиспользовать существующие цифровые коды (НЕ вводить new enum), только переименовать семантику. Это минимизирует миграцию данных и риск. Поле `Lead.stage: String(10)` (`models.py:83`) — строка, миграция схемы НЕ нужна (только данные).

## Маппинг кодов (ОБЯЗАТЕЛЬНЫЙ к соблюдению)

| код | СТАРЫЙ лейбл | НОВЫЙ лейбл | миграция данных |
|---|---|---|---|
| `"0"` | Сырые лиды | **Серые лиды** | — (rename label only) |
| `"1"` | В работе | В работе | — |
| `"2"` | Квалифицирован | Квалифицирован | — |
| `"3"` | КП отправлено | КП отправлено | — |
| `"4"` | Переговоры | Переговоры | — |
| `"5"` | Договор | **Договор + Счёт** | `UPDATE … SET stage='5' WHERE stage IN ('5','6')` (вбирает бывший код 6 «Счёт выставлен») |
| `"6"` | Счёт выставлен | **Оплачено** | `UPDATE … SET stage='6' WHERE stage='7'` (1 лид) |
| `"7"` | Оплачено | **Доставлено** | — (код освобождён после 7→6, данных нет) |
| `"postponed"` | — | **Отложенный спрос** | — (новый код, данных нет) |
| `"lost"` | Потерян | Потерян | — |

**Сложность миграции:** коды 6 и 7 оба валидны до миграции, и 7 должно переехать в 6, а 6 — в 5. Прямой `UPDATE 7→6` затем `6→5` создал бы коллизию (одна запись прошла бы дважды). Решение — **временный маркер `_tmp_paid`** (см. T-09).

## Архитектура (обязательно к соблюдению)

**Правило зависимостей (главное правило проекта):** при смене стадий обновляются ВСЕ захардкоженные перечисления в одном коммите. Карта зависимостей:

```
funnel_service.py (STAGES, LABELS, COLORS) — ЕДИНЫЙ источник
   ├── leads.py:119,132-140 (сборка stages_data) — дата-драйвен, НЕ ТРОГАТЬ
   ├── lead_card.html, lead_form.html — дата-драйвен через LABELS, НЕ ТРОГАТЬ
   ├── report_service.py:34,41,119,121 — дата-драйвен (STAGES, LABELS), НЕ ТРОГАТЬ
   ├── report_service.py:85  (KPI in_) — ЗАХАРДКОЖЕНО, СВЕРИТЬ (состав unchanged, но проверить)
   ├── report_service.py:110 (linear_stages) — ЗАХАРДКОЖЕНО, СВЕРИТЬ (состав unchanged)
   ├── import_service.py:88-99 (determine_stage) — возвращает 0/1/3/4, СВЕРИТЬ (unchanged)
   ├── funnel_report.html:15-39 — ЗАХАРДКОЖЕНЫ заголовки и stage_* ключи, ОБЯЗАТЕЛЬНО ПРАВИТЬ
   └── schemas.py:27, leads.py:250,439, tasks.py:65,90 — unchanged коды, ПРОВЕРИТЬ
```

**Миграция данных — отдельный скрипт** `scripts/migrate_stages_v11.py` (одноразовый, с бэкапом). Скрипт запускается ОДИН раз на прод-БД; кодер НЕ запускает его на локальной БД без явного разрешения Owner (но пишет и тестирует локально на копии). В PLAN включён как артефакт; запуск на проде — отдельная операция.

## Файлы

### 1. `app/services/funnel_service.py` (модификация, строки 9-27, 30-53)

**STAGES (стр. 9):**
```python
STAGES = ["0", "1", "2", "3", "4", "5", "6", "7", "postponed", "lost"]
```

**STAGE_LABELS (стр. 11-21):**
```python
STAGE_LABELS = {
    "0": "Серые лиды",
    "1": "В работе",
    "2": "Квалифицирован",
    "3": "КП отправлено",
    "4": "Переговоры",
    "5": "Договор + Счёт",
    "6": "Оплачено",
    "7": "Доставлено",
    "postponed": "Отложенный спрос",
    "lost": "Потерян",
}
```

**STAGE_COLORS (стр. 23-27):**
```python
STAGE_COLORS = {
    "0": "gray", "1": "blue", "2": "indigo", "3": "purple",
    "4": "orange", "5": "yellow", "6": "green", "7": "teal",
    "postponed": "amber",
    "lost": "red",
}
```
> Кодер может скорректировать цвета в рамках палитры Tailwind (gray/blue/indigo/purple/orange/yellow/green/teal/amber/red). Главное — каждый код из STAGES имеет запись в STAGE_COLORS (иначе упадёт stages_data). «Оплачено» (6) — зелёный (успех), «Доставлено» (7) — teal (следующий шаг), «Отложенный спрос» (postponed) — amber (внимание).

**validate_transition (стр. 30-53)** — добавить явное правило для postponed (минимум):
```python
def validate_transition(lead: Lead, from_stage: str, to_stage: str) -> tuple[bool, list[str]]:
    if from_stage == to_stage:
        return True, []

    # Нелинейные исходы — без gate
    if to_stage in ("lost", "postponed"):
        return True, []

    # Переходы с gate (unchanged)
    if from_stage == "0" and to_stage == "1":
        if not lead.assigned_manager_id:
            return False, ["Назначьте менеджера"]
        return True, []

    if from_stage == "1" and to_stage == "2":
        errors = []
        has_dm = any(c.is_decision_maker for c in lead.contacts)
        if not has_dm:
            errors.append("Отметьте ЛПР среди контактов")
        if not lead.rapeseed_verified:
            errors.append("Подтвердите выращивание рапса")
        if errors:
            return False, errors
        return True, []

    return True, []
```
> Остальные переходы (3→4→5→6→7) — свободные, без gate (как и раньше). Возврат из postponed/lost в линейную воронку — тоже свободный (return True, [] в конце). Кодер может добавить gate «из lost нельзя вернуть без причины» если бизнес попросит — но по умолчанию НЕ добавляем (YAGNI).

### 2. `app/services/report_service.py` (модификация — сверить, правок может не быть)

**(a) Стр. 85 — KPI конверсия:**
```python
Lead.stage.in_(["3", "4", "5", "6", "7"])
```
> Состав unchanged (3,4,5,6,7), но семантически теперь: КП отправлено + Переговоры + Договор+Счёт + Оплачено + Доставлено. postponed и lost НЕ входят (правильно — отложенный спрос это не конверсия). Код literally не меняется, но кодер СВЕРЯЕТ что интерпретация корректна и явно отмечает в SUMMARY.

**(b) Стр. 110 — linear_stages:**
```python
linear_stages = ["0", "1", "2", "3", "4", "5", "6", "7"]
```
> Состав unchanged (0..7). Это расчёт узких мест ЛИНЕЙНОЙ воронки. postponed и lost сюда НЕ входят (нелинейные исходы). После переименования labels: `STAGE_LABELS['6']` = «Оплачено», `STAGE_LABELS['7']` = «Доставлено» — подставятся корректно (стр. 119, 121). Код literally не меняется, но кодер СВЕРЯЕТ и отмечает в SUMMARY.

> ⚠️ Главная ловушка: если кодер решит «linear_stages должен включать postponed» — это сломает расчёт конверсии между соседними стадиями (postponed — не сосед никого в линейном смысле). НЕ включать.

### 3. `app/templates/funnel_report.html` (модификация, стр. 15-39)

**Заголовки `<th>` (стр. 15-25):**
```html
<th class="text-left px-4 py-2 font-medium">Регион</th>
<th class="text-right px-4 py-2 font-medium">Серые</th>
<th class="text-right px-4 py-2 font-medium">В работе</th>
<th class="text-right px-4 py-2 font-medium">Квалиф.</th>
<th class="text-right px-4 py-2 font-medium">КП</th>
<th class="text-right px-4 py-2 font-medium">Перег.</th>
<th class="text-right px-4 py-2 font-medium">Договор+Счёт</th>
<th class="text-right px-4 py-2 font-medium">Оплата</th>
<th class="text-right px-4 py-2 font-medium">Доставка</th>
<th class="text-right px-4 py-2 font-medium">Отлож.</th>
<th class="text-right px-4 py-2 font-medium">Потерян</th>
<th class="text-right px-4 py-2 font-medium">Всего</th>
```

**Ячейки `<td>` (стр. 31-41) — добавить postponed, оставить lost красным:**
```html
<td class="text-right px-4 py-2 text-ink">{{ r.get('stage_0', 0) }}</td>
<td class="text-right px-4 py-2 text-ink">{{ r.get('stage_1', 0) }}</td>
<td class="text-right px-4 py-2 text-ink">{{ r.get('stage_2', 0) }}</td>
<td class="text-right px-4 py-2 text-ink">{{ r.get('stage_3', 0) }}</td>
<td class="text-right px-4 py-2 text-ink">{{ r.get('stage_4', 0) }}</td>
<td class="text-right px-4 py-2 text-ink">{{ r.get('stage_5', 0) }}</td>
<td class="text-right px-4 py-2 text-ink">{{ r.get('stage_6', 0) }}</td>
<td class="text-right px-4 py-2 text-ink">{{ r.get('stage_7', 0) }}</td>
<td class="text-right px-4 py-2 text-amber-600">{{ r.get('stage_postponed', 0) }}</td>
<td class="text-right px-4 py-2 text-red-600">{{ r.get('stage_lost', 0) }}</td>
<td class="text-right px-4 py-2 font-medium text-ink">{{ r.total }}</td>
```
> Ключ `stage_postponed` формируется в `report_service.py:20` как `f"stage_{stage}"` → для `stage='postponed'` даст `'stage_postponed'`. Работает без правок report_service (динамический ключ).

### 4. `app/services/import_service.py` (сверить, правок НЕТ)

`determine_stage` (стр. 88-99) возвращает `"0","1","3","4"`. Все эти коды сохранили семантику (0=Серые, 1=В работе, 3=КП отправлено, 4=Переговоры). Стр. 165 (`lead.stage='lost'`) — unchanged. **Кодер СВЕРЯЕТ и отмечает в SUMMARY что изменений нет.**

### 5. `app/schemas.py`, `app/routes/leads.py`, `app/routes/tasks.py` (сверить, правок НЕТ)

- `schemas.py:27` — `stage: str = "0"` (код «Серые лиды» unchanged).
- `leads.py:250` — создание лида `stage="0"` (unchanged).
- `leads.py:439` — `if lead.stage == "lost"` (unchanged).
- `tasks.py:65,90` — `Lead.stage != "lost"` (unchanged).
- Все используют unchanged коды. **Кодер СВЕРЯЕТ и отмечает в SUMMARY.**

### 6. `scripts/migrate_stages_v11.py` (новый)

```python
"""Одноразовая миграция стадий воронки (фаза 11).

Перенос кодов:
  6 «Счёт выставлен» → 5 «Договор + Счёт» (merge с существующим кодом 5)
  7 «Оплачено»      → 6 «Оплачено» (сдвиг)

Коды 0,1,2,3,4,lost — unchanged. postponed, новый код 7 — без данных.

Запуск: ОДИН РАЗ на целевой БД. Перед запуском делает бэкап.
Идемпотентность частичная: повторный запуск безопасен только если
миграция ещё не применена (проверка по отсутствию кода '6' в значении
«Счёт выставлен» невозможна без исходных labels — опираемся на бэкап)."""
import shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path

DB = Path("storage/crm.db")

def main():
    if not DB.exists():
        print(f"БД не найдена: {DB}"); sys.exit(1)

    # 1. БЭКАП (обязательно)
    bak = DB.with_name(f"crm.db.before-migrate-v11-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(DB, bak)
    print(f"Бэкап: {bak}")

    con = sqlite3.connect(DB); cur = con.cursor()

    # Контрольный снимок «до»
    before = dict(cur.execute("SELECT stage, COUNT(*) FROM leads GROUP BY stage").fetchall())
    print("До:", before)

    # 2. Сдвиг 7 → 6 через временный маркер (коллизия: 6 валиден до миграции)
    #    Порядок: 7 → _tmp_paid → (5,6 → 5) → _tmp_paid → 6
    cur.execute("UPDATE leads SET stage='_tmp_paid' WHERE stage='7'")
    cur.execute("UPDATE stage_history SET from_stage='_tmp_paid' WHERE from_stage='7'")
    cur.execute("UPDATE stage_history SET to_stage='_tmp_paid'   WHERE to_stage='7'")

    # 3. Merge 5,6 → 5 (бывшие «Договор» и «Счёт выставлен» → «Договор + Счёт»)
    cur.execute("UPDATE leads SET stage='5' WHERE stage IN ('5','6')")
    cur.execute("UPDATE stage_history SET from_stage='5' WHERE from_stage IN ('5','6')")
    cur.execute("UPDATE stage_history SET to_stage='5'   WHERE to_stage   IN ('5','6')")

    # 4. Финал: _tmp_paid → 6 («Оплачено»)
    cur.execute("UPDATE leads SET stage='6' WHERE stage='_tmp_paid'")
    cur.execute("UPDATE stage_history SET from_stage='6' WHERE from_stage='_tmp_paid'")
    cur.execute("UPDATE stage_history SET to_stage='6'   WHERE to_stage='_tmp_paid'")

    con.commit()

    # Контрольный снимок «после»
    after = dict(cur.execute("SELECT stage, COUNT(*) FROM leads GROUP BY stage").fetchall())
    print("После:", after)

    # Санитарные проверки
    tmp = cur.execute("SELECT COUNT(*) FROM leads WHERE stage='_tmp_paid'").fetchone()[0]
    assert tmp == 0, f"Остались _tmp_paid записи: {tmp}"
    htmp = cur.execute("SELECT COUNT(*) FROM stage_history WHERE from_stage='_tmp_paid' OR to_stage='_tmp_paid'").fetchone()[0]
    assert htmp == 0, f"Остались _tmp_paid в history: {htmp}"

    con.close()
    print("OK. Миграция применена. Суммы лидов до/после должны совпасть по затронутым кодам.")

if __name__ == "__main__":
    main()
```

> ⚠️ Запуск на ПРОД-БД — отдельная операция Owner, НЕ часть кодерской задачи. Кодер пишет скрипт и тестирует его локально на КОПИИ БД (`storage/crm.db.prod-fresh` или подобной), подтвержая что суммы сходятся и _tmp_paid не остаётся. В SUMMARY указать: «скрипт готов и протестирован локально, запуск на проде — за Owner».

## Шаги выполнения

1. `app/services/funnel_service.py` — STAGES, STAGE_LABELS, STAGE_COLORS, validate_transition (+ postponed).
2. `app/services/report_service.py` — сверить стр. 85 и 110 (правок вероятно нет, отметить в SUMMARY).
3. `app/templates/funnel_report.html` — заголовки и ячейки под 10 стадий (+ stage_postponed).
4. `app/services/import_service.py`, `app/schemas.py`, `app/routes/leads.py`, `app/routes/tasks.py` — сверить unchanged коды, отметить в SUMMARY.
5. `scripts/migrate_stages_v11.py` — написать, протестировать на копии БД локально.
6. Ручная проверка: канбан показывает 10 колонок, drag-and-drop работает, отчёт по воронке показывает все стадии, карточка лида показывает новый stage_label.

## Acceptance criteria (gate)

- [ ] Канбан показывает **10 колонок** в порядке: Серые лиды, В работе, Квалифицирован, КП отправлено, Переговоры, Договор + Счёт, **Оплачено, Доставлено**, Отложенный спрос, Потерян.
- [ ] Drag-and-drop работает между всеми 10 колонками (включая postponed).
- [ ] Лид в стадии «Договор + Счёт» после миграции (бывший код 5 «Договор») отображается корректно.
- [ ] Лид в стадии «Оплачено» после миграции (бывший код 7) отображается в колонке 6 «Оплачено», НЕ в «Доставлено».
- [ ] Карточка лида показывает актуальный stage_label для каждой стадии.
- [ ] Отчёт по воронке (`funnel_report.html`) показывает 10 колонок с правильными заголовками и данными, включая stage_postponed (пока 0).
- [ ] `validate_transition` разрешает переход в «Отложенный спрос» (postponed) без gate (как lost).
- [ ] `report_service.py:85` KPI конверсии не падает (labels есть для всех кодов).
- [ ] `report_service.py:110-121` расчёт узких мест не падает с KeyError (STAGE_LABELS покрывает все коды из linear_stages).
- [ ] `scripts/migrate_stages_v11.py` протестирован на копии БД: суммы лидов по затронутым кодам до/после сходятся, _tmp_paid не остаётся, бэкап создаётся.
- [ ] После миграции в БД НЕТ лидов с кодом 6 в значении «Счёт выставлен» (теперь 6 = «Оплачено»).
- [ ] В коде НЕТ захардкоженных названий стадий кроме funnel_report.html (grep по «Серые лиды», «Договор + Счёт», «Доставлено», «Отложенный спрос» находит их только в funnel_service.py и funnel_report.html).
- [ ] SUMMARY явно отмечает: report_service.py:85,110 — unchanged (сверено); import_service.py — unchanged; schemas/leads/tasks — unchanged.

## Не делаем (YAGNI)

- НЕ вводим новый enum-тип для стадий (поля остаются String) — миграция схемы избыточна, строковые коды работают.
- НЕ переименовываем цифровые коды в строковые («gray», «paid» и т.п.) — переиспользование существующих кодов минимально ломает данные.
- НЕ добавляем gate для переходов 3→4→5→6→7 (свободные, как раньше) — бизнес не просил.
- НЕ запускаем миграцию на прод-БД в рамках фазы — это отдельная операция Owner.
- НЕ трогаем канбан-шаблоны и карточку лида (дата-драйвены).
- НЕ меняем KPI-состав в report_service.py:85 (3..7) — семантика сохранилась.
- НЕ включаем postponed в linear_stages — это нелинейный исход, сломает расчёт конверсии между соседями.
