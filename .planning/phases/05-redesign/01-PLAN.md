---
phase: 5-redesign
plan: "01"
slice: 5-01
type: execute
wave: 1
depends_on:
  - phase-4
requirements:
  - CRM-5-01
autonomous: true
files_modified:
  - app/templates/base.html
  - app/templates/login.html
  - app/templates/dashboard.html
  - app/templates/kanban.html
  - app/templates/lead_card.html
  - app/templates/tasks.html
  - app/templates/deals.html
  - app/templates/upload_template.html
  - app/templates/supervisor_dashboard.html
  - app/templates/funnel_report.html
  - app/templates/managers_report.html
  - app/templates/partials/lead_info_form.html
  - app/templates/partials/contacts_list.html
  - app/templates/partials/contact_row.html
  - app/templates/partials/contact_log_list.html
  - app/templates/partials/contact_log_row.html
  - app/templates/partials/comments_list.html
  - app/templates/partials/comment_row.html
  - app/templates/partials/tasks_list.html
  - app/templates/partials/task_row.html
  - app/templates/partials/documents_list.html
  - app/templates/partials/document_row.html
  - app/templates/partials/document_form.html
  - app/templates/partials/deals_list.html
  - app/templates/partials/deal_row.html
  - app/static/css/app.css
files_created:
  - app/static/js/drawer.js
  - app/templates/partials/drawer.html
must_haves:
  truths:
    - "D-01: base.html <head> подключает Geist Sans + Geist Mono через CDN (jsdelivr). Tailwind CDN config расширен: fontFamily.sans=['Geist Sans','system-ui'], fontFamily.mono=['Geist Mono','monospace'], цвета canvas='#F8FAFC', ink='#030213', muted='#717182'"
    - "D-02: base.html <body> использует bg-slate-50 (не bg-gray-100). Sidebar: bg-white border-r border-black/10 (не bg-gray-900). Текст sidebar: text-[#030213] и text-[#717182]. Логотип CRM RAI: font-medium (не font-bold)"
    - "D-03: Во ВСЕХ 25 шаблонах: ни одного font-bold или font-semibold. Все заголовки — font-medium. Метрики/числа — font-medium. Основной текст — font-normal"
    - "D-04: Во ВСЕХ 25 шаблонах: bg-gray-100 заменён на bg-slate-50 (canvas) или bg-white border border-black/10 (surfaces). rounded-lg → rounded-2xl. shadow → border border-black/10"
    - "D-05: Цвета текста: text-gray-900 → text-[#030213] (Ink). text-gray-500/600/700 → text-[#717182] (Muted) для второстепенного текста. Заголовки — text-[#030213]"
    - "D-06: Иерархия CTA: на каждой странице РОВНО ОДНА primary-кнопка (bg-[#030213] text-white). Остальные — secondary (bg-white border border-black/10) или ghost (text-[#717182] hover:text-[#030213]). Заменить все bg-blue-600 на primary/secondary по контексту"
    - "D-07: ИНН, номера счетов, ID, телефоны — обёрнуты в font-mono (Geist Mono) через класс font-mono. Проверить: lead_info_form (ИНН), contact_row (телефон), deal_row (сумма), document_row (номер)"
    - "D-08: Risk Triage цвета применены к статусам: lost→text-red-600, просроченные таски→text-amber-600, сырые лиды→text-blue-500, оплачено→text-emerald-500. Воронка в supervisor_dashboard: бары используют каноничные цвета (не bg-gray-400/bg-blue-400)"
    - "D-09: app/static/js/drawer.js реализует Drawer (SidePanelForm): overlay справа, фиксируется, закрывается по Esc / клику на overlay / кнопке X. HTMX-формы создания/редактирования открываются в drawer вместо inline"
    - "D-10: app/templates/partials/drawer.html — переиспользуемый каркас drawer: <div id='drawer' class='fixed inset-y-0 right-0 w-96 bg-white border-l border-black/10 shadow-xl transform translate-x-full transition-transform'> с слотами для заголовка и контента"
    - "D-11: Контакты, журнал звонков, комментарии, сделки — формы создания вынесены в drawer. На странице остаётся таблица/список + кнопка 'Добавить' (secondary), открывающая drawer. Содержимое drawer загружается через HTMX"
    - "D-12: lead_info_form.html — View/Edit B-Pattern: по умолчанию поля отображаются как Label + Value (без input-рамок). Пустые значения → '—' (text-[#717182]). Кнопка 'Редактировать' (secondary) переключает на Edit Mode (появляются input-границы border-black/10). Сохранить → обратно в View"
    - "D-13: Empty states: все списки (контакты, документы, сделки, таски, комментарии) — при пустом списке показывают иконку + текст + кнопку 'Добавить' по центру. Не просто 'Нет данных'"
    - "D-14: Долг D-H закрыт: documents_list.html — при отсутствии active_templates форма генерации не рендерится, показывается empty state 'Загрузите шаблон на странице Шаблоны' со ссылкой"
    - "D-15: Канбан-карточки: сохраняют card-стиль (board, не list — исключение из C-Pattern). Но стилизованы по канону: bg-white border border-black/10 rounded-2xl. Колонки: bg-slate-50/50 rounded-2xl"
    - "D-16: Контекстные подсказки: длинные описания под заголовками заменены на кнопку-иконку 'i' с tooltip (title='...' или data-tooltip). Минимум 3 места: дашборд (описание воронки), карточка лида (описание верификации рапса), supervisor dashboard (описание просадок)"
    - "D-17: Таблицы (deals, tasks, templates, funnel_report, managers_report): thead → text-[#717182] font-medium, border-b border-black/10. Ячейки → text-sm text-[#030213]. Hover → bg-slate-50"
    - "D-18: Login страница: bg-slate-50 (canvas), карточка bg-white border border-black/10 rounded-2xl p-8. Заголовок font-medium. Кнопка 'Войти' — primary (bg-[#030213])"
  artifacts:
    - path: app/static/js/drawer.js
      provides: "Drawer (SidePanelForm) — боковая панель для создания/редактирования"
    - path: app/templates/partials/drawer.html
      provides: "Переиспользуемый каркас drawer"
    - path: app/static/css/app.css
      provides: "Каноничные CSS-переменные и утилиты"
  key_links:
    - from: app/templates/base.html
      to: app/static/css/app.css
      via: "Tailwind CDN config + Geist fonts + custom CSS vars"
      pattern: "Visual Canon foundation"
    - from: app/static/js/drawer.js
      to: app/templates/partials/drawer.html
      via: "openDrawer(url) / closeDrawer() + HTMX"
      pattern: "Drawer pattern"
