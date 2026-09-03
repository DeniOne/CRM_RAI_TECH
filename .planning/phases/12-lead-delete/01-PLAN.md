---
phase: 12-lead-delete
plan: "01"
slice: 12-01
type: execute
wave: 1
depends_on:
  - phase-2
requirements:
  - CRM-12-01
autonomous: true
files_modified:
  - app/routes/leads.py
  - app/templates/lead_card.html
files_created: []
must_haves:
  truths:
    - "T-01: В app/routes/leads.py добавлен НОВЫЙ роут `delete_lead` с декоратором `@router.delete(\"/leads/{lead_id}\")`. Сигнатура: `async def delete_lead(request: Request, lead_id: int, session: AsyncSession = Depends(get_session))`. Роут получает current_user через `get_current_user(request, session)` (как lead_card в leads.py:339) и ДО любого действия проверяет роль: `if user.role.value not in (\"admin\", \"supervisor\"): raise HTTPException(status_code=403, detail=\"Недостаточно прав\")`. Используется тот же паттерн role-gate, что в leads.py:278 (`if user.role.value not in (\"supervisor\", \"admin\")`) и tasks.py:304. Обычный менеджер получает 403 — серверная защита обязательна, даже если в UI кнопки нет"
    - "T-02: Если лид не найден — `raise HTTPException(status_code=404, detail=\"Лид не найден\")` (после select по id, до удаления). Паттерн идентичен delete_contact (leads.py:648-652)"
    - "T-03: Перед `session.delete(lead)` ЯВНО удаляются зависимые записи, которые НЕ покрываются ORM-cascade `Lead.contacts/contact_logs/comments/tasks/deals/documents` (models.py:98-103). А именно — две таблицы БЕЗ relationship/cascade к Lead: (а) `StageHistory` (models.py:106-115, FK lead_id БЕЗ cascade) и (б) `AgentMessage` (models.py:248, context_lead_id БЕЗ cascade). Код: `await session.execute(delete(StageHistory).where(StageHistory.lead_id == lead_id))` и `await session.execute(delete(AgentMessage).where(AgentMessage.context_lead_id == lead_id))`. `delete` импортировать из `sqlalchemy`. Без этого шага в БД остаются orphan-записи со ссылкой на несуществующий lead_id (SQLite FK выключены, PRAGMA foreign_keys=ON нигде не ставится — cascade срабатывает только через ORM relationship для 6 таблиц, но НЕ для StageHistory/AgentMessage)"
    - "T-04: Перед удалением лид из БД — ЯВНО удаляются физические файлы документов с диска. Папка `storage/documents/{lead_id}/` (.docx и .pdf, создаются в documents.py:203-207) удаляется через `shutil.rmtree(dir_path, ignore_errors=True)` (ignore_errors=True — чтобы не падать, если папка не существует или уже удалена). Путь формируется через `pathlib.Path(\"storage/documents\") / str(lead_id)`. Перед rmtree проверить `dir_path.exists()`. Импортировать `shutil` и `pathlib.Path` вверху leads.py. БЕЗ этого шага — orphan-files риск: БД-строки Document уйдут по ORM-cascade (models.py:103), а .docx/.pdf останутся навсегда (в проекте нигде нет os.remove/Path.unlink/shutil.rmtree — это первая точка удаления файлов)"
    - "T-05: Само удаление лида — через `await session.delete(lead)` (с уже загруженным объектом lead), затем `await session.commit()`. Это активирует ORM-cascade для 6 таблиц: Contact, ContactLog, Comment, Task, Deal, Document (models.py:98-103). НИ В КОЕМ СЛУЧАЕ не использовать raw SQL `DELETE FROM leads WHERE id=...` — он НЕ включит FK cascade (SQLite PRAGMA foreign_keys=OFF) и оставит все 8 зависимых таблиц как orphan"
    - "T-06: После успешного удаления — ответ `JSONResponse(status_code=200, content={\"ok\": True})` (формат `{ok, ...}` как в api_rename_lead leads.py:399-424 и api_change_stage leads.py:382). Редирект на /kanban делает ФРОНТ (см. T-08), а НЕ сервер — потому что серверный RedirectResponse при fetch вернёт 200 с непарсимым телом, и фронт сломается. JSONResponse импортировать из `fastapi.responses` (проверить, что уже есть)"
    - "T-07: При ошибке БД/исключении во время удаления — откат транзакции `await session.rollback()` и возврат `JSONResponse(status_code=500, content={\"ok\": False, \"detail\": \"Ошибка удаления\"})`. Обернуть блок удаления в try/except (Exception). Это защищает от полусостояния: либо лид удалён полностью (файлы + все таблицы), либо ничего не удалено и user видит ошибку. Порядок операций внутри try: сначала удалить StageHistory/AgentMessage (БД), потом файлы (rmtree), потом session.delete(lead)+commit. Если rmtree бросит исключение — rollback вернёт удалённые StageHistory/AgentMessage, лид останется жив, user увидит ошибку и сможет повторить"
    - "T-08: В app/templates/lead_card.html в шапке карточки (~стр. 46-52, рядом с кнопкой «Отправить в чат») добавлена новая кнопка «Удалить лид», обёрнутая в role-gate: `{% if current_user.role.value in ('supervisor', 'admin') %}...{% endif %}`. Паттерн role-gate — как в partials/task_card.html:44. Кнопка красная/деструктивная: `class=\"... text-red-600 hover:text-red-800 hover:bg-red-50 ...\"` с иконкой-мусоркой (svg `M19 7l-.867 12.142...` — точно такой же как в contact_row.html:25-29). Атрибуты: `type=\"button\"` и `onclick=\"deleteLead()\"`. Кнопка НЕ htmx (нет hx-delete), потому что после удаления нужен JS-редирект, а не DOM-swap (карточка-источник исчезает)"
    - "T-09: В блок `<script>` lead_card.html (~стр. 84-183) добавлена функция `deleteLead()`. Реализация по образцу `applyDadata` (lead_info_form.html:287-321, использует нативный confirm + fetch): (1) `if (!confirm('Удалить лида «' + LEAD_NAME + '\' без возможности восстановления? Все контакты, журнал, комментарии, задачи, сделки и документы будут удалены.')) return;` — LEAD_NAME объявить рядом с LEAD_ID (lead_card.html:97) как `var LEAD_NAME = {{ lead.name | tojson }};` (tojson — безопасное экранирование кавычек в названии); (2) `fetch('/leads/' + LEAD_ID, { method: 'DELETE' })`; (3) `.then(r => r.json())`; (4) при `data.ok === true` — `window.location.href = '/kanban'`; (5) иначе — `alert('Ошибка: ' + (data.detail || 'не удалось удалить'))`. Заголовки/Content-Type/body НЕ передавать (DELETE без тела, CSRF в проекте нет — авторизация только по cookie session, см. main.py:16-24)"
    - "T-10: Кнопка «Удалить лид» НЕ появляется в канбане (kanban.html, partials/kanban_board.html) — только в карточке лида. Удаление из канбана — out-of-scope (см. YAGNI). После удаления юзер редиректится на /kanban, где лид уже отсутствует в БД и не отрендерится. Доп. обновление DOM канбана НЕ требуется"
    - "T-11: Роут delete_lead устойчив к double-submit: повторный DELETE на уже удалённый lead_id вернёт 404 (select → scalar_one_or_none() → None → raise 404). Фронт на 404 отдаёт alert «не удалось удалить», но это не ломает UX (user уже на /kanban после первого успешного клика)"
  artifacts:
    - path: app/routes/leads.py (модификация)
      provides: "новый роут @router.delete('/leads/{lead_id}') → delete_lead; серверный role-gate (admin/supervisor); явное удаление StageHistory и AgentMessage по lead_id; shutil.rmtree(storage/documents/{lead_id}); session.delete(lead) + commit; JSONResponse {ok:true} / {ok:false,detail} с rollback при ошибке"
    - path: app/templates/lead_card.html (модификация)
      provides: "кнопка «Удалить лид» в шапке под role-gate supervisor/admin; var LEAD_NAME = {{ lead.name | tojson }}; функция deleteLead() с confirm + fetch DELETE + редирект на /kanban"
  key_links:
    - from: app/templates/lead_card.html (кнопка «Удалить лид»)
      to: app/routes/leads.py (delete_lead)
      via: "onclick=\"deleteLead()\" → fetch('/leads/' + LEAD_ID, {method:'DELETE'}) → роут @router.delete('/leads/{lead_id}')"
      pattern: "Нативный fetch + DELETE (как saveLeadName через POST), НЕ htmx — потому что источник DOM исчезает после удаления и нужен window.location редирект"
    - from: app/routes/leads.py (delete_lead)
      to: app/models.py (Lead relationships)
      via: "session.delete(lead) → ORM-cascade удаляет contacts/contact_logs/comments/tasks/deals/documents (models.py:98-103)"
      pattern: "SQLAlchemy ORM-cascade, НЕ raw SQL — потому что PRAGMA foreign_keys=OFF в этом проекте и DB-level ondelete не работает"
    - from: app/routes/leads.py (delete_lead)
      to: storage/documents/{lead_id}/ (файлы на диске)
      via: "shutil.rmtree(path, ignore_errors=True) — ручная очистка, т.к. ORM-cascade не знает про файловую систему"
      pattern: "Первая точка удаления файлов в проекте — дублирует паттерн future cleanup для других сущностей с файлами (templates)"
    - from: app/routes/leads.py (delete_lead)
      to: app/models.py (StageHistory, AgentMessage)
      via: "delete(StageHistory).where(lead_id == ...) и delete(AgentMessage).where(context_lead_id == ...) — ручная очистка orphan-таблиц без relationship к Lead"
      pattern: "Явное удаление зависит от БД-инварианта: в этом проекте FK выключены, поэтому orphan-записи никогда не чистятся автоматически"
