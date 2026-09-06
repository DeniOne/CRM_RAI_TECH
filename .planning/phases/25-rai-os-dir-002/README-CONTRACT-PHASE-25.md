# README-CONTRACT — Phase 25: Sync по RAI-OS-DECISION-CRM-001 + исполнение RAI-OS-DIR-002 (P0)

**Phase:** 25 — rai-os-dir-002 (вне очереди, по решению OS от 2026-09-07)
**Verdict:** ✅ PASS
**Author (Tech Lead):** ZCode
**Date:** 2026-09-07
**Gate:** rai_os_validate.py (PASS 12/13 артефактов после фазы) + локальные тесты
fail-fast (3 негативных / 2 позитивных) + регрессионные гейты + серверные
boolean re-checks + e2e-проверка логина на проде.

---

## Что сделано (все 4 пункта follow-up OS-решения §4)

1. **Пуш**: `bad81fd` → origin/master (первым шагом; далее `0067447`, `bd1e2f2` + этот коммит).
2. **Waiver-синк** по RAI-OS-DECISION-CRM-001: W1 `proposed→active`
   (approved_by: Denis; компенсирующие меры дополнены DRIFT-CRM-001 и запретом
   новых мутационных MCP-инструментов); W2 `proposed→approved`, затем
   `→active` после свидетельства ротации; `policy-lock.exceptions =
   [RAI-OS-WAIVER-001, RAI-OS-WAIVER-002]`. Правило валидатора уточнено:
   в exceptions вносятся только `active`-waivers (approved-без-активации —
   легальный промежуточный статус по решению OS).
3. **Мост :8100 объявлен** (DRIFT-CRM-001 закрыт как декларация): `run_mcp_http.py`
   — серверный streamable-http поверх того же `mcp_server.py`, 0.0.0.0:8100,
   ufw только docker-подсеть 172.23.0.0/16 (потребитель rai-ep dev api),
   `allowed_hosts=['*']` → контроль экспозиции фактически только ufw. Заявлен в
   `module.yaml` (contracts.provides, platform.ai_control_plane) и CHANGE-003.
   Экспозиция и код моста не менялись.
4. **RAI-OS-DIR-002 (P0) исполнен**:
   - **Ротация**: онлайн-бэкап (`crm.db.bak.20260907-dir002`) → единственный
     пользователь на дефолтном пароле (активный админ, подтверждение находки OS)
     ротирован на сгенерированный на сервере пароль (28 симв. A-Za-z0-9);
     plaintext только в `/root/crm-admin-rotation-2026-09-07.txt` (0600).
   - **Fail-fast + профили**: `app/config.py` — `CRM_ENV=dev|prod` (guard на
     опечатку значения); в `prod` — RuntimeError на import при dev-дефолтных или
     пустых `SECRET_KEY`/`ADMIN_PASSWORD`. Локально: 3 негативных теста падают с
     точным сообщением, 2 позитивных грузятся; регрессионные гейты (verify,
     kanban, filters, contact_edit, htmx) идентичны базовой линии фазы 24 —
     dev-поведение не изменилось.
   - **Прод-деплой**: `.env` += `CRM_ENV=prod` + сгенерированный `ADMIN_PASSWORD`
     (файл 0600), pull, rebuild. Контейнер Up, startup complete (fail-fast
     пройден), https://raitechnology.online/login → 200.
   - **Верификация** (booleans + e2e): `SECRET_KEY_overridden=true`,
     `ADMIN_PASSWORD_overridden=true`, `CRM_ENV=prod`,
     `users_on_default_password=0` (до и после деплоя), логин `admin`/`admin` —
     HTTP 200 (отклонён), логин новым паролем — HTTP 303 → `/` (успех, секрет не
     покидал сервер). DIR-002 ack → **satisfied** с evidence.

## Побочные находки фазы (зафиксированы, runtime не менялся)

1. **CRM-RAI-OS-CHANGE-007** (новый, P1 proposed): крон rai-ep ежечасно читает
   `crm.db` напрямую (`mode=ro`, upsert в свою postgres по ИНН) — незаявленная
   прямая DB-интеграция. Не P0 (read-only, без утечки/мутаций/секретов).
   Декларирована со стороны CRM; сторона rai-ep — внешний контур OS.
2. **Неопознанный git-pull актор** на сервере: reflog фиксирует pull до bad81fd и
   bd1e2f2 в минуты после пушей, не из моих сессий; poller/таймеры/вебхуки не
   найдены. Контейнер при этом не перезапускался. Рекомендация OS: идентифицировать
   актора — деплой-канал должен быть явным (delivery-гигиена, вне этой фазы).

## Долги

| Долг | Почему | Когда | Блокирует? |
|---|---|---|---|
| Декларация EP-синка со стороны rai-ep | Владелец границы — rai-ep (CHANGE-007 зафиксировал CRM-сторону) | Следующая сверка OS / фаза EP | НЕТ (read-only, идемпотентно) |
| Идентификация pull-актора на сервере | Не найден штатными средствами; риск «pull без rebuild» низкий, но канал неявный | OS/Denis (рекомендация в evidence §6.2) | НЕТ |
| W2 → remediated, CHANGE-006 → closed | Закрытие требует OS-сверки (governance §5.9) | Следующая сверка OS | НЕТ — exit-критерии объективно выполнены |
| Индивидуальные пароли ротированных учёток | P0-сдерживание одним сгенерированным паролем; UI смены пароля отсутствует | Отдельная мини-фаза (бэклог) | НЕТ |
| Подключение rai_os_validate.py к CI | CI в репо по-прежнему нет | С появлением CI | НЕТ |

## Изменённые файлы

`app/config.py` (единственный runtime-файл: +профиль/fail-fast, семантика dev
не изменилась), `docs/CRM_RAI_TECH.md` (§10: CRM_ENV; §профиль среды),
`AGENTS.md` (+правило профиля), `.rai-os/*` (waivers, policy-lock, CHANGE-003/006/007,
module.yaml, directives/RAI-OS-DIR-002), `.planning/phases/25-rai-os-dir-002/*`,
`scripts/rai_os_validate.py` (уточнение cross-check правила). Секреты, плейнтекст
пароля, прод-payload в git не попадали.
