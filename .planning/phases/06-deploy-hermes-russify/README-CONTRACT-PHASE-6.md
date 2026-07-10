# README-CONTRACT — Phase 6: Hermes AI Dock + русификация

**Phase:** 6 — deploy-hermes-russify
**Verdict:** **PASS**
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo
**Date:** 2026-07-11

---

## Итоговый вердикт: PASS

Фаза 6 завершена. Hermes AI Dock реализован (модель, сервис, роутер, UI). Русификация выполнена — «Таски» → «Задачи» везде. Graceful degradation работает (Hermes локально не запущен — чат показывает сообщение об ошибке, история сохраняется). Деплой на rai-dev — следующий блок техлида.

---

## D-критерии — сводка

| # | Критерий | Статус | Примечание |
|---|---|:---:|---|
| D-01 | config.py: HERMES_API_URL, TOKEN, TIMEOUT, ENABLED | ✅ | 4 поля, читаются из .env через pydantic-settings |
| D-02 | AgentMessage модель создана | ✅ | id, user_id, role, content, context_lead_id, actions, created_at. Связь user. Таблица в БД существует |
| D-03 | hermes_service.py: send_to_hermes() с graceful degradation | ✅ | ConnectError, TimeoutException, HERMES_ENABLED=False, generic Exception — все обработаны |
| D-04 | GET /agent — страница чата, последние 50 сообщений | ✅ | 200, history + composer + quick actions |
| D-05 | POST /agent/send — HTMX, сохраняет user+assistant, вызывает Hermes | ✅ | 200, partial возвращается, AgentMessage записи создаются |
| D-06 | POST /agent/clear — удаление истории | ✅ | 200, редирект на /agent, история очищается |
| D-07 | При недоступности Hermes — сообщение об ошибке, история сохраняется | ✅ | Проверено: «Не удалось подключиться к агенту» — оба AgentMessage сохранены |
| D-08 | agent_chat.html — AI Dock по канону | ✅ | header → history (bubbles) → composer (primary bg-ink) → quick actions (3 кнопки) |
| D-09 | agent_message_pair.html — partial для HTMX | ✅ | user message (bg-ink right) + agent reply (bg-slate-50 left) + time |
| D-10 | Sidebar: «Задачи» + «Чат с агентом» | ✅ | Проверено: «Таски» нет, «Задачи» есть, «Чат с агентом» → /agent |
| D-11 | grep «таск» → 0 | ✅ | 0 вхождений во всех шаблонах |
| D-12 | Весь UI-текст на русском | ✅ | Проверено: placeholder, кнопки, empty states — русский |
| D-13 | httpx в requirements.txt | ✅ | |
| D-14 | agent.router в main.py | ✅ | |
| D-15 | GET /agent → 200, чат рендерится | ✅ | |
| D-16 | POST /agent/send при отключённом Hermes — не падает | ✅ | 200, graceful degradation |
| D-17 | Функциональность не сломана | ✅ | 8 страниц → 200, gate 0→1 → 422 |
| D-18 | init_db создаёт agent_messages | ✅ | Таблица существует в БД |

**Итог:** 18/18 PASS.

---

## Runtime-верификация

| Проверка | Результат |
|---|---|
| `GET /agent` | ✅ 200, чат с историей + composer + quick actions |
| `POST /agent/send` (Hermes offline) | ✅ 200, graceful degradation, оба сообщения сохранены |
| `POST /agent/clear` | ✅ 200, история очищена, empty state показан |
| Sidebar: «Задачи» (не «Таски») | ✅ |
| Sidebar: «Чат с агентом» → /agent | ✅ |
| Quick actions: 3 кнопки | ✅ Найти клиентов, Мои задачи, Создать задачу |
| Visual Canon: bg-ink, rounded-2xl, text-ink, text-muted | ✅ |
| No font-bold | ✅ |
| `/` `/kanban` `/leads/1` `/tasks` `/deals` `/templates` `/reports` | ✅ все 200 |
| Gate 0→1 без менеджера → 422 | ✅ |
| agent_messages table in DB | ✅ |

---

## Архитектурные замечания

1. **hermes_service.py** — чистая реализация. httpx.AsyncClient с timeout из настроек. 4 уровня graceful degradation: disabled → connect → timeout → generic. Все возвращают структурированный dict с reply/actions/error.

2. **AgentMessage** — отдельная таблица для истории чата. `context_lead_id` (nullable FK) — позволяет привязывать диалог к конкретному лиду (для будущего контекстного чата из карточки лида). `actions` (JSON-строка) — если Hermes вернёт действия (поиск, создание задачи), они сохранятся.

3. **POST /agent/clear** — использует `delete()` ORM-запрос, не загружает сообщения в память. Правильно для потенциально большой истории.

4. **Quick actions** — кнопки предзаполняют input через JS (`onclick="document.getElementById('message-input').value='...'"`). Простой подход без отдельного JS-файла. При отправке пользователь видит предзаполненный текст и может отредактировать перед отправкой.

5. **AI Dock канон** — UI соответствует §8 VISUAL_CANON: header → history → composer. Нет отдельной левой колонки signals (пока не нужно — signals будут когда Hermes начнёт возвращать actions). Composer внизу, primary-кнопка «Отправить» — единственная на странице.

---

## Что дальше — деплой (блок техлида)

1. **Docker-файлы:** .env, Dockerfile, docker-compose.yml, .dockerignore
2. **Git:** init, first commit
3. **Деплой:** ssh rai-dev → git clone → docker compose up -d --build
4. **Данные:** копирование xlsx на сервер, импорт через `docker compose exec`
5. **Тест:** http://161.35.89.51:8000 — CRM доступна извне
6. **Hermes:** когда gateway поднят на 8080 — тест интеграции вживую