---

# Plan 12-01 — Удаление лида (карточка, admin/supervisor)

**Phase:** 12 — lead-delete
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

Удаления лида в проекте **нет вообще** — ни endpoint, ни кнопки, ни soft-delete полей (`is_deleted`/`deleted_at`/`archived` отсутствуют, `grep` по `app/` пусто). Доступные сейчас операции над лидом: смена стадии (в т.ч. «потеря» `stage="lost"` + `loss_reason`), переименование, редактирование инфо/реквизитов, назначение менеджера, импорт. Полностью удалить заведомо мусорного/дублирующего лида вместе со всеми его контактами, журналом, задачами, сделками и документами — нельзя. Это блокирует нормальную поддержку БД: дубли при импорте, тестовые лиды, ошибочно заведённые — копятся.

Задача (требование пользователя): **для ролей admin и supervisor — кнопка «Удалить лид» в карточке лида.** Обычный `manager` кнопки не видит и не может удалить (даже если вызовет endpoint напрямую — серверный 403).

**Root cause (подтверждено чтением кода):**
- В `app/routes/leads.py` (1205 строк) НЕТ ни `@router.delete("/leads/{lead_id}")`, ни `@router.post("/leads/{lead_id}/delete")`. Единственный DELETE в файле — `delete_contact` (`leads.py:641-658`), который удаляет контакт **внутри** лида, не самого лида.
- В `app/templates/lead_card.html` (185 строк) нет ни одной кнопки удаления — `grep -ni "delete\\|удал"` находит только CSS-`classList.remove(...)`.
- Soft-delete полей в `Lead` (`models.py:47-103`) нет — будет hard-delete. Удаление **необратимо**, поэтому в UI обязательно жёсткий confirm с предупреждением о составе удаляемых данных.

