---
phase: 15-task-save-ux-feedback
plan: "01"
slice: 15-01
type: execute
wave: 1
depends_on:
  - phase-7
requirements:
  - CRM-15-01
autonomous: true
files_modified:
  - app/templates/partials/task_edit_form.html
files_created: []
must_haves:
  truths:
    - "T-01: На кнопке «Сохранить» в app/templates/partials/task_edit_form.html (строки 35-38) добавлен атрибут `hx-disabled-elt=\"this\"` — это встроенный механизм htmx, который блокирует кнопку на время запроса (ставит disabled) и автоматически разблокирует после ответа. Паттерн 1-в-1 скопирован из lead_form.html:90 (там на кнопке «Создать лид» уже работает). Это устраняет дублирующие PUT-запросы при многократных кликах пользователя («тыкал, тыкал — висит»), что само по себе было причиной усугубления зависания"
    - "T-02: На форме добавлен обработчик `hx-on::response-error=\"var btn=document.getElementById('task-edit-submit'); btn.disabled=false; btn.textContent='Сохранить'; event.detail.xhr.response && showToast(JSON.parse(event.detail.xhr.response).detail || 'Ошибка сохранения', 'error');\"`. Паттерн 1-в-1 из lead_form.html:4. Это решает вторичную причину: при ошибке валидации (422 «Название обязательно», 403 «не свои задачи», 500) drawer раньше НЕ закрывался и toast НЕ показывался → пользователь видел «зависание/не работает». Теперь при ошибке: кнопка разблокируется (на случай если htmx не снял disabled), текст восстанавливается, показывается красный toast с сообщением из {detail}"
    - "T-03: Существующий обработчик `hx-on::after-request=\"if(event.detail.successful){ closeDrawer(); showToast('Задача обновлена'); }\"` (task_edit_form.html:7) ОСТАЁТСЯ без изменений. after-request срабатывает на любой ответ (успех+ошибка), но ветка `if(event.detail.successful)` корректно отличает успех — при успехе drawer закрывается, показывается зелёный toast. При ошибке after-request ничего не делает (нет else), и отрабатывает параллельный response-error (T-02)"
    - "T-04: Роут update_task (app/routes/tasks.py:243-295) НЕ ТРОГАЕТСЯ. Разведка подтвердила: серверная сторона минимальна и оптимальна — 1 SELECT по PK (tasks.py:264) + 1 UPDATE при commit (tasks.py:289) + 1 SELECT в get_current_user (auth.py:86-88), без N+1, без selectinload, без внешних вызовов, без hooks, без sleep, без redirect-chain. Ответ — маленький partial task_card.html с минимальным контекстом {current_user, task} (tasks.py:291-295). Причина «зависания» — фронтенд-видимость, не сервер"
    - "T-05: Решение пользователя (AskUserQuestion) — только UI-фикс. Глобальный `htmx.config.requestTimeout` в base.html и `PRAGMA busy_timeout` в database.py ВНЕ scope этой фазы (см. YAGNI). При спорадических сетевых/конкурентных задержках эффект может сохраняться — это documented known-limitation"
  artifacts:
    - path: app/templates/partials/task_edit_form.html (модификация)
      provides: "T-01: hx-disabled-elt=\"this\" на кнопке Сохранить (блокировка повторных кликов). T-02: hx-on::response-error на форме с разблокировкой кнопки + toast об ошибке. T-03: существующий hx-on::after-request сохранён без изменений"
  key_links:
    - from: app/templates/partials/task_edit_form.html (кнопка Сохранить)
      to: htmx (механизм hx-disabled-elt)
      via: "hx-disabled-elt=\"this\" → htmx ставит button.disabled=true на время запроса и снимает после ответа"
      pattern: "Встроенный механизм htmx, уже применяется в lead_form.html:90 — визуальная и поведенческая консистентность"
    - from: app/templates/partials/task_edit_form.html (hx-on::response-error)
      to: app/templates/base.html (showToast)
      via: "showToast(message, 'error') — функция уже определена в base.html:96, поддерживает типы"
      pattern: "Использует существующую инфраструктуру toast'ов, не вводит новый JS"
    - from: app/routes/tasks.py (update_task ошибки 422/403/500)
      to: app/templates/partials/task_edit_form.html (toast)
      via: "HTTPException(detail=...) → JSON ответ {detail:...} → event.detail.xhr.response → showToast(detail, 'error')"
      pattern: "Сервер уже отдаёт детальные сообщения об ошибках (tasks.py:270, 274) — фронт просто не показывал их пользователю"
