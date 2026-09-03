---
phase: 14-task-assignee-lead-owner
plan: "01"
slice: 14-01
type: execute
wave: 1
depends_on:
  - phase-7
requirements:
  - CRM-14-01
autonomous: true
files_modified:
  - app/routes/leads.py
  - app/routes/tasks.py
files_created: []
must_haves:
  truths:
    - "T-01: В app/routes/leads.py В ТРЁХ местах создания задачи `Task(...)` поле `assigned_to=user.id` ЗАМЕНЕНО на `assigned_to=(lead.assigned_manager_id or user.id)`. Три точки: (1) `add_contact_log` leads.py:702 — авто-задача «Перезвонить»; (2) `add_action` leads.py:903 — задача из журнала действий; (3) `create_task` leads.py:1104 — основная форма POST /leads/{lead_id}/tasks. Во всех трёх переменная `lead` уже загружена выше по функции (leads.py:677, 853, 1091 соответственно) — `lead.assigned_manager_id` доступен в области видимости. `created_by=user.id` ОСТАЁТСЯ — кто создал, остаётся корректным"
    - "T-02: Фолбэк `or user.id` обязателен — `Lead.assigned_manager_id` nullable (`models.py:52`, `Mapped[Optional[int]]`), а `Task.assigned_to` NOT NULL (`models.py:179`). Если у лида нет владельца — задача назначается на создателя (supervisor/admin), как и раньше. Без фолбэка — IntegrityError на NOT NULL при `assigned_manager_id=None`"
    - "T-03: После правки ВЫПОЛНЯЕТСЯ инвариант проекта `Task.assigned_to == Lead.assigned_manager_id` (когда у лида есть владелец). Этот инвариант уже зафиксирован в миграции `scripts/migrate_todo_to_tasks.py:189` (`assigned_to=lead.assigned_manager_id`) и подразумевается во всём коде фильтров (см. T-06). Восстановление инварианта — цель фазы, не побочный эффект"
    - "T-04: Существующая модель правок задачи (`task.assigned_to != user.id` → 403 для manager в tasks.py:233 `task_edit_form` и tasks.py:269 `update_task`, и в шаблоне task_card.html:35) НЕ ТРОГАЕТСЯ. Логика корректна: после T-01 `task.assigned_to` = реальный исполнитель = менеджер-владелец лида, поэтому менеджер автоматически получает права на редактирование своих задач (даже если создал supervisor). Никаких правок в гейтах edit/delete НЕ делать"
    - "T-05: В app/routes/tasks.py ВЕТКА `no_tasks` хелпера `_query_leads_with_tasks` (tasks.py:87-98) ИСПРАВЛЕНА — `task_filter` теперь применяется ВНУТРИ `exists(...)`. Было: `has_tasks = exists(select(Task.id).where(Task.lead_id == Lead.id))`. Стало: `has_tasks = exists(select(Task.id).where(Task.lead_id == Lead.id, task_filter))`. Без этой правки лид с чужой задачей (например, поставленной supervisor'ом до миграции данных, или после правки T-01 если у лида сменился владелец) никогда не покажется «без задач» в рамках scope. `task_filter` уже возвращается из `_user_scope_filters` (tasks.py:22-32), нужно просто прокинуть в exists"
    - "T-06: В app/routes/tasks.py функция `_task_counts` (tasks.py:35-75) — счётчик `leads_without_tasks` (строки 61-68) ИСПРАВЛЕН аналогично T-05: `has_tasks` принимает `task_filter` в `.where()`. Было: `exists(select(Task.id).where(Task.lead_id == Lead.id))`. Стало: `exists(select(Task.id).where(Task.lead_id == Lead.id, task_filter))`. Без этого счётчик в сайдбаре у supervisor/admin показывает «лиды без задач ВООБЩЕ» (по всей БД), а не «в рамках scope» — рассинхрон с отображаемым списком при выборе менеджера. `_user_scope_filters(user)` (tasks.py:37) вызывается БЕЗ manager_id, поэтому scope = вся БД для supervisor/admin — что нормально для счётчика в сайдбаре"
    - "T-07: UI создания задачи `app/templates/partials/task_form.html` НЕ ТРОГАЕТСЯ. Решение пользователя (AskUserQuestion) — вариант «всегда владелец лида», без UI выбора исполнителя. `assigned_to` определяется сервером по лиду. Это минимальная правка, согласуется с migrate_todo_to_tasks.py и не требует валидации/UX-изменений"
    - "T-08: Данные, уже созданные с багом (`Task.assigned_to == supervisor.id` в чужих лидах), ТРЕБУЮТ миграции-исправления. В рамках фазы добавляется скрипт `scripts/migrate_fix_task_assignee.py` (новый файл) — одноразовый: для каждой задачи с `lead_id IS NOT NULL` обновляет `Task.assigned_to = (SELECT assigned_manager_id FROM leads WHERE id = Task.lead_id)` ТОЛЬКО если у лида есть assigned_manager_id. Если у лида нет владельца — `assigned_to` НЕ МЕНЯЕТСЯ (остаётся на создателе, валидное состояние). Скрипт идемпотентный (повторный запуск безопасен). Запускается ОДИН раз вручную после деплоя кода; в коммите фиксируется результат (сколько строк обновлено)"
    - "T-09: Фильтры `_user_scope_filters` (tasks.py:22-32) НЕ ТРОГАЮТСЯ — они корректны. Для manager: `Task.assigned_to == user.id` И `Lead.assigned_manager_id == user.id` (пара одинаковых X). Для supervisor/admin с manager_id: `== manager_id`. Для supervisor/admin без manager_id: `(True, True)` = вся БД. После правки T-01 эти фильтры начинают работать как задумано — потому что данные становятся согласованы с инвариантом"
    - "T-10: Тикер руководителя (`app/routes/ticker.py:79-98`) и тикер менеджера (`ticker.py:46`) НЕ ТРОГАЮТСЯ — оба построены на `Task.assigned_to` и после правки данных автоматически показывают корректную картину: тикер руководителя показывает «задачи всех менеджеров» (JOIN к User по assigned_to), тикер менеджера — свои задачи. Никаких правок"
    - "T-11: Дашборд менеджера (`app/routes/dashboard.py:37`) НЕ ТРОГАЕТСЯ — фильтр `Task.assigned_to == user.id` корректен после правки данных. Страница `/tasks` (tasks.py:144, `filters = [Task.assigned_to == user.id]` для всех ролей) НЕ ТРОГАЕТСЯ — это отдельная старая страница вне симптома, ее поведение (supervisor видит только свои задачи) сохраняется как есть"
  artifacts:
    - path: app/routes/leads.py (модификация)
      provides: "T-01: 3 правки assigned_to=user.id → assigned_to=(lead.assigned_manager_id or user.id) в add_contact_log:702, add_action:903, create_task:1104. created_by=user.id сохранён"
    - path: app/routes/tasks.py (модификация)
      provides: "T-05: task_filter прокинут в exists() ветки no_tasks (tasks.py:88). T-06: task_filter прокинут в exists() счётчика leads_without_tasks (tasks.py:61)"
    - path: scripts/migrate_fix_task_assignee.py (новый)
      provides: "T-08: одноразовый скрипт миграции исторических данных — обновляет Task.assigned_to = lead.assigned_manager_id где лид имеет владельца; идемпотентный"
  key_links:
    - from: app/routes/leads.py (create_task / add_action / add_contact_log)
      to: app/models.py (Task.assigned_to + Lead.assigned_manager_id)
      via: "Task(assigned_to=lead.assigned_manager_id or user.id) — данные на запись"
      pattern: "Восстановление инварианта Task.assigned_to == Lead.assigned_manager_id (как в migrate_todo_to_tasks.py:189)"
    - from: app/routes/tasks.py (_user_scope_filters)
      to: app/routes/leads.py (создание задач)
      via: "task_filter = Task.assigned_to == X. После T-01 X (создатель) и lead.assigned_manager_id совпадают — фильтр начинает работать корректно без правок в нём самом"
      pattern: "Фильтры корректны архитектурно, проблема была в данных, не в логике фильтрации"
    - from: app/routes/tasks.py (_query_leads_with_tasks ветка no_tasks)
      to: app/models.py (Task, Lead)
      via: "exists(select(Task.id).where(Task.lead_id == Lead.id, task_filter)) — scope-aware проверка «нет задач»"
      pattern: "Раньше: «нет задач ВООБЩЕ». Стало: «нет задач в рамках scope». Согласовано с _user_scope_filters"
    - from: scripts/migrate_fix_task_assignee.py
      to: storage/crm.db (tasks + leads)
      via: "UPDATE tasks SET assigned_to = (SELECT assigned_manager_id FROM leads WHERE id = tasks.lead_id) WHERE EXISTS (...)"
      pattern: "Одноразовое исправление исторических данных, оставшихся от бага. Идемпотентное, безопасное"