**Критичные подводные камни (обязательно учесть кодеру — без них данные повредятся):**

1. **ORM-cascade покрывает только 6 таблиц.** У `Lead` настроены `cascade="all, delete-orphan"` для `contacts/contact_logs/comments/tasks/deals/documents` (`models.py:98-103`). Эти таблицы уйдут автоматически при `session.delete(lead)`. **НО две таблицы имеют FK на `leads.id` БЕЗ cascade и без relationship к Lead:**
   - `StageHistory` (`models.py:106-115`) — история смены стадий (фактически audit-таблица лида);
   - `AgentMessage` (`models.py:248`) — история чата с ИИ по контексту лида (`context_lead_id`).
   Их надо удалить **явно** по `lead_id`, иначе в БД остаются orphan-записи со ссылкой на несуществующий лид.

2. **SQLite FK выключены.** В `app/database.py:7-8` engine создаётся БЕЗ `PRAGMA foreign_keys=ON`, и больше нигде это не выставляется (поиск `PRAGMA` → только `table_info`, `journal_mode`, `integrity_check`, `foreign_key_check`). Значит: **raw SQL `DELETE FROM leads` НЕ включит cascade вообще** — все 8 зависимых таблиц останутся как orphan. Удалять только через `session.delete(lead)` (ORM-cascade), а StageHistory/AgentMessage — отдельным `delete(...)`.