---

# Plan 5-01 — Redesign по Visual Canon (Wave 1)

**Phase:** 5 — redesign
**Wave:** B-1
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

Фазы 1–4 создали полностью функциональный CRM: импорт данных, канбан, карточка лида, документооборот, аналитика. Но UI использует дефолтный Tailwind (system-ui, `bg-gray-100`, `font-bold`, `shadow`, `rounded-lg`, `bg-blue-600` везде). Заказчик предоставил детальный Visual Canon (см. `.planning/canon/VISUAL_CANON.md`) — стандарт с существующего проекта RAI Platform.

Фаза 5 — cross-cutting редизайн: применение канона ко всем 25 шаблонам без изменения функциональности. Только HTML/CSS/JS, без правок роутов и моделей.

**Разведка (нарушения канона):**
- `font-bold`/`font-semibold`: ~30 вхождений в 18 шаблонах
- `bg-gray-100`: 5 вхождений (нужно `bg-slate-50`)
- `rounded-lg`: 28 вхождений (нужно `rounded-2xl`)
- `shadow`: 28 вхождений (нужно `border border-black/10`)
- `text-gray-500/600/700`: 66 вхождений (нужно `text-[#717182]`)
- `bg-blue-600`: 15 вхождений (нужно primary/secondary по контексту)
- Inline-формы: 7 в partials (нужно Drawer-паттерн)
- Шрифт: system-ui (нужно Geist Sans/Mono)

## Что делает кодер (по группам)