---

# Plan 14-01 — Исполнитель задачи = владелец лида (фикс бага «задачи на руководителе»)

**Phase:** 14 — task-assignee-lead-owner
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

**Симптом (от пользователя):** в разделе «Задачи» supervisor создаёт задачи в лидах менеджеров, но система считает их задачами supervisor'а, а не менеджера. При фильтре по менеджеру в «Лиды без задач» — у него задач нет; при фильтре по supervisor'у — задачи висят на нём. Нужно: задачи привязываются к лиду, а владелец лида (менеджер) и есть исполнитель задачи.

**Root cause (подтверждено чтением кода):**

В `app/routes/leads.py` при создании `Task(...)` **в трёх местах жёстко подставляется `assigned_to=user.id`** — то есть ID того, кто создаёт задачу (supervisor/admin), а не владельца лида:

| Функция | Строка | Контекст |
|---|---|---|
| `add_contact_log` | `leads.py:702` | авто-задача «Перезвонить: {lead.name}» при заполнении журнала контактов |
| `add_action` | `leads.py:903` | задача из журнала действий (если заполнен `task_title`) |
| `create_task` | `leads.py:1104` | основная форма создания задачи (POST `/leads/{lead_id}/tasks`) |

Во всех трёх `lead` уже загружен выше (строки 677, 853, 1091) — `lead.assigned_manager_id` доступен.