---

# Plan 15-01 — Визуальный отклик кнопки «Сохранить» в редактировании задачи

**Phase:** 15 — task-save-ux-feedback
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

**Симптом (от пользователя):** при редактировании задачи кнопка «Сохранить» даёт ощущение зависания / большого таймаута — будто не работает или зависло.

**Разведка показала: сервер НЕ виноват.** Роут `update_task` (`app/routes/tasks.py:243-295`) минимален и оптимален:
- 1 SELECT по PK `Task.id` (tasks.py:264, индексный lookup, мгновенно);
- 1 UPDATE при `session.commit()` (tasks.py:289);
- 1 SELECT в `get_current_user` (auth.py:86-88, на каждый запрос);
- ответ — маленький partial `task_card.html` (55 строк), контекст `{current_user, task}`, без N+1, без selectinload, без внешних вызовов, без SQLAlchemy event-listeners, без redirect-chain, без sleep/email/уведомлений.

Сервер отрабатывает за миллисекунды. Проблема — **в отсутствии визуального отклика на фронтенде**:

| Причина | Где | Эффект |
|---|---|---|
| **Нет `hx-indicator`/спиннера** | `task_edit_form.html:35-38` | Пользователь кликает — визуально ничего не происходит до возврата ответа. Даже 200 мс воспринимаются как «зависло» |
| **Нет блокировки повторного клика** | `task_edit_form.html:35-38` | Юзер тыкает N раз → N дублирующих PUT в очереди → реальное замедление + «висит и висит» |
| **`hx-on::after-request` молчит при ошибке** | `task_edit_form.html:7` | При 422 (пустое название)/403/500 drawer НЕ закрывается и toast НЕ показывается → «не работает» |

Эти три фактора суммарно и дают субъективное «зависание/не работает».

**Решение пользователя (AskUserQuestion):** только UI-фикс. Глобальный htmx timeout и SQLite busy_timeout — вне scope (см. YAGNI).

## Архитектура (обязательно к соблюдению)

**Применить готовый паттерн `lead_form.html` к `task_edit_form.html` 1-в-1.** Принципы:

1. **`hx-disabled-elt=\"this\"` на кнопке** — встроенный механизм htmx, ставит `button.disabled=true` на время запроса и автоматически снимает после ответа. Никакого JS, никакого своего state. Уже работает в `lead_form.html:90`.

2. **`hx-on::response-error` на форме** — htmx event, срабатывает ТОЛЬКО при неуспешном HTTP-ответе (4xx/5xx). Внутри: разблокировать кнопку (на случай если disabled не снялся — htmx обычно снимает сам, но дешёвая подстраховка), восстановить текст «Сохранить», показать красный toast с `detail` из ответа сервера. Паттерн 1-в-1 из `lead_form.html:4`.

3. **`hx-on::after-request` остаётся как есть.** Этот event срабатывает на любой ответ, но ветка `if(event.detail.successful)` корректно отличает успех. При успехе: `closeDrawer()` + зелёный toast. При ошибке: `after-request` ничего не делает (нет else), отрабатывает параллельный `response-error`.

4. **Использовать существующую инфраструктуру toast'ов.** `showToast(message, type)` уже определена в `base.html:96` и поддерживает тип `'error'` (красный). Не вводим новый JS.

5. **Сервер уже отдаёт человекочитаемые сообщения об ошибках** — `HTTPException(status_code=422, detail=\"Название обязательно\")` (tasks.py:274), `\"Можно редактировать только свои задачи\"` (tasks.py:270). Фронт просто не показывал их пользователю — теперь будет.

## Файлы

### 1. `app/templates/partials/task_edit_form.html` (модификация)

**(a) Форма — добавить `hx-on::response-error` (строка 5-7):**

Было:
```html
<form hx-put="/api/tasks/{{ task.id }}"
      hx-target="#task-{{ task.id }}" hx-swap="outerHTML"
      hx-on::after-request="if(event.detail.successful){ closeDrawer(); showToast('Задача обновлена'); }">
```

