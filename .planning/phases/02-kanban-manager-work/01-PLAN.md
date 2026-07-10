---
phase: 2-kanban-manager-work
plan: "01"
slice: 2-01
type: execute
wave: 1
depends_on:
  - phase-1
requirements:
  - CRM-2-01
autonomous: true
files_modified:
  - app/main.py
  - app/routes/dashboard.py
  - app/templates/base.html
  - app/templates/dashboard.html
  - app/services/phone_parser.py
  - app/services/import_service.py
  - app/schemas.py
files_created:
  - app/routes/leads.py
  - app/routes/contacts.py
  - app/routes/comments.py
  - app/routes/tasks.py
  - app/services/funnel_service.py
  - app/templates/kanban.html
  - app/templates/lead_card.html
  - app/templates/partials/lead_card_content.html
  - app/templates/partials/contact_row.html
  - app/templates/partials/contact_log_row.html
  - app/templates/partials/comment_row.html
  - app/templates/partials/task_row.html
  - app/templates/partials/kanban_column.html
  - app/templates/tasks.html
  - app/static/js/kanban.js
must_haves:
  truths:
    - "D-01: app/services/funnel_service.py содержит STAGES (список стадий 0..7 + lost), STAGE_LABELS (русские названия), validate_transition(lead, from_stage, to_stage) -> (bool, list[str]) с воротами: 0→1 требует assigned_manager_id; 1→2 требует хотя бы один Contact с is_decision_maker=True и rapeseed_verified=True; 2→3 без жёстких ворот; остальные переходы свободны"
    - "D-02: app/services/funnel_service.py содержит async change_stage(session, lead_id, to_stage, user_id) — меняет стадию, создаёт StageHistory запись, обновляет stage_changed_at"
    - "D-03: GET /kanban отдаёт HTML-канбан: 9 колонок (стадии 0..7 + lost), в каждой — карточки лидов (имя, уровень, приоритет, регион). Карточки draggable через SortableJS"
    - "D-04: GET /kanban поддерживает query-параметры: manager (all/my — по умолчанию my для manager-роли, all для supervisor/admin), region (id), level (A/B/C), priority (1/2/3)"
    - "D-05: POST /api/leads/{id}/stage принимает {stage: str} через HTMX, вызывает funnel_service.change_stage, возвращает обновлённую колонку-источник и колонку-приёмник (HTML-фрагменты)"
    - "D-06: При невыполнении ворот transition — POST /api/leads/{id}/stage возвращает HTTP 422 + JSON {errors: [...]} с человекочитаемыми сообщениями; канбан-карточка остаётся в исходной колонке"
    - "D-07: GET /leads/{id} отдаёт карточку лида (HTMX-модалка или отдельная страница): реквизиты, верификация рапса (объём, тайминг, verified), контакты, журнал звонков, комментарии, таски — всё на одной странице с табами"
    - "D-08: POST /leads/{id}/contacts — добавление контакта (name, position, phone, email, is_decision_maker) через HTMX-форму; новый контакт появляется в списке без перезагрузки"
    - "D-09: POST /leads/{id}/contacts/{contact_id}/toggle-dm — переключение флага is_decision_maker через HTMX (чекбокс); обновляет строку контакта"
    - "D-10: POST /leads/{id}/contact-log — добавление записи журнала (contact_type, result, outcome, next_action_date) через HTMX; если next_action_date указана — автоматически создаётся Task с title='Перезвонить: {lead.name}', due_date=next_action_date"
    - "D-11: POST /leads/{id}/comments — добавление комментария через HTMX; новый комментарий вверху списка"
    - "D-12: POST /leads/{id}/edit — редактирование полей лида (rapeseed_verified, rapeseed_volume, harvest_timing, level, priority, inn, head_name, site, general_comment, done_summary, todo_summary) через HTMX-форму"
    - "D-13: GET /tasks — страница тасков текущего пользователя: фильтр (pending/in_progress/done), сортировка по due_date; таски с просроченной датой подсвечены красным"
    - "D-14: POST /api/tasks/{id}/status — смена статуса таска через HTMX"
    - "D-15: Sidebar в base.html обновлён: рабочие ссылки на /kanban, /tasks, / (дашборд); supervisor/admin видит доп. ссылку 'Все лиды' (manager=all)"
    - "D-16: phone_parser.py regex исправлен — захватывает полные номера (до 20 символов), не урезая. Тест: parse_phones('7 (811) 523-23-36') → phone содержит '7 (811) 523-23-36'"
    - "D-17: import_service.py: ИНН сохраняется без '.0' суффикса (если val — float и val == int(val), конвертировать в int → str); level нормализуется — всё не-A/B/C → None"
    - "D-18: Канбан доступен после логина: admin видит все лиды, manager — только assigned_manager_id = свой id (пока все лиды unassigned — manager видит пустой канбан, admin видит все)"
  artifacts:
    - path: app/services/funnel_service.py
      provides: "Правила воронки: стадии, ворота перехода, аудит через StageHistory"
    - path: app/routes/leads.py
      provides: "Карточка лида + смена стадии + редактирование + CRUD контактов/журнала/комментариев"
    - path: app/templates/kanban.html
      provides: "Канбан-доска с drag-and-drop через SortableJS"
  key_links:
    - from: app/templates/kanban.html
      to: app/static/js/kanban.js
      via: "Sortable.create + HTMX fetch on end"
      pattern: "drag-and-drop stage change"
    - from: app/routes/leads.py
      to: app/services/funnel_service.py
      via: "validate_transition + change_stage"
      pattern: "gate validation"
    - from: app/routes/leads.py
      to: app/templates/partials/*.html
      via: "TemplateResponse fragments"
      pattern: "HTMX partial render"
---

# Plan 2-01 — Канбан и работа менеджера (Wave 1)

**Phase:** 2 — kanban-manager-work
**Wave:** B-1
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

Фаза 1 создала фундамент: 583 лида в БД, аутентификация, базовый дашборд со счётчиками. Сейчас менеджер видит только цифры, но не может работать с лидами. Фаза 2 превращает CRM из «витрины статистики» в рабочий инструмент: канбан-доска для перетаскивания лидов по стадиям воронки, карточка лида со всеми данными, журнал контактов, комментарии, таски.

**Текущее состояние кода (из code review Фазы 1):**
- `app/models.py` — все 10 моделей готовы, связи + cascade на месте
- `app/routes/dashboard.py` — только GET / со счётчиками
- `app/templates/` — base.html (sidebar), dashboard.html, login.html
- `app/services/import_service.py` — импорт xlsx (нужны 2 фикса-долга из Фазы 1)
- `app/services/phone_parser.py` — парсер телефонов (нужен фикс regex)
- `app/auth.py` — get_current_user, require_role готовы
- `app/main.py` — роуты auth + dashboard подключены
- БД: 583 лида, 662 контакта, 306 записей журнала, 0 тасков, 0 stage_history

**Долги Фазы 1, закрываемые здесь:**
- D-B: парсер телефонов урезает номера → фикс в phone_parser.py
- D-C: аномальные level («Исключён», «Источник») → нормализация в import_service.py
- D-A: ИНН с `.0` → фикс в import_service.py

## Что делает кодер (пофайлово)

### 1. `app/services/funnel_service.py` (новый) — логика воронки

```python
STAGES = ["0", "1", "2", "3", "4", "5", "6", "7", "lost"]

STAGE_LABELS = {
    "0": "Сырые лиды",
    "1": "В работе",
    "2": "Квалифицирован",
    "3": "КП отправлено",
    "4": "Переговоры",
    "5": "Договор",
    "6": "Счёт выставлен",
    "7": "Оплачено",
    "lost": "Потерян",
}

STAGE_COLORS = {
    "0": "gray", "1": "blue", "2": "indigo", "3": "purple",
    "4": "orange", "5": "yellow", "6": "cyan", "7": "green",
    "lost": "red",
}
```

**`def validate_transition(lead: Lead, from_stage: str, to_stage: str) -> tuple[bool, list[str]]`**

Возвращает `(ok, errors)`. Правила:
- `to_stage == "lost"` → всегда ok (потерять можно с любой стадии)
- `from_stage == "0" → "1"` → ok если `lead.assigned_manager_id is not None`, иначе error "Назначьте менеджера"
- `from_stage == "1" → "2"` → ok если есть хотя бы один Contact с `is_decision_maker=True` AND `lead.rapeseed_verified == True`, иначе errors: "Отметьте ЛПР среди контактов" и/или "Подтвердите выращивание рапса"
- Остальные переходы → ok (свободные)
- `from_stage == to_stage` → ok (no-op)

**`async def change_stage(session, lead_id: int, to_stage: str, user_id: int) -> Lead`**

1. Загрузить lead с `selectinload(Lead.contacts)`
2. Вызвать `validate_transition`
3. Если not ok → raise ValueError(errors) (роут ловит и возвращает 422)
4. Создать `StageHistory(lead_id, from_stage=lead.stage, to_stage, changed_by, changed_at=now)`
5. Обновить `lead.stage = to_stage`, `lead.stage_changed_at = now`
6. Если `to_stage == "lost"` и `lead.loss_reason` пустой → не блокировать, но установить дефолт "Причина не указана"
7. `session.add`, `await session.flush`
8. Вернуть lead

### 2. `app/services/phone_parser.py` (модификация) — фикс долга D-B

**Сейчас:** regex `(?:\+?7|8)[\s\-()]*\d{2,4}[\s\-()]*\d{2,4}[\s\-()]*\d{2,4}` урезает номера.

**Задача:** заменить regex на паттерн, захватывающий полные российские номера (11 цифр после кода страны). Рекомендуемый паттерн:

```python
PHONE_RE = re.compile(
    r'(?:\+?7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}'
    r'|(?:\+?7|8)[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}[\s\-()]*\d{2}'
    r'|\d{2,3}[\s\-()]*\d{2}[\s\-()]*\d{2}[\s\-()]*\d{2}'  # городские без кода
)
```

Или проще — жадный паттерн: всё что похоже на телефон (цифры, пробелы, дефисы, скобки, начинающиеся с +7/7/8 или с цифры):

```python
PHONE_RE = re.compile(r'(?:\+?[78][\s\-()]*)?(?:\d[\s\-()]*\d[\s\-()]*\d[\s\-()]*\d[\s\-()]*\d[\s\-()]*\d[\s\-()]*\d[\s\-()]*\d[\s\-()]*\d[\s\-()]*\d)')
```

Главный критерий: `parse_phones('7 (811) 523-23-36')` → phone содержит полный номер `7 (811) 523-23-36`, а не урезанный `7 (811) 523-23`.

**Тест:** добавить `if __name__ == "__main__":` блок с проверочными кейсами.

### 3. `app/services/import_service.py` (модификация) — фикс долгов D-A, D-C

**D-A — ИНН как float:**
В функции `_str_or_none` добавить:
```python
def _str_or_none(val) -> str | None:
    if val is None or pd.isna(val):
        return None
    # ИНН приходит как float из pandas — убираем .0
    if isinstance(val, float) and val == int(val):
        val = int(val)
    s = str(val).strip()
    if s.lower() in ("nan", "—", "-", ""):
        return None
    return s
```

**D-C — нормализация level:**
В функции импорта, при создании Lead:
```python
level_raw = _str_or_none(row.get(col_map.get("level", "")))
level_val = level_raw if level_raw in ("A", "B", "C") else None
```
Передать `level=level_val` вместо `level=level_raw`.

⚠ **Внимание:** эти фиксы в import_service влияют на новые импорты. Существующая БД уже содержит данные с `.0` в ИНН и аномальными level. Кодер должен добавить функцию `async def cleanup_existing_data(session)` в import_service.py, которая:
1. Для всех leads: если inn заканчивается на `.0` → убрать `.0`
2. Для всех leads: если level не в (A,B,C,None) → установить None

И вызвать её в `scripts/import_xlsx.py` после импорта (или отдельным скриптом `scripts/cleanup_data.py`).

### 4. `app/routes/leads.py` (новый) — главный роутер работы с лидами

Подключается в `app/main.py`: `app.include_router(leads.router)`

**Маршруты:**

#### `GET /kanban`
- Query params: `manager` (all/my, default зависит от роли), `region` (int?), `level` (str?), `priority` (int?)
- Логика фильтрации:
  - role=manager → по умолчанию `manager=my` (только assigned_manager_id == current_user.id)
  - role=supervisor/admin → по умолчанию `manager=all`
  - `manager=all` доступно только supervisor/admin; для manager — принудительно my
- Запрос: `select(Lead).options(selectinload(Lead.region)).where(фильтры)`
- Рендер: `kanban.html` с лидами, сгруппированными по stage

#### `GET /leads/{id}` — карточка лида
- Загрузка: `select(Lead).options(selectinload(Lead.contacts), selectinload(Lead.contact_logs), selectinload(Lead.comments), selectinload(Lead.tasks), selectinload(Lead.region))`
- Рендер: `lead_card.html`

#### `POST /api/leads/{id}/stage` — смена стадии (HTMX)
- Body: `stage: str = Form(...)`
- Вызывает `funnel_service.change_stage`
- При успехе: возвращает HTML-фрагмент — обновлённые колонки (или пустой 200 + HTMX swap через events)
- При ошибке ворот (ValueError): HTTP 422 + `{"errors": [...]}`
- **Важно:** HTMX на клиенте слушает response: если 422 → показать alert с ошибками, вернуть карточку в исходную колонку (SortableJS `.cancel()`)

#### `POST /leads/{id}/edit` — редактирование полей (HTMX)
- Form fields: `rapeseed_verified` (checkbox), `rapeseed_volume`, `harvest_timing`, `level`, `priority`, `inn`, `head_name`, `site`, `general_comment`, `done_summary`, `todo_summary`, `loss_reason` (если stage=lost)
- Обновляет lead, возвращает обновлённый фрагмент секции

#### `POST /leads/{id}/contacts` — добавить контакт (HTMX)
- Form: `name`, `position`, `phone`, `email`, `is_decision_maker` (checkbox)
- Создаёт Contact, возвращает `partials/contact_row.html` (новая строка)

#### `POST /leads/{id}/contacts/{contact_id}/toggle-dm` — переключить ЛПР (HTMX)
- Инвертирует `is_decision_maker`, возвращает обновлённую `partials/contact_row.html`

#### `POST /leads/{id}/contact-log` — добавить запись журнала (HTMX)
- Form: `contact_type` (select: call/email/visit), `result` (textarea), `outcome` (select), `next_action_date` (date input)
- Создаёт ContactLog
- Если `next_action_date` указана → создаёт Task: `title=f"Перезвонить: {lead.name}"`, `due_date=next_action_date`, `assigned_to=current_user.id`, `lead_id=lead.id`, `priority=1`
- Возвращает `partials/contact_log_row.html` (новая строка вверху)

#### `POST /leads/{id}/comments` — добавить комментарий (HTMX)
- Form: `body` (textarea)
- Создаёт Comment, возвращает `partials/comment_row.html`

#### `POST /leads/{id}/assign` — назначить менеджера (HTMX)
- Form: `manager_id` (select из списка users)
- Доступно supervisor/admin
- Устанавливает `assigned_manager_id`, возвращает обновлённую карточку

### 5. `app/routes/contacts.py` — НЕ нужен

Контакты — только в контексте лида. Все роуты в `leads.py`.

### 6. `app/routes/comments.py` — НЕ нужен

Комментарии — только в контексте лида. Все роуты в `leads.py`.

### 7. `app/routes/tasks.py` (новый) — страница тасков

Подключается в `app/main.py`.

#### `GET /tasks`
- Query: `status` (pending/in_progress/done/all, default=pending)
- Запрос: `select(Task).where(Task.assigned_to == current_user.id).order_by(Task.due_date)`
- Просроченные: `due_date < now() AND status in (pending, in_progress)` → подсветить красным
- Рендер: `tasks.html`

#### `POST /api/tasks/{id}/status` — сменить статус (HTMX)
- Form: `status` (select)
- Обновляет Task, если `status=done` → `completed_at=now()`
- Возвращает обновлённую строку

### 8. `app/routes/dashboard.py` (модификация)

- GET / остаётся как есть (счётчики)
- Sidebar ссылка «Дашборд» → `/`
- Добавить в контекст `current_user` (уже передаётся, но убедиться)

### 9. `app/templates/base.html` (модификация)

Обновить sidebar-навигацию:
```html
<nav class="space-y-2">
    <a href="/" class="...">Дашборд</a>
    <a href="/kanban" class="...">Канбан</a>
    <a href="/tasks" class="...">Таски</a>
    {% if current_user.role.value in ('supervisor', 'admin') %}
    <a href="/kanban?manager=all" class="...">Все лиды</a>
    {% endif %}
</nav>
```

Добавить в `<head>` SortableJS CDN:
```html
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"></script>
```

### 10. `app/templates/kanban.html` (новый)

Структура:
```html
{% extends "base.html" %}
{% block content %}

<!-- Фильтры -->
<div class="flex gap-4 mb-4">
    <select name="region" hx-get="/kanban" hx-target="#kanban-board" hx-include="[name='level'],[name='priority'],[name='manager']">
        <option value="">Все регионы</option>
        {% for r in regions %}<option value="{{ r.id }}">{{ r.name }}</option>{% endfor %}
    </select>
    <!-- аналогично level, priority, manager -->
</div>

<!-- Канбан -->
<div id="kanban-board" class="flex gap-3 overflow-x-auto">
    {% for stage in stages %}
    <div class="kanban-column flex-1 min-w-[250px] bg-gray-50 rounded-lg p-3" data-stage="{{ stage.code }}">
        <div class="flex justify-between items-center mb-3">
            <h3 class="font-semibold text-sm">{{ stage.label }}</h3>
            <span class="text-xs text-gray-400 bg-gray-200 rounded-full px-2">{{ stage.count }}</span>
        </div>
        <div class="kanban-cards space-y-2" data-stage="{{ stage.code }}">
            {% for lead in stage.leads %}
            {% include "partials/kanban_card.html" %}
            {% endfor %}
        </div>
    </div>
    {% endfor %}
</div>

<script src="/static/js/kanban.js"></script>
{% endblock %}
```

Карточка лида в колонке (`partials/kanban_card.html`):
```html
<div class="kanban-card bg-white rounded shadow p-3 cursor-move"
     data-lead-id="{{ lead.id }}" data-stage="{{ lead.stage }}">
    <div class="font-medium text-sm truncate">{{ lead.name }}</div>
    <div class="flex gap-2 mt-1 text-xs text-gray-500">
        {% if lead.level %}<span class="badge level-{{ lead.level }}">{{ lead.level }}</span>{% endif %}
        {% if lead.priority %}<span>Приоритет {{ lead.priority }}</span>{% endif %}
    </div>
    <div class="text-xs text-gray-400 mt-1">{{ lead.region.name if lead.region else '—' }}</div>
</div>
```

### 11. `app/static/js/kanban.js` (новый) — drag-and-drop логика

```javascript
document.querySelectorAll('.kanban-cards').forEach(function(el) {
    new Sortable(el, {
        group: 'kanban',
        animation: 150,
        onEnd: function(evt) {
            var leadId = evt.item.dataset.leadId;
            var toStage = evt.to.dataset.stage;
            var fromStage = evt.from.dataset.stage;

            fetch('/api/leads/' + leadId + '/stage', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: 'stage=' + encodeURIComponent(toStage)
            }).then(function(resp) {
                if (!resp.ok) {
                    // Вернуть карточку обратно
                    evt.from.appendChild(evt.item);
                    return resp.json().then(function(data) {
                        alert('Невозможно сменить стадию:\n' + data.errors.join('\n'));
                    });
                }
                // Обновить счётчики колонок
                updateColumnCounts();
            });
        }
    });
});

function updateColumnCounts() {
    document.querySelectorAll('.kanban-column').forEach(function(col) {
        var count = col.querySelectorAll('.kanban-card').length;
        var badge = col.querySelector('.kanban-count');
        if (badge) badge.textContent = count;
    });
}
```

⚠ **Важно:** SortableJS при `onEnd` уже переместил DOM-элемент. Если сервер отклонил (422) — нужно вернуть элемент в исходную колонку (`evt.from.appendChild(evt.item)`).

### 12. `app/templates/lead_card.html` (новый) — карточка лида

Полная страница (не модалка — проще для HTMX):

```html
{% extends "base.html" %}
{% block content %}

<div class="mb-4">
    <a href="/kanban" class="text-blue-600 text-sm">← Назад к канбану</a>
</div>

<div class="bg-white rounded-lg shadow p-6 mb-4">
    <h1 class="text-2xl font-bold">{{ lead.name }}</h1>
    <div class="flex gap-4 mt-2 text-sm text-gray-600">
        <span>Стадия: <strong>{{ stage_label }}</strong></span>
        <span>Уровень: <strong>{{ lead.level or '—' }}</strong></span>
        <span>Регион: <strong>{{ lead.region.name if lead.region else '—' }}</strong></span>
    </div>
</div>

<!-- Табы -->
<div class="flex border-b mb-4">
    <button class="tab-btn active" data-tab="info">Информация</button>
    <button class="tab-btn" data-tab="contacts">Контакты ({{ lead.contacts|length }})</button>
    <button class="tab-btn" data-tab="log">Журнал ({{ lead.contact_logs|length }})</button>
    <button class="tab-btn" data-tab="comments">Комментарии ({{ lead.comments|length }})</button>
    <button class="tab-btn" data-tab="tasks">Таски ({{ lead.tasks|length }})</button>
</div>

<!-- Таб: Информация -->
<div id="tab-info" class="tab-content">
    {% include "partials/lead_info_form.html" %}
</div>

<!-- Таб: Контакты -->
<div id="tab-contacts" class="tab-content hidden">
    {% include "partials/contacts_list.html" %}
</div>

<!-- и т.д. для остальных табов -->

{% endblock %}
```

### 13. Partials (новые) — HTMX-фрагменты

Каждый partial — переиспользуемый HTML-фрагмент, который роут возвращает для HTMX-swap:

- `partials/lead_info_form.html` — форма редактирования полей лида (rapeseed_verified, volume, timing, level, priority, inn, и т.д.)
- `partials/contacts_list.html` — список контактов + форма добавления
- `partials/contact_row.html` — одна строка контакта (с чекбоксом ЛПР)
- `partials/contact_log_list.html` — список записей журнала + форма добавления
- `partials/contact_log_row.html` — одна запись журнала
- `partials/comments_list.html` — список комментариев + форма
- `partials/comment_row.html` — один комментарий
- `partials/tasks_list.html` — список тасков лида
- `partials/task_row.html` — одна таска

### 14. `app/templates/tasks.html` (новый) — страница тасков

```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">Мои таски</h1>

<!-- Фильтр -->
<div class="flex gap-2 mb-4">
    <a href="/tasks?status=pending" class="...">Активные</a>
    <a href="/tasks?status=done" class="...">Завершённые</a>
    <a href="/tasks?status=all" class="...">Все</a>
</div>

<div class="space-y-2">
    {% for task in tasks %}
    <div class="bg-white rounded shadow p-3 flex items-center justify-between
                {% if task.is_overdue %}border-l-4 border-red-500{% endif %}">
        <div>
            <div class="font-medium">{{ task.title }}</div>
            <div class="text-xs text-gray-500">
                {{ task.due_date.strftime('%d.%m.%Y') if task.due_date else 'без срока' }}
                {% if task.lead %}· <a href="/leads/{{ task.lead.id }}" class="text-blue-500">{{ task.lead.name }}</a>{% endif %}
            </div>
        </div>
        <select hx-post="/api/tasks/{{ task.id }}/status" hx-target="closest div"
                name="status" class="text-sm border rounded px-2 py-1">
            <option value="pending" {% if task.status=='pending' %}selected{% endif %}>Ожидает</option>
            <option value="in_progress" {% if task.status=='in_progress' %}selected{% endif %}>В работе</option>
            <option value="done" {% if task.status=='done' %}selected{% endif %}>Готово</option>
            <option value="cancelled" {% if task.status=='cancelled' %}selected{% endif %}>Отменено</option>
        </select>
    </div>
    {% else %}
    <div class="text-gray-400 text-center py-8">Нет тасков</div>
    {% endfor %}
</div>
{% endblock %}
```

### 15. `app/main.py` (модификация)

Добавить подключение новых роутеров:
```python
from app.routes import auth, dashboard, leads, tasks
app.include_router(leads.router)
app.include_router(tasks.router)
```

### 16. `app/schemas.py` (модификация)

Добавить Pydantic-схемы для валидации форм (если кодер использует их вместо прямого Form()):
- `ContactCreate`, `ContactLogCreate`, `CommentCreate`, `TaskStatusUpdate`, `LeadEdit`

### 17. `scripts/cleanup_data.py` (новый) — фикс существующих данных

Standalone-скрипт, применяет фиксы долгов D-A и D-C к существующей БД:
1. Убрать `.0` из ИНН всех лидов
2. Нормализовать level (не-A/B/C → None)
3. Перезапарсить телефоны из `lead.rapeseed_info`? — НЕТ, телефоны не сохранены в исходном виде. Оставить как есть, фикс только для новых импортов.

## Anti-conflict (важно для кодера)

**НЕ ТРОГАТЬ:**
- `Екатерина.xlsx`, `_Вероника.xlsx` — исходные файлы
- `.planning/` — артефакты техлида
- `app/models.py` — схемы БД не меняются в этой фазе (модели готовы из Фазы 1)
- `app/auth.py` — аутентификация не меняется
- `app/database.py` — не меняется

**Модифицировать (аккуратно, не ломая Фазу 1):**
- `app/main.py` — только добавление `include_router`
- `app/templates/base.html` — только sidebar + SortableJS CDN
- `app/routes/dashboard.py` — без изменений (или минимальные)
- `app/services/phone_parser.py` — только regex паттерн
- `app/services/import_service.py` — только `_str_or_none` + нормализация level
- `app/schemas.py` — только добавление новых схем

## Готово, когда (success criteria)

- [ ] D-01..D-18 — все выполнены
- [ ] `python run.py` — сервер запускается без ошибок
- [ ] `http://127.0.0.1:8000/kanban` — канбан с 9 колонками, карточки лидов видны (admin видит все 583)
- [ ] Drag-and-drop карточки между колонками — POST `/api/leads/{id}/stage` вызывается
- [ ] Переход 0→1 без assigned_manager → 422 + alert с сообщением «Назначьте менеджера»
- [ ] Переход 1→2 без ЛПР → 422 + alert «Отметьте ЛПР среди контактов»
- [ ] `http://127.0.0.1:8000/leads/1` — карточка лида с табами (Информация, Контакты, Журнал, Комментарии, Таски)
- [ ] Добавление контакта через HTMX — появляется без перезагрузки
- [ ] Чекбокс ЛПР на контакте — переключается через HTMX
- [ ] Добавление записи журнала с next_action_date → создаётся Task (видна на /tasks)
- [ ] `http://127.0.0.1:8000/tasks` — страница тасков, просроченные подсвечены
- [ ] Смена статуса таска через select — HTMX работает
- [ ] `parse_phones('7 (811) 523-23-36')` → полный номер в результате
- [ ] В БД: ИНН без `.0`, level только A/B/C/NULL
- [ ] Sidebar: рабочие ссылки /kanban, /tasks, /
- [ ] Нет `console.log` / `print` отладочного мусора

## Не готово, когда

- Канбан не отображается (пустой, ошибка рендера)
- Drag-and-drop не работает (SortableJS не подключён, или onEnd не вызывает API)
- Смена стадии проходит без проверки ворот (можно перетащить 1→2 без ЛПР)
- Карточка лида не загружается (ошибка запроса, missing selectinload)
- HTMX-формы не работают (нет partials, неправильные hx-target/hx-swap)
- Таски не создаются из журнала (next_action_date игнорируется)
- Фикс phone_parser ломает существующие контакты (не должно — только новые парсинги)
- Cleanup-скрипт не запущен (ИНН всё ещё с `.0`)

## Что даёт эта фаза

Менеджер получает полноценный рабочий инструмент:
- **Канбан** — перетаскивает лиды по стадиям воронки, система контролирует ворота
- **Карточка лида** — все данные в одном месте: реквизиты, верификация рапса, контакты с ЛПР, журнал звонков, комментарии
- **Журнал контактов** — добавление звонка с авто-созданием напоминания
- **Таски** — дашборд «на сегодня» с просроченными подсветками
- **Долги Фазы 1 закрыты** — телефоны не урезаются, ИНН без `.0`, level нормализован

## Следующий шаг

Фаза 3 — Документооборот: .docx-шаблоны (КП, договор, счёт), генерация через python-docx → PDF, статусы документов, сделки.