**Почему это корень бага, а не фильтры:** весь проект построен на инварианте `Task.assigned_to == Lead.assigned_manager_id`:
- `scripts/migrate_todo_to_tasks.py:189` при первичной миграции пишет `assigned_to=lead.assigned_manager_id` — то есть авторы миграции явно зафиксировали инвариант.
- `_user_scope_filters` (`tasks.py:22-32`) возвращает **пару одинаковых фильтров** `Task.assigned_to == X` и `Lead.assigned_manager_id == X` — структура подразумевает, что X один и тот же.
- Тикер руководителя (`ticker.py:79-98`), тикер менеджера (`ticker.py:46`), дашборд (`dashboard.py:37`), гейты edit/delete (`tasks.py:233, 269`, `task_card.html:35`) — все построены на `Task.assigned_to` и НЕ нуждаются в правках, если данные согласованы.

То есть **фильтры корректны архитектурно, проблема в данных**. Лечится именно точкой создания.

**Решение пользователя (AskUserQuestion):** всегда владелец лида (`lead.assigned_manager_id`), без UI выбора исполнителя. Минимальная правка, согласуется с инвариантом проекта.

## Архитектура (обязательно к соблюдению)

**Восстановление инварианта `Task.assigned_to == Lead.assigned_manager_id` в точке создания + починка scope-aware проверки «нет задач» + одноразовая миграция исторических данных.** Принципы:

1. **Правка в одной точке — данные в нескольких.** Замена `assigned_to=user.id` → `assigned_to=(lead.assigned_manager_id or user.id)` в 3 местах `leads.py`. Всё остальное (фильтры, тикеры, дашборд, гейты) автоматически начинает работать корректно — потому что данные становятся согласованы с инвариантом.

2. **Фолбэк `or user.id` обязателен.** `Lead.assigned_manager_id` nullable, `Task.assigned_to` NOT NULL. Лид без владельца → задача на создателя. Это валидное состояние (например, новый лид, которому ещё не назначили менеджера, но supervisor уже ставит задачу).

3. **`created_by=user.id` НЕ МЕНЯЕТСЯ.** Поле «кто создал» хранит supervisor.id — это правильно, audit-trail создания сохраняется. Меняется только «кому назначена» (исполнитель).

4. **Правка фильтров scope-aware.** Даже после восстановления инварианта, ветка `no_tasks` и счётчик `leads_without_tasks` проверяют «нет задач ВООБЩЕ», а не «нет задач в scope». Для supervisor/admin это означало бы рассинхрон: лид с задачой другого менеджера (после миграции T-08 — исторической, или если у лида сменился владелец) никогда не покажется «без задач». Решение: прокинуть `task_filter` в `exists(...)` — теперь «нет задач» = «нет задач в рамках scope (менеджера/роли)».