Стало:
```html
<form hx-put="/api/tasks/{{ task.id }}"
      hx-target="#task-{{ task.id }}" hx-swap="outerHTML"
      hx-on::after-request="if(event.detail.successful){ closeDrawer(); showToast('Задача обновлена'); }"
      hx-on::response-error="var btn=document.getElementById('task-edit-submit'); btn.disabled=false; btn.textContent='Сохранить'; event.detail.xhr.response && showToast(JSON.parse(event.detail.xhr.response).detail || 'Ошибка сохранения', 'error');">
```

> **Пояснения:**
> - `hx-on::response-error` срабатывает только при 4xx/5xx. `hx-on::after-request` срабатывает всегда, но его `if(event.detail.successful)` фильтрует только успех. Эти два event'а НЕ конфликтуют — при ошибке сработают оба, но `after-request` ничего не сделает (нет else), а `response-error` покажет toast.
> - `btn.disabled=false` — подстраховка. htmx после `response-error` обычно сам снимает `disabled` с `hx-disabled-elt`, но `lead_form.html:4` делает это явно и мы повторяем проверенный паттерн.
> - `btn.textContent='Сохранить'` — на случай если будет добавлен текст «Сохранение...» в будущем (сейчас в T-01 мы НЕ меняем текст кнопки, но подстраховка от будущих изменений не мешает).
> - `JSON.parse(event.detail.xhr.response).detail` — сервер (FastAPI HTTPException) отдаёт JSON вида `{"detail": "Название обязательно"}`. Это работает для всех существующих raise в `update_task` (tasks.py:262, 266, 270, 274).
> - `|| 'Ошибка сохранения'` — фолбэк, если detail пустой или response не JSON.

**(b) Кнопка — добавить `hx-disabled-elt=\"this\"` (строки 35-38):**

Было:
```html
<button type="submit" id="task-edit-submit"
        class="w-full bg-ink text-white px-4 py-2 rounded-lg text-sm hover:bg-ink/90">
    Сохранить
</button>
```

Стало:
```html
<button type="submit" id="task-edit-submit"
        hx-disabled-elt="this"
        class="w-full bg-ink text-white px-4 py-2 rounded-lg text-sm hover:bg-ink/90 disabled:opacity-60 disabled:cursor-not-allowed">
    Сохранить
</button>
```

> **Пояснения:**
> - `hx-disabled-elt=\"this\"` — htmx ставит `disabled=true` на эту кнопку при отправке формы, автоматически снимает после ответа (успех или ошибка). Полностью убирает возможность дублирующих кликов. Паттерн 1-в-1 из `lead_form.html:90`.
> - `disabled:opacity-60 disabled:cursor-not-allowed` — Tailwind-классы для визуальной индикации заблокированной кнопки (становится серой, курсор «нельзя»). Без этого `disabled` сработает функционально, но визуально кнопка останется как активная — пользователь не поймёт, что произошло. Это мини-индикатор взамен отсутствующего спиннера.
> - `id=\"task-edit-submit\"` остаётся (он нужен для разблокировки в response-error из T-02).

> ⚠️ **Почему НЕ добавляем hx-indicator (спиннер):** `hx-disabled-elt` + `disabled:opacity-60` даёт достаточно визуального отклика — кнопка сереет и перестаёт принимать клики. Спиннер — избыточен для формы из 4 полей с миллисекундным ответом сервера. Если позже понадобится спиннер — добавить `<span class=\"htmx-indicator\">...</span>` и `hx-indicator=\"find .htmx-indicator\"`, но это отдельная UX-задача, не блокер.

## Шаги выполнения

1. `app/templates/partials/task_edit_form.html`:
   - На `<form>` добавить `hx-on::response-error=\"...\"` (T-02). Существующий `hx-on::after-request` НЕ трогать (T-03).
   - На `<button id=\"task-edit-submit\">` добавить `hx-disabled-elt=\"this\"` и `disabled:opacity-60 disabled:cursor-not-allowed` в class (T-01).
2. Ручная проверка сценариев (см. Acceptance) — критично: визуальный отклик при нормальном сохранении, блокировка повторных кликов, toast при ошибке валидации.

## Acceptance criteria (gate)