3. **Orphan-файлы на диске.** Документы хранятся в `storage/documents/{lead_id}/doc_*.docx` и `.pdf` (`documents.py:203-207`). В БД пути — `Document.file_path` / `file_path_pdf` (`models.py:219-220`). При ORM-cascade строки `Document` уйдут, а **физические файлы останутся навсегда** — в проекте НЕТ ни `os.remove`, ни `Path.unlink`, ни `shutil.rmtree` нигде в `app/` (это первая точка удаления файлов вообще). Нужен явный `shutil.rmtree(storage/documents/{lead_id}/, ignore_errors=True)`.

4. **Внешних систем нет.** Проверено: `bitrix`/`1c`/`erp`/`webhook`/`external_api` — пусто в `app/`, `scripts/`, `mcp_server.py`. Deal (`models.py:192-204`) живёт только локально, полей `external_id` нет. Каскадное удаление Deal безопасно, рассинхрона с внешними системами не будет.

5. **CSRF в проекте нет.** Авторизация — только по cookie `session` (`AuthMiddleware` в `main.py:16-24`). В существующих `fetch`/`hx-post` (`saveLeadName`, `api_change_stage`) никаких заголовков и токенов не передаётся. Новый DELETE идёт по тому же паттерну — без заголовков.

## Архитектура (обязательно к соблюдению)

**Hard-delete лида через FastAPI DELETE-роут с серверным role-gate + ручная очистка 3 категорий зависимостей.** Принципы:

1. **Hard-delete, не soft.** Soft-delete не заложен в модель, вводить его в этой фазе = разрастание (затронет все 60+ SELECT по лидам, канбан, фильтры, MCP, mcp_server.py). MVP = необратимое удаление с жёстким confirm в UI. Если позже понадобится «корзина» — это отдельная фаза.

2. **Серверный role-gate обязателен и первичен.** UI-gate (Jinja `{% if current_user.role.value in ('supervisor', 'admin') %}`) скрывает кнопку, но это косметика. Серверная проверка `user.role.value not in ("admin", "supervisor")` → 403 — единственная настоящая защита. Любой запрос DELETE от менеджера (через curl/консоль) обязан получить 403. Паттерн как в `leads.py:278`.

3. **Порядок операций внутри транзакции — детерминированный и атомарный:**
   ```
   BEGIN
     1. select Lead by id (если None → 404)
     2. role-gate (если не admin/supervisor → 403)
     3. delete(StageHistory).where(lead_id == X)    # БД-orphan
     4. delete(AgentMessage).where(context_lead_id == X)  # БД-orphan
     5. shutil.rmtree(storage/documents/X/, ignore_errors=True)  # файлы
     6. session.delete(lead)                         # ORM-cascade на 6 таблиц
     7. session.commit()
   EXCEPTION → session.rollback(); return 500 {ok:false}
   ```
   Шаги 3-4 — БД-изменения, попадают в ту же транзакцию, что и 6-7. Шаг 5 (файлы) — НЕ транзакционный (файловая система), поэтому `ignore_errors=True`: если файлы не удалятся, лид всё равно удалится из БД (потеря файлов на диске — менее критична, чем полусостояние «файлы есть, лид уже удалён, откатить нельзя»). Если упадут шаги 3/4/6/7 — rollback вернёт ВСЁ в исходное состояние, user увидит ошибку и сможет повторить.