5. **Миграция исторических данных обязательна.** В БД уже есть задачи, созданные supervisor'ом в чужих лидах с `assigned_to=supervisor.id`. Без миграции код-фикс сработает только на новые задачи, а симптом у пользователя останется для старых. Скрипт `scripts/migrate_fix_task_assignee.py` обновляет исторические данные один раз.

6. **UI не трогаем.** Решение пользователя — без UI выбора исполнителя. Форма `task_form.html` остаётся как есть, `assigned_to` определяется сервером.

## Файлы

### 1. `app/routes/leads.py` (модификация)

**(a) `add_contact_log` (~стр. 700-708)** — авто-задача «Перезвонить»:
```python
    if next_date:
        task = Task(
            lead_id=lead_id,
            assigned_to=lead.assigned_manager_id or user.id,   # ← БЫЛО user.id
            created_by=user.id,
            title=f"Перезвонить: {lead.name}",
            due_date=datetime.combine(next_date, datetime.min.time()),
            priority=1,
            status="pending",
        )
        session.add(task)
```

**(b) `add_action` (~стр. 901-909)** — задача из журнала действий:
```python
        new_task = Task(
            lead_id=lead_id,
            assigned_to=lead.assigned_manager_id or user.id,   # ← БЫЛО user.id
            created_by=user.id,
            title=task_name,
            due_date=due_dt,
            priority=task_priority if task_priority in (1, 2, 3) else 2,
            status="pending",
        )
        session.add(new_task)
        await session.flush()
```

**(c) `create_task` (~стр. 1102-1111)** — основная форма:
```python
    task = Task(
        lead_id=lead_id,
        assigned_to=lead.assigned_manager_id or user.id,   # ← БЫЛО user.id
        created_by=user.id,
        title=title,
        description=description or None,
        due_date=due_dt,
        priority=priority,
        status="pending",
    )
    session.add(task)
```

> **Проверка перед коммитом:** во всех трёх функциях `lead` загружен выше (677/853/1091) и доступен в области видимости `Task(...)`. Если кодер видит, что в каком-то из 3 мест `lead` вдруг не загружен — НЕ использовать `user.id` как фолбэк, а ДОБАВИТЬ загрузку лида (как в create_task:1090-1093). Но по текущему коду это НЕ нужно — везде уже есть.

### 2. `app/routes/tasks.py` (модификация)

**(a) Ветка `no_tasks` хелпера `_query_leads_with_tasks` (~стр. 87-98)** — scope-aware проверка «нет задач»:
```python
    if filter == "no_tasks":
        has_tasks = exists(
            select(Task.id).where(Task.lead_id == Lead.id, task_filter)   # ← +task_filter
        )
        conds = [lead_filter, Lead.stage != "lost", ~has_tasks]
        if stage:
            conds.append(Lead.stage == stage)
        result = await session.execute(
            select(Lead)
            .where(*conds)
            .options(selectinload(Lead.assigned_manager))
            .order_by(Lead.name)
        )
        return result.scalars().all()
```

**(b) Счётчик `leads_without_tasks` в `_task_counts` (~стр. 61-68)** — аналогично:
```python
    has_tasks = exists(
        select(Task.id).where(Task.lead_id == Lead.id, task_filter)   # ← +task_filter
    )
    leads_without = await session.scalar(
        select(func.count(Lead.id)).where(
            lead_filter,
            Lead.stage != "lost",
            ~has_tasks,
        )
    )
```

> **Почему `task_filter` тут корректен:** `_user_scope_filters` (tasks.py:22-32) возвращает пару `(task_filter, lead_filter)`. В `_query_leads_with_tasks` они получены на строке 81; в `_task_counts` — на строке 37 (БЕЗ manager_id, т.к. счётчик сайдбара общий для supervisor/admin). `task_filter` для supervisor/admin без manager_id = `True` (bare Python True), SQLAlchemy трактует как всегда-истинное — фильтр не сужает, проверка остаётся «нет задач ВООБЩЕ». Для manager = `Task.assigned_to == user.id` — проверка становится «нет МОИХ задач». Это правильная семантика для каждой роли.

### 3. `scripts/migrate_fix_task_assignee.py` (новый файл)