- [ ] **Нормальное сохранение:** заполнить валидную форму → клик «Сохранить» → кнопка **сразу** сереет (`disabled:opacity-60`) и перестаёт принимать клики → через мгновение drawer закрывается, показывается зелёный toast «Задача обновлена». Ощущения зависания НЕТ — есть чёткий визуальный отклик.
- [ ] **Блокировка повторных кликов:** быстро кликнуть «Сохранить» 3-5 раз подряд → уходит ОДИН PUT-запрос (проверить в DevTools/Network), остальные клики игнорируются (кнопка disabled). Раньше ушло бы N дублирующих запросов.
- [ ] **Ошибка валидации (422):** очистить поле «Название» → клик «Сохранить» → кнопка разблокируется, показывается красный toast «Название обязательно» (detail из tasks.py:274), drawer НЕ закрывается (форма остаётся, пользователь видит свою ошибку). Раньше — никакого отклика, «зависание».
- [ ] **Ошибка доступа (403):** (только если тестировщик может сэмулировать — например, менеджер пытается редактировать чужую задачу через curl, или проверка на тестовых данных) → toast «Можно редактировать только свои задачи» (detail из tasks.py:270).
- [ ] **Серверная ошибка (500):** при любой нештатной ситуации → toast «Ошибка сохранения» (фолбэк при отсутствии detail), кнопка разблокирована, форма не «зависла».
- [ ] **Восстановление после ошибки:** после показа ошибки валидации (422) → заполнить название → клик «Сохранить» → успешное сохранение, drawer закрыт, зелёный toast. Повторный сабмит работает корректно (кнопка не застревает в disabled).
- [ ] **Регрессия drawer'а:** `closeDrawer()` и `showToast()` вызываются корректно — взять за эталон `lead_form.html` (там тот же стек `after-request` + `response-error` работает). Если на сворачивании drawer'а есть JS-ошибка в консоли — фиксить не в этой фазе, но отметить в README-CONTRACT.
- [ ] **Сервер не тронут:** diff `app/routes/tasks.py` — пустой. Все сообщения об ошибках (422 «Название обязательно», 403 «Можно редактировать только свои задачи», 404 «задача не найдена») уже возвращаются сервером и теперь показываются юзеру.

## Не делаем (YAGNI)

- **НЕ добавляем `hx-indicator` (спиннер)** — `hx-disabled-elt` + `disabled:opacity-60` даёт достаточно визуального отклика для формы из 4 полей с миллисекундным ответом. Спиннер — избыточен. Если позже понадобится для длинных операций — отдельная UX-задача.
- **НЕ меняем текст кнопки на «Сохранение...»** — `disabled:opacity-60` достаточно. Динамическая смена текста добавила бы JS-сложности без реальной пользы для UX. Подстраховка `btn.textContent='Сохранить'` в response-error остаётся (на случай будущих изменений), но самой смены текста НЕТ.
- **НЕ добавляем глобальный `htmx.config.requestTimeout`** в `base.html` — решение пользователя «только UI-фикс». При спорадических сетевых задержках htmx будет ждать бесконечно (как сейчас). Если станут массовыми — отдельная фаза с таймаутом + toast «Сервер не отвечает». Сейчас — known-limitation.
- **НЕ добавляем `PRAGMA busy_timeout=5000`** в `database.py` — решение пользователя. SQLite write-lock при конкурентных вкладках остаётся как есть (WAL режим смягчает). Отдельная фаза, если станут массовыми ошибки `database is locked`.
- **НЕ трогаем `update_task` (tasks.py:243-295)** — сервер оптимален, причина не в нём.
- **НЕ трогаем `create_task`** (в leads.py) и его UI (`task_form.html`) — жалоб на создание не было. Применить паттерн туда можно попутно, но это separate concern — оставить на усмотрение, НЕ блокер этой фазы. Если кодер видит, что в task_form.html ТАКАЯ же проблема (нет hx-disabled-elt/response-error) — может заодно пофиксить, но это НЕ acceptance criterion.
- **НЕ добавляем middleware для логирования времени запроса** — полезно для дев-диагностики, но не часть UX-фикса. Отдельная дев-фаза.
- **НЕ вводим optimistic concurrency control** (версионирование задач, проверка stale-update) — over-engineering, в жалобе нет симптома race condition при редактировании.
- **НЕ объединяем стили кнопок** в общий CSS-класс / компонент — пусть `task_edit_form.html` остаётся точечной правкой. Рефакторинг форм — отдельная фаза.