### Группа 1: Foundation — base.html + app.css

#### `app/templates/base.html` (модификация)

**`<head>` — шрифты + Tailwind config:**

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}CRM RAI{% endblock %}</title>
    <!-- Geist Sans + Mono -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/geist@1/dist/font/geist-sans.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/geist@1/dist/font/geist-mono.css">
    <!-- Tailwind CDN с конфигом -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
    tailwind.config = {
        theme: {
            extend: {
                fontFamily: {
                    sans: ['Geist Sans', 'system-ui', 'sans-serif'],
                    mono: ['Geist Mono', 'monospace'],
                },
                colors: {
                    canvas: '#F8FAFC',
                    ink: '#030213',
                    muted: '#717182',
                },
            },
        },
    }
    </script>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"></script>
    <link rel="stylesheet" href="/static/css/app.css">
</head>
```

**`<body>` — canvas + sidebar:**

```html
<body class="bg-canvas min-h-screen font-sans">
    {% if current_user %}
    <div class="flex">
        <aside class="w-64 bg-white border-r border-black/10 min-h-screen p-4 flex flex-col">
            <div class="text-xl font-medium text-ink mb-6">CRM RAI</div>
            <nav class="space-y-1 flex-1">
                <a href="/" class="block px-3 py-2 rounded-lg text-sm text-ink hover:bg-slate-100">Дашборд</a>
                <a href="/kanban" class="block px-3 py-2 rounded-lg text-sm text-ink hover:bg-slate-100">Канбан</a>
                <a href="/tasks" class="block px-3 py-2 rounded-lg text-sm text-ink hover:bg-slate-100">Таски</a>
                <a href="/templates" class="block px-3 py-2 rounded-lg text-sm text-ink hover:bg-slate-100">Шаблоны</a>
                <a href="/deals" class="block px-3 py-2 rounded-lg text-sm text-ink hover:bg-slate-100">Сделки</a>
                {% if current_user.role.value in ('supervisor', 'admin') %}
                <a href="/reports" class="block px-3 py-2 rounded-lg text-sm text-ink hover:bg-slate-100">Аналитика</a>
                <a href="/kanban?manager=all" class="block px-3 py-2 rounded-lg text-sm text-ink hover:bg-slate-100">Все лиды</a>
                {% endif %}
            </nav>
            <div class="pt-4 border-t border-black/10">
                <div class="text-sm text-ink">{{ current_user.full_name }}</div>
                <div class="text-xs text-muted">{{ current_user.role.value }}</div>
                <a href="/logout" class="block mt-2 text-sm text-red-600 hover:text-red-700">Выйти</a>
            </div>
        </aside>
        <main class="flex-1 p-6">
            {% block content %}{% endblock %}
        </main>
    </div>
    <!-- Drawer overlay -->
    <div id="drawer-overlay" class="fixed inset-0 bg-black/20 z-40 hidden" onclick="closeDrawer()"></div>
    <div id="drawer" class="fixed inset-y-0 right-0 w-96 bg-white border-l border-black/10 z-50 transform translate-x-full transition-transform duration-200 overflow-y-auto">
        <div id="drawer-content"></div>
    </div>
    <script src="/static/js/drawer.js"></script>
    {% else %}
    {% block fullpage %}{% endblock %}
    {% endif %}
</body>
```

#### `app/static/css/app.css` (модификация)

```css
/* Visual Canon — CRM RAI */

/* Каноничные цвета как CSS-переменные */
:root {
    --canvas: #F8FAFC;
    --ink: #030213;
    --muted: #717182;
    --border: rgba(0, 0, 0, 0.1);
}

body {
    font-family: 'Geist Sans', system-ui, sans-serif;
    color: var(--ink);
    background-color: var(--canvas);
}

/* Mono для технических данных */
.font-mono, code, pre {
    font-family: 'Geist Mono', monospace;
}

/* Drawer */
#drawer.open {
    transform: translateX(0);
}