Одноразовая миграция исторических данных:
```python
"""Одноразовая миграция: восстановить инвариант Task.assigned_to == Lead.assigned_manager_id.

Запуск: python scripts/migrate_fix_task_assignee.py
Безопасен для повторного запуска (идемпотентный).

Контекст: до фикса задачи, созданные supervisor/admin в чужих лидах,
получали assigned_to=creator_id вместо assigned_to=lead.assigned_manager_id.
Этот скрипт исправляет исторические данные.
"""
import asyncio
import sys
from pathlib import Path

# Подключить корень проекта для импорта app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import update, select
from app.database import engine
from app.models import Task, Lead
from sqlalchemy.ext.asyncio import AsyncSession


async def main():
    async with AsyncSession(engine) as session:
        # Найти задачи, у которых assigned_to НЕ совпадает с владельцем лида
        stmt = (
            select(Task.id, Task.assigned_to, Lead.assigned_manager_id, Lead.id)
            .join(Lead, Task.lead_id == Lead.id)
            .where(Task.assigned_to != Lead.assigned_manager_id)
            .where(Lead.assigned_manager_id.is_not(None))
        )
        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            print("✓ Нет задач для миграции. БД уже согласована.")
            return

        print(f"Найдено задач с рассинхроном: {len(rows)}")
        for tid, cur, new, lid in rows:
            print(f"  task #{tid}: assigned_to {cur} → {new} (lead_id={lid})")

        # Массовое обновление: task.assigned_to = lead.assigned_manager_id
        upd = (
            update(Task)
            .where(Task.lead_id == Lead.id)
            .where(Task.assigned_to != Lead.assigned_manager_id)
            .where(Lead.assigned_manager_id.is_not(None))
            .values(assigned_to=Lead.assigned_manager_id)
        )
        # SQLAlchemy async: эмулируем join в UPDATE через подзаконный select
        # Более портабельный вариант — построчно:
        for tid, cur, new, lid in rows:
            await session.execute(
                update(Task).where(Task.id == tid).values(assigned_to=new)
            )
        await session.commit()
        print(f"✓ Обновлено строк: {len(rows)}")


if __name__ == "__main__":
    asyncio.run(main())
```
> ⚠️ Кодер: реализация через построчный UPDATE (а не один bulk с JOIN) — потому что SQLite + aiosqlite капризно относится к `UPDATE ... FROM` синтаксису. Построчный надёжнее и для ~сотен строк выполняется мгновенно. Перед коммитом скрипт запустить ОДИН раз на актуальной БД, результат (сколько строк обновлено) зафиксировать в README-CONTRACT.
> ⚠️ **Бэкап БД перед запуском обязателен.** Скрипт пишет в `storage/crm.db` напрямую через `AsyncSession`. Сделать копию (например `storage/crm.db.before-phase-14`) перед прогоном.

## Шаги выполнения

1. **Бэкап БД:** `cp storage/crm.db storage/crm.db.before-phase-14` (или как принято в проекте — проверить `.gitignore`, бэкапы БД обычно исключены, см. коммит `2aa2f47`).
2. `app/routes/leads.py` — три правки `assigned_to=user.id` → `assigned_to=(lead.assigned_manager_id or user.id)` (T-01).
3. `app/routes/tasks.py` — прокинуть `task_filter` в `exists(...)` в двух местах: ветка `no_tasks` (T-05) и счётчик `leads_without_tasks` (T-06).
4. `scripts/migrate_fix_task_assignee.py` — создать скрипт, запустить один раз, зафиксировать результат.
5. Ручная проверка сценариев (см. Acceptance) — критично: создание задачи supervisor'ом в чужом лиде, фильтр по менеджеру, счётчик сайдбара, права редактирования.

## Acceptance criteria (gate)