4. **DELETE-метод на FastAPI, не POST.** В `delete_contact` (`leads.py:641`) уже используется `@router.delete(...)` — продолжаем паттерн. Front дёргает `fetch(url, {method:'DELETE'})`. На уровне HTTP это семантически корректный delete.

5. **Редирект делает фронт, не сервер.** Сервер возвращает `JSONResponse({ok:true})`, JS в `deleteLead()` делает `window.location.href = '/kanban'`. Серверный `RedirectResponse` на fetch-запрос вернёт тело HTML, фронт сломается при `r.json()`. Этим же продиктован выбор нативного `fetch` вместо htmx: источник DOM (карточка лида) исчезает, swap невозможен.

6. **Канбан не трогаем.** После редиректа на `/kanban` лид уже отсутствует в БД — он просто не отрендерится. Дополнительного обновления DOM канбана (через HTMX или ручное) НЕ нужно.

## Файлы

### 1. `app/routes/leads.py` (модификация)

**(a) Импорты вверху файла** — проверить и при необходимости добавить:
```python
import shutil
from pathlib import Path
from fastapi.responses import JSONResponse
from sqlalchemy import delete   # для bulk-delete StageHistory/AgentMessage
```
> `delete` из `sqlalchemy` — это функция bulk-удаления, отличается от `session.delete(obj)` (ORM-удаление одного объекта). Проверить что уже импортировано (`select` точно есть, см. lead_card). Если `shutil`/`Path`/`JSONResponse`/`delete` уже импортированы — НЕ дублировать.

**(b) Новый роут** — разместить рядом с другими операциями над лидом (логично после `assign_manager` ~leads.py:929, до DaData-блока ~leads.py:1109):
```python
@router.delete("/leads/{lead_id}")
async def delete_lead(
    request: Request,
    lead_id: int,
    session: AsyncSession = Depends(get_session),
):
    # 1. Авторизация + серверный role-gate
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    if user.role.value not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    # 2. Загрузить лид (если нет → 404)
    result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")

    try:
        # 3. Явно удалить БД-orphan'ы без ORM-cascade к Lead
        await session.execute(
            delete(StageHistory).where(StageHistory.lead_id == lead_id)
        )
        await session.execute(
            delete(AgentMessage).where(AgentMessage.context_lead_id == lead_id)
        )

        # 4. Удалить файлы документов на диске (ignore_errors — если нет папки)
        docs_dir = Path("storage/documents") / str(lead_id)
        if docs_dir.exists():
            shutil.rmtree(docs_dir, ignore_errors=True)

        # 5. Удалить сам лид → ORM-cascade на 6 зависимых таблиц
        await session.delete(lead)
        await session.commit()
    except Exception:
        await session.rollback()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "detail": "Ошибка удаления лида"},
        )

    return JSONResponse(status_code=200, content={"ok": True})
```
> **Пояснения:**
> - Шаги 3-5 идут в одной транзакции async-session (SQLAlchemy async session с begin-on-commit). `session.execute(delete(...))` и `session.delete(lead)` накапливаются, `commit()` фиксирует всё разом. При исключении на любом шаге — rollback откатывает ВСЕ изменения, включая шаги 3-4.
> - Шаг 4 (файлы) — вне транзакции БД. Если `shutil.rmtree` упадёт, исключение попадёт в `except`, rollback откатит шаги 3-4, лид останется жив. `ignore_errors=True` — на случай отсутствия папки (лид без документов) или прав доступа.
> - Порядок «сначала orphan БД → потом файлы → потом лид» выбран так, чтобы при сбое на шаге 5 (маловероятно, но) у нас не осталось ситуации «файлы удалены, лид жив, StageHistory уже удалён» — rollback вернёт БД в согласованное состояние.
> - `StageHistory` и `AgentMessage` должны быть импортированы из `app.models` вверху файла (проверить, что уже есть; `Lead` точно импортирован).