/* Tooltip для контекстных подсказок */
.tooltip-trigger {
    position: relative;
    cursor: help;
}
.tooltip-trigger:hover .tooltip-content,
.tooltip-trigger:focus .tooltip-content {
    display: block;
}
.tooltip-content {
    display: none;
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    background: var(--ink);
    color: white;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12px;
    white-space: nowrap;
    z-index: 50;
    margin-bottom: 4px;
}

/* View/Edit B-Pattern */
.view-mode .edit-field { display: none; }
.edit-mode .view-field { display: none; }
```

### Группа 2: Drawer — drawer.js + drawer.html

#### `app/static/js/drawer.js` (новый)

```javascript
function openDrawer(url, title) {
    var overlay = document.getElementById('drawer-overlay');
    var drawer = document.getElementById('drawer');
    var content = document.getElementById('drawer-content');
    
    // Заголовок + loader
    content.innerHTML = '<div class="p-6"><div class="text-lg font-medium text-ink mb-4">' + (title || '') + '</div><div class="text-muted text-sm">Загрузка...</div></div>';
    
    overlay.classList.remove('hidden');
    drawer.classList.add('open');
    
    // HTMX-загрузка контента
    fetch(url).then(function(resp) {
        return resp.text();
    }).then(function(html) {
        content.innerHTML = '<div class="p-6">' +
            '<div class="flex justify-between items-center mb-4">' +
            '<div class="text-lg font-medium text-ink">' + (title || '') + '</div>' +
            '<button onclick="closeDrawer()" class="text-muted hover:text-ink text-xl">&times;</button>' +
            '</div>' + html + '</div>';
    });
}

function closeDrawer() {
    document.getElementById('drawer-overlay').classList.add('hidden');
    document.getElementById('drawer').classList.remove('open');
}