- [ ] **Главный сценарий:** supervisor логинится → открывает чужой лид (где `assigned_manager_id` = менеджер M) → создаёт задачу → задача сохраняется с `Task.assigned_to = M.id` (проверить в БД после создания, а не в UI).
- [ ] В разделе «Задачи → Лиды без задач» фильтр по менеджеру M → лид с задачей от supervisor'а НЕ в списке «без задач» (у него задача есть). Раньше лид был бы «без задач» с точки зрения менеджера M, т.к. задача числилась на supervisor'е.
- [ ] В разделе «Задачи → Лиды» (total/today/overdue) фильтр по менеджеру M → задача, созданная supervisor'ом, ВИДНА под менеджером M.
- [ ] Фильтр по supervisor'у → задача НЕ висит на нём (теперь она на менеджере M). Раньше висела.
- [ ] Менеджер M видит эту задачу в своём тикере (`/ticker`) и дашборде (`/dashboard`) — без правки ticker.py/dashboard.py.
- [ ] Менеджер M может редактировать эту задачу (кнопка «Редактировать» в task_card.html появляется, нет 403) — гейт `task.assigned_to != user.id` (tasks.py:233) теперь пропускает.
- [ ] **Счётчик сайдбара `leads_without_tasks`** для supervisor/admin согласован со списком: если supervisor выбрал manager_id=M в `/tasks/leads`, счётчик в сайдбаре остаётся общим (по всей БД) — это acceptable, т.к. счётчик не знает про выбор на странице (T-06 правит только «нет задач в scope роли», а не «нет задач в выбранном менеджере»). Документировать как known-limitation в README-CONTRACT.
- [ ] **Лид без владельца** (`assigned_manager_id=None`): supervisor создаёт задачу → `assigned_to=user.id` (фолбэк сработал), IntegrityError нет, задача валидная.
- [ ] **Создание задачи менеджером в своём лиде:** менеджер M создаёт задачу в своём лиде (`assigned_manager_id=M.id`) → `assigned_to=M.id`. Поведение не изменилось — менеджер создавал и создаёт на себя.
- [ ] **Auto-задача «Перезвонить»** (add_contact_log): supervisor заполняет журнал контактов чужого лида с next_action_date → создаётся задача с `assigned_to=lead.assigned_manager_id`.
- [ ] **Задача из журнала действий** (add_action): supervisor пишет журнал действий с task_title → создаётся задача с `assigned_to=lead.assigned_manager_id`.
- [ ] **Миграция исторических данных:** после прогона `scripts/migrate_fix_task_assignee.py` — `SELECT COUNT(*) FROM tasks t JOIN leads l ON t.lead_id=l.id WHERE t.assigned_to != l.assigned_manager_id AND l.assigned_manager_id IS NOT NULL` возвращает 0. Скрипт идемпотентный (повторный запуск пишет «нет задач для миграции»).
- [ ] **Регрессия тикера:** `/ticker` у supervisor'а показывает задачи менеджеров (через JOIN User по assigned_to), а не свои. У менеджера — свои задачи.
- [ ] **Регрессия правок задач:** после миграции менеджеры могут редактировать задачи, созданные supervisor'ом (раньше 403, т.к. assigned_to=supervisor.id ≠ manager.id).

## Не делаем (YAGNI)

- **НЕ добавляем UI выбора исполнителя в `task_form.html`** — решение пользователя «всегда владелец лида». Если позже понадобится гибкость «назначить на себя или на менеджера» — отдельная фаза с `<select name="assigned_to">` + серверная валидация.
- **НЕ трогаем `_user_scope_filters`** (tasks.py:22-32) — корректна. Проблема была в данных, не в логике фильтрации.
- **НЕ трогаем тикер** (`ticker.py:46, 79-98`) и **дашборд** (`dashboard.py:37`) — построены на `Task.assigned_to`, после миграции данных работают корректно.
- **НЕ трогаем гейты edit/delete задач** (`tasks.py:233, 269`, `task_card.html:35`) — `task.assigned_to != user.id` корректен, после миграции менеджеры получают права автоматически.
- **НЕ трогаем страницу `/tasks`** (tasks.py:144, `filters = [Task.assigned_to == user.id]` для всех ролей) — отдельная старая страница, не связана с симптомом. Supervisor видит «свои» (созданные им) задачи — это валидное поведение для той страницы, не баг.
- **НЕ правим счётчик сайдбара под выбранный в `/tasks/leads` менеджер** — счётчик живёт в сайдбаре и не знает про выбор на странице. Передача `manager_id` через JS в `/api/tasks/sidebar` — отдельная UX-фаза, не часть этого фикса. Документировать как known-limitation.
- **НЕ делаем soft-migration** (миграция «на лету» при чтении задачи) — одноразовый скрипт проще и чище, не оставляет长期 компенсирующей логики в коде.
- **НЕ переносим `assigned_to` в `Lead.assigned_manager_id` (денормализация наоборот)** — `Task.assigned_to` нужна как самостоятельное поле (NOT NULL, FK), потому что у задачи может не быть лида (`lead_id` nullable — `models.py:178`), а `assigned_to` обязателен. Архитектура корректна.
- **НЕ добавляем миграцию с помощью Alembic** — в проекте нет Alembic (модели создаются через `Base.metadata.create_all`, миграции — скриптами в `scripts/`). Скрипт `migrate_fix_task_assignee.py` следует существующему паттерну (`scripts/migrate_todo_to_tasks.py`).