### 2. `app/templates/lead_card.html` (модификация)

**(a) Кнопка в шапке (~стр. 46-52)** — рядом с кнопкой «Отправить в чат», внутри role-gate:
```html
{% if current_user.role.value in ('supervisor', 'admin') %}
<button type="button" onclick="deleteLead()"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm text-red-600 hover:text-red-800 hover:bg-red-50 transition-colors"
        title="Удалить лида без возможности восстановления">
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
    </svg>
    Удалить лид
</button>
{% endif %}
```
> Иконка-мусорка идентична `contact_row.html:25-29` — визуальная консистентность с другими destructive-действиями в проекте. `text-red-600` + `hover:bg-red-50` — деструктивная семантика без перегруза (как `task_card.html:44-52`).

**(b) Глобальные переменные в `<script>`** — рядом с `var LEAD_ID = {{ lead.id }};` (~стр. 97):
```javascript
var LEAD_ID = {{ lead.id }};
var LEAD_NAME = {{ lead.name | tojson }};   // ← НОВОЕ, безопасное экранирование кавычек/апострофов в названии
```
> `tojson` обязательно — название лида может содержать одинарную/двойную кавычку (например «ООО \"Рога и копыта\"»), и `var LEAD_NAME = '{{ lead.name }}';` сломает JS-синтаксис. `tojson` выдаст корректный JS-строковый литерал.

**(c) Функция `deleteLead()`** — в блок `<script>` (~стр. 84-183), рядом с `saveLeadName`:
```javascript
function deleteLead() {
    if (!confirm('Удалить лида «' + LEAD_NAME + '» без возможности восстановления?\n\nБудут удалены: все контакты, журнал контактов, комментарии, задачи, сделки, документы (включая .docx/.pdf файлы).\n\nЭто действие НЕОБРАТИМО.')) {
        return;
    }
    fetch('/leads/' + LEAD_ID, { method: 'DELETE' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.ok) {
                window.location.href = '/kanban';
            } else {
                alert('Ошибка: ' + (data.detail || 'не удалось удалить лида'));
            }
        })
        .catch(function(err) { alert('Ошибка запроса: ' + err.message); });
}
```
> Паттерн 1-в-1 с `saveLeadName` (`lead_card.html:117-162`) + `confirm` из `applyDadata` (`lead_info_form.html:287-321`). Никаких заголовков, никакого CSRF — авторизация по cookie session. После успеха — редирект на `/kanban` (лид уже отсутствует в БД, доска отрендерится без него).

## Шаги выполнения

1. `app/routes/leads.py`:
   - Проверить/добавить импорты `shutil`, `pathlib.Path`, `JSONResponse`, `sqlalchemy.delete`, `StageHistory`, `AgentMessage`.
   - Добавить роут `delete_lead` (~25 строк) после `assign_manager`.
2. `app/templates/lead_card.html`:
   - Добавить кнопку «Удалить лид» в role-gate в шапке.
   - Добавить `var LEAD_NAME = {{ lead.name | tojson }};`.
   - Добавить функцию `deleteLead()` в `<script>`.
3. Ручная проверка сценариев (см. Acceptance) — критично: role-gate, 404 на несуществующем, orphan-файлы реально удаляются, каскад реально убирает 6 таблиц, StageHistory/AgentMessage реально пусты после удаления.

## Acceptance criteria (gate)

- [ ] Кнопка «Удалить лид» видна в карточке лида только для ролей admin и supervisor. Для manager кнопки НЕТ (проверить логином разных ролей).
- [ ] Клик по кнопке → confirm-диалог с текстом про необратимость + перечень удаляемых данных.
- [ ] Отмена confirm → ничего не происходит, лид остаётся.
- [ ] Подтверждение → лид удаляется, юзер редиректится на `/kanban`, удалённого лида на доске НЕТ.
- [ ] В БД после удаления: строка `leads` удалена, строки `contacts`/`contact_logs`/`comments`/`tasks`/`deals`/`documents` для этого lead_id удалены (ORM-cascade сработал).
- [ ] В БД после удаления: `stage_history` для этого lead_id НЕ содержит orphan-записей (явный delete сработал) — проверить `SELECT * FROM stage_history WHERE lead_id = X` возвращает 0 строк.
- [ ] В БД после удаления: `agent_messages` для этого `context_lead_id` НЕ содержит orphan-записей — проверить `SELECT * FROM agent_messages WHERE context_lead_id = X` возвращает 0 строк.
- [ ] Папка `storage/documents/{lead_id}/` удалена с диска (если была). Если у лида документов не было — ошибки нет.
- [ ] **Серверный role-gate:** запрос `curl -X DELETE /leads/{id}` под сессией manager возвращает **403** (проверить в DevTools/Network или curl с cookie). Даже если менеджер как-то увидит кнопку — её клик приведёт к alert «Недостаточно прав».
- [ ] **404 на несуществующем:** запрос `DELETE /leads/999999` возвращает 404 (лид не найден), фронт показывает alert.
- [ ] **500 при сбое БД:** симулировать не обязательно, но кодер обязан показать что блок `try/except/rollback` есть и `JSONResponse(500, {ok:false})` возвращается.
- [ ] **Название с кавычками:** создать лида с названием `ООО "Тест"` (или `ООО «Тест»`) → кнопка удаления работает, confirm показывает корректное название без `undefined` или JS-ошибки в консоли.
- [ ] **Double-submit:** быстро кликнуть дважды → первый удаляет, второй возвращает 404, фронт уже на `/kanban`, не падает.
- [ ] Удаление лида **с** сделкой → сделка удалена каскадом, в `/leads/{lead_id}` (404 после удаления), в списке сделок (`/deals` если есть) этой сделки нет.
- [ ] Удаление лида **с** задачей → задача удалена каскадом, в `/tasks` (или сайдбаре задач) этой задачи нет.
- [ ] Канбан-доска не сломана: после удаления лида вернуться на `/kanban`, проверить drag-and-drop и счётчики колонок работают корректно.

## Не делаем (YAGNI)

- **НЕ делаем soft-delete** (`is_deleted`/`deleted_at`/`archived`) — это потребует переписать 60+ SELECT по лидам во всех роутах, канбане, фильтрах, MCP-сервере. Если понадобится «корзина» — отдельная фаза.
- **НЕ добавляем кнопку удаления в канбан** (kanban.html / partials/kanban_board.html) — удаление только из карточки. Если user хочет удалить — открывает карточку. Это out-of-scope, отдельная UX-задача (с обновлением DOM доски, счётчиков, и т.п.).
- **НЕ делаем массовое удаление** (multi-select в канбане → удалить всё выделенное) — отдельная фаза, требует UI выбора и batch-эндпоинта.
- **НЕ трогаем** `app/static/js/kanban.js`, `mcp_server.py`, MCP-инструменты — удаление только через UI карточки.
- **НЕ экспортируем удалённого лида в архив** (snapshot в JSON/file перед удалением) — over-engineering для MVP. Если когда-то понадобится audit-trail удалений — это отдельная фаза с `deleted_leads`-таблицей.
- **НЕ добавляем webhook/уведомление** другим пользователям об удалении лида — нет инфраструктуры уведомлений, out-of-scope.
- **НЕ блокируем удаление при активных задачах/сделках** (как `delete_user` блокирует при зависимостях) — лид это не пользователь, его зависимости корректно удаляются каскадом. Блокировка была бы over-engineering для MVP.
- **НЕ запрашиваем причину удаления** (как `loss_reason` при `stage="lost"`) — это не «потеря», это физическое удаление. Audit через StageHistory/AgentMessage остаётся, но отдельного поля «причина удаления» не вводим.