// Закрытие по Esc
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeDrawer();
});
```

#### `app/templates/partials/drawer.html` (новый)

Каркас для переиспользования (если нужен серверный рендеринг drawer-контента):

```html
<!-- Использование: {% include "partials/drawer.html" with context %} -->
<!-- Заголовок drawer передаётся через переменную drawer_title -->
<!-- Контент — через блок drawer_body -->
```

### Группа 3: Шаблоны — глобальные замены (все 25 файлов)

**Единые правила замены для ВСЕХ шаблонов:**

| Найти | Заменить на | Примечание |
|---|---|---|
| `font-bold` | `font-medium` | Заголовки, метрики |
| `font-semibold` | `font-medium` | Подзаголовки |
| `bg-gray-100` | `bg-slate-50` | Canvas (body, login) или `bg-slate-50/50` (колонки канбана) |
| `rounded-lg` | `rounded-2xl` | Surfaces |
| `shadow` (без shadow-xl) | `border border-black/10` | Surfaces вместо тени |
| `bg-gray-900` | `bg-white border-r border-black/10` | Sidebar |
| `text-gray-900` | `text-ink` (или `text-[#030213]`) | Ink |
| `text-gray-700` | `text-ink` | Основной текст |
| `text-gray-600` | `text-muted` (или `text-[#717182]`) | Muted |
| `text-gray-500` | `text-muted` | Muted |
| `text-gray-400` | `text-muted` | Muted (приглушенный) |
| `bg-gray-50` | `bg-slate-50/50` | Фон строк/колонок |
| `hover:bg-gray-700` | `hover:bg-slate-100` | Sidebar hover |
| `border-gray-700` | `border-black/10` | Sidebar border |
| `bg-blue-600` | `bg-ink` (primary) или `bg-white border border-black/10` (secondary) | По контексту |
| `hover:bg-blue-700` | `hover:bg-ink/90` (primary) или `hover:bg-slate-50` (secondary) | |
| `text-blue-600` / `text-blue-500` | `text-blue-500` (R1 Info) или `text-ink hover:underline` (ссылки) | По контексту |

**ВАЖНО:** Кодер должен пройти КАЖДЫЙ из 25 шаблонов и применить замены. Не делать слепой find-replace — оценивать контекст (primary vs secondary button, info vs muted text).

### Группа 4: CTA-иерархия (D-06)

На каждой странице — ровно ОДНА primary-кнопка (`bg-ink text-white`).

| Страница | Primary | Secondary/Ghost |
|---|---|---|
| login.html | «Войти» | — |
| dashboard.html (manager) | «Все мои таски» | — |
| dashboard.html (admin) | — (нет действий) | — |
| kanban.html | — (нет действий) | Фильтры (secondary select) |
| lead_card.html | «Сохранить» (в edit mode) | «Редактировать», «Добавить» (secondary) |
| tasks.html | — | Фильтры (secondary links) |
| deals.html | — | Фильтры (secondary links) |
| upload_template.html | «Загрузить» | «Удалить» (ghost) |
| supervisor_dashboard.html | «Экспорт Excel» | «Воронка», «KPI» (secondary links) |
| managers_report.html | «Фильтр» | — |
| contacts_list (partial) | (в drawer) | «Добавить» (secondary, открывает drawer) |
| contact_log_list (partial) | (в drawer) | «Добавить» (secondary, открывает drawer) |
| comments_list (partial) | (в drawer) | «Добавить» (secondary, открывает drawer) |
| deals_list (partial) | (в drawer) | «Создать» (secondary, открывает drawer) |
| documents_list (partial) | «Сгенерировать» | — |
| lead_info_form (partial) | «Сохранить» | «Назначить» (secondary) |

### Группа 5: Drawer-паттерн для форм (D-09, D-10, D-11)

**Частичные шаблоны (partials):** формы создания переносятся в drawer.

**Пример для contacts_list.html:**

Было (inline форма):
```html
<form hx-post="/leads/{id}/contacts" ...>
    <input name="name" ...>
    <input name="phone" ...>
    <button>Добавить</button>
</form>
```

Стало (кнопка + drawer):
```html
<div class="flex justify-between items-center mb-4">
    <h2 class="text-lg font-medium text-ink">Контакты</h2>
    <button onclick="openDrawer('/leads/{id}/contacts/form', 'Новый контакт')"
            class="bg-white border border-black/10 px-3 py-1.5 rounded-lg text-sm text-ink hover:bg-slate-50">
        + Добавить
    </button>
</div>
<table class="w-full text-sm">
    <!-- rows -->
</table>
```

⚠ **Для drawer нужен дополнительный роут** — `GET /leads/{id}/contacts/form`, возвращающий HTML-форму для drawer. Аналогично для contact-log, comments, deals.

**Кодер должен добавить эти GET-роуты в `app/routes/leads.py`:**

```python
@router.get("/leads/{lead_id}/contacts/form", response_class=HTMLResponse)
async def contact_form(request, lead_id: int, session):
    from app.main import templates
    user = await get_current_user(request, session)
    return templates.TemplateResponse(request, "partials/contact_form.html",
        {"current_user": user, "lead_id": lead_id})

# Аналогично:
# GET /leads/{id}/contact-log/form
# GET /leads/{id}/comments/form
# GET /leads/{id}/deals/form
```

И создать 4 новых partial-шаблона: `contact_form.html`, `contact_log_form.html`, `comment_form.html`, `deal_form.html` — содержащие только форму (для загрузки в drawer).

**POST-роуты остаются без изменений** — после submit HTMX обновляет список и закрывает drawer:
```html
<form hx-post="/leads/{id}/contacts" hx-target="#contacts-list" hx-swap="beforeend"
      hx-on::after-request="closeDrawer()">
```

### Группа 6: View/Edit B-Pattern для lead_info_form (D-12)

**Сейчас:** форма всегда в edit mode (input-поля видны постоянно).

**Задача:** по умолчанию — View Mode (Label + Value без рамок). Кнопка «Редактировать» → Edit Mode.

```html
<div id="lead-info-container">
    <!-- View Mode (по умолчанию) -->
    <div class="view-mode space-y-3">
        <div>
            <div class="text-xs text-muted">ИНН</div>
            <div class="text-sm font-mono text-ink view-field">{{ lead.inn or '—' }}</div>
            <input class="edit-field ..." name="inn" value="{{ lead.inn or '' }}">
        </div>
        <!-- ... остальные поля ... -->
        <button onclick="toggleEditMode()" class="bg-white border border-black/10 px-4 py-2 rounded-lg text-sm">
            Редактировать
        </button>
    </div>
    
    <!-- Edit Mode -->
    <div class="edit-mode hidden">
        <form hx-post="/leads/{id}/edit" hx-target="#lead-info-container" ...>
            <!-- input-поля с border-black/10 -->
            <button type="submit" class="bg-ink text-white px-4 py-2 rounded-lg text-sm">Сохранить</button>
            <button onclick="toggleEditMode()" class="text-muted hover:text-ink text-sm">Отмена</button>
        </form>
    </div>
</div>

<script>
function toggleEditMode() {
    document.querySelector('.view-mode').classList.toggle('hidden');
    document.querySelector('.edit-mode').classList.toggle('hidden');
}
</script>
```

⚠ **Упрощение:** если View/Edit B-Pattern сложно реализовать для всех полей — можно сделать два отдельных partial-шаблона: `lead_info_view.html` (только чтение) и `lead_info_edit.html` (форма). Роут lead_edit возвращает view-шаблон после сохранения. Кнопка «Редактировать» загружает edit-шаблон через HTMX.

### Группа 7: Empty states (D-13)

Все списки при пустом состоянии:

```html
{% else %}
<div class="flex flex-col items-center justify-center py-12 text-center">
    <svg class="w-12 h-12 text-muted/30 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
    </svg>
    <div class="text-sm text-muted mb-3">Нет контактов</div>
    <button onclick="openDrawer('/leads/{id}/contacts/form', 'Новый контакт')"
            class="bg-white border border-black/10 px-3 py-1.5 rounded-lg text-sm text-ink hover:bg-slate-50">
        + Добавить
    </button>
</div>
{% endfor %}
```

### Группа 8: Контекстные подсказки (D-16)

Замена длинных описаний на tooltip-иконку:

```html
<!-- Было: -->
<h2 class="text-lg font-medium mb-4">Воронка продаж</h2>
<p class="text-sm text-muted mb-4">Распределение лидов по стадиям. Конверсия показывает процент перехода между соседними стадиями.</p>

<!-- Стало: -->
<h2 class="text-lg font-medium mb-4 flex items-center gap-1">
    Воронка продаж
    <span class="tooltip-trigger text-muted text-sm">
        ⓘ
        <span class="tooltip-content">Распределение лидов по стадиям. Конверсия — процент перехода между соседними стадиями.</span>
    </span>
</h2>
```

Минимум 3 места:
1. supervisor_dashboard — «Воронка продаж» (что показывают проценты)
2. supervisor_dashboard — «Просадки воронки» (что считается bottleneck)
3. lead_card — «Реквизиты и рапс» (зачем нужна верификация рапса)

### Группа 9: Risk Triage цвета (D-08)

| Элемент | Сейчас | Канон |
|---|---|---|
| Стадия lost (канбан, дашборд) | `text-red-400`/`text-red-600` | `text-red-600` (R4) |
| Просроченный таск | `text-red-600` / `border-red-500` | `text-amber-600` (R3) — не критический, требует внимания |
| Сырой лид (стадия 0) | `text-gray-600` | `text-blue-500` (R1 Info) |
| Оплачено (стадия 7) | `text-green-600` | `text-emerald-500` (Success) |
| Конверсия <25% | `text-red-600` | `text-red-600` (R4) |
| Конверсия <50% | `text-amber-600` | `text-amber-600` (R3) |
| Конверсия ≥50% | `text-emerald-600` | `text-emerald-500` (Success) |
| Воронка-бары | `bg-gray-400`, `bg-blue-400`, `bg-green-400` | `bg-slate-300`, `bg-blue-500`, `bg-emerald-500` |

## Anti-conflict (важно для кодера)

**НЕ ТРОГАТЬ:**
- `app/models.py`, `app/auth.py`, `app/database.py`, `app/config.py`
- `app/routes/*.py` — кроме добавления GET-роутов для drawer-форм (D-11)
- `app/services/*.py`
- `Екатерина.xlsx`, `_Вероника.xlsx`, `.planning/`
- Python-логика: никакие изменения функциональности, только UI

**Исключение — leads.py:** добавляются 4 GET-роута для drawer-форм (`/leads/{id}/contacts/form`, `/leads/{id}/contact-log/form`, `/leads/{id}/comments/form`, `/leads/{id}/deals/form`). Эти роуты только рендерят form-partials, без бизнес-логики.

**Создаваемые файлы:**
- `app/static/js/drawer.js`
- `app/templates/partials/drawer.html`
- `app/templates/partials/contact_form.html`
- `app/templates/partials/contact_log_form.html`
- `app/templates/partials/comment_form.html`
- `app/templates/partials/deal_form.html`
- `app/templates/partials/lead_info_view.html` (если выбран двухшаблонный View/Edit)

## Готово, когда (success criteria)

- [ ] D-01..D-18 — все выполнены
- [ ] `grep -rn 'font-bold\|font-semibold' app/templates/` → 0 результатов
- [ ] `grep -rn 'bg-gray-100' app/templates/` → 0 результатов
- [ ] `grep -rn 'rounded-lg' app/templates/` → 0 результатов (всё `rounded-2xl`)
- [ ] `grep -rn 'bg-gray-900' app/templates/` → 0 результатов
- [ ] Geist Sans/Mono подключены, шрифт применяется на всех страницах
- [ ] Canvas: `bg-slate-50` (не `bg-gray-100`)
- [ ] Sidebar: `bg-white border-r border-black/10` (не `bg-gray-900`)
- [ ] Surfaces: `bg-white border border-black/10 rounded-2xl` (не `rounded-lg shadow`)
- [ ] Primary кнопка: `bg-ink text-white` (не `bg-blue-600`), одна на страницу
- [ ] ИНН/телефоны/суммы: `font-mono`
- [ ] Drawer работает: клик «Добавить» → открывается боковая панель, форма сабмитится через HTMX, drawer закрывается
- [ ] View/Edit B-Pattern: карточка лида — по умолчанию просмотр, «Редактировать» → режим редактирования
- [ ] Empty states: иконка + текст + кнопка «Добавить»
- [ ] Контекстные подсказки: минимум 3 tooltip-иконки
- [ ] Risk Triage: lost→red-600, просрочка→amber-600, сырой лид→blue-500, оплачено→emerald-500
- [ ] Сервер запускается, все страницы рендерятся без ошибок
- [ ] Функциональность не сломана: канбан drag-and-drop, HTMX-формы, генерация документов — всё работает

## Не готово, когда

- Любой `font-bold` или `font-semibold` остался в шаблонах
- Любой `bg-gray-100` или `bg-gray-900` остался
- Geist не подключён или не применяется (проверить через DevTools)
- Drawer не открывается или не закрывается
- View/Edit B-Pattern ломает редактирование лида
- HTMX-формы перестают работать после переноса в drawer
- Канбан drag-and-drop сломался после restyling
- Более одной primary-кнопки на странице
- ИНН/телефоны не в font-mono
- Empty states отсутствуют (просто «Нет данных»)

## Что даёт эта фаза

CRM RAI получает каноничный визуальный стандарт:
- ✅ **Geist Sans/Mono** — профессиональная типографика
- ✅ **Institutional Light** — чистый светлый интерфейс
- ✅ **View/Edit B-Pattern** — разделение режимов просмотра и редактирования
- ✅ **Drawer** — формы в боковой панели, контекст не теряется
- ✅ **CTA-иерархия** — одна primary-кнопка, чёткая иерархия действий
- ✅ **Risk Triage** — семантические цвета статусов
- ✅ **Контекстные подсказки** — вместо длинных плашек
- ✅ **Empty states** — с иконкой и кнопкой
- ✅ **Долг D-H закрыт** — empty state для документов без шаблонов

## Следующий шаг

CRM RAI функционально и визуально завершён. Дальнейшие шаги — по запросу:
- Управление пользователями (создание менеджеров, смена паролей)
- Импорт новых xlsx через UI (не через скрипт)
- Уведомления (email/in-app)
- AI-функции (AI Dock по канону)
