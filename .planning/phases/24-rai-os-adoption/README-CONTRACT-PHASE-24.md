# README-CONTRACT — Phase 24: Внедрение RAI OS Governance Protocol (директива RAI-OS-DIR-001)

**Phase:** 24 — rai-os-adoption (governance-only, PLAN согласован структурой директивы)
**Verdict:** ✅ PASS
**Author (Tech Lead):** ZCode
**Date:** 2026-09-06
**Gate:** `python scripts/rai_os_validate.py` (схемы + перекрёстные проверки) + локальные
гейты проекта (verify.py, test_*) + подтверждение нулевого diff по runtime.

---

## Что сделано

Внедрён RAI OS Governance Protocol v1.0.0 по разделу «CRM RAI» директивы
RAI-OS-DIR-001: декларации и управление, **без изменения поведения среды исполнения**.

1. **PLAN**: `.planning/phases/24-rai-os-adoption/01-PLAN.md` (7 T-критериев).
2. **Паспорт модуля** `.rai-os/module.yaml` (валиден по `module.schema.json`):
   role=`domain-module`, lifecycle=`donor-and-standalone`, id=`crm-rai` (совпадает
   с registry RAI OS). Зафиксированы как факты: локальная cookie-auth
   (itsdangerous+pbkdf2), однотенантная среда, SQLite, MCP с прямым доступом к БД.
   Прямые записи MCP объявлены фактическим внутренним интерфейсом и **не** контрактом
   OS (`contracts.provides` + CHANGE-003). Владение: только sales-domain состояние
   (лид/сделка/КП/активность); каноническая Party-идентичность — `must_not_own`.
3. **Фиксация политик** `.rai-os/policy-lock.yaml` (валиден по
   `policy-lock.schema.json`): `enforcement: declared`; политики canon/governance/
   architecture/data_ownership — `declared` (признаны, не внедрены в код),
   security/contracts/design/ai/delivery — `partial` (частичные локальные
   доказательства). `exceptions: []` — waivers ещё proposed, одобрения Владельца нет.
4. **Директива принята**: `.rai-os/directives/RAI-OS-DIR-001.yaml` (acknowledged,
   plan_ref → PLAN фазы 24).
5. **Инвентаризация пробелов** — 6 proposed change-записей P1 и 2 proposed waiver:
   | ID | Пробел | Приоритет |
   |---|---|---|
   | CRM-RAI-OS-CHANGE-001 | tenancy: нет модели/контекста тенанта | P1 |
   | CRM-RAI-OS-CHANGE-002 | объектная авторизация неполна (мутации лида — только сессия) | P1 |
   | CRM-RAI-OS-CHANGE-003 | нет стабильного integration API; MCP RW напрямую в SQLite, минуя auth/доменные сервисы | P1 |
   | CRM-RAI-OS-CHANGE-004 | схема меняется при старте (create_all+ALTER), версионируемых миграций нет | P1 |
   | CRM-RAI-OS-CHANGE-005 | нет outbox/событий (блокирует целевую интеграцию OS) | P1 |
   | CRM-RAI-OS-CHANGE-006 | нет разделения dev/prod (единый .env, dev-дефолты SECRET_KEY/ADMIN_PASSWORD) | P1 |
   | RAI-OS-WAIVER-001 | MCP direct RW через stdio (действующее состояние до целевого API) | P1 proposed |
   | RAI-OS-WAIVER-002 | dev/prod конфигурация без fail-fast на дефолтных секретах | P1 proposed |
6. **Локальная команда валидации**: `python scripts/rai_os_validate.py` — схемы из
   `RAI_OS/protocol/schemas/` (мини-движок подмножества JSON Schema, без новых
   зависимостей: stdlib + PyYAML) + перекрёстные проверки (module_id, policy_lock
   путь, evidence-пути, согласованность waiver-статусов с policy-lock.exceptions,
   plan_ref директив). CI в репо отсутствует — подключение отложено до его
   появления (зафиксировано в module.governance.validation_command).
7. **Инструкции агентов**: `AGENTS.md` в корне — классификация OS-impact ДО
   написания/исполнения PLAN обязательна (governance §6), границы владения,
   известные пробелы «не чинить мимоходом».

## Gate-результаты

- `scripts/rai_os_validate.py`: **PASS, 11/11 артефактов** (2 манифеста + 6 changes +
  2 waivers по схемам; directive-ack по структурной проверке — схемы протокола для
  ack не содержат; перекрёстные проверки чистые).
- `scripts/verify.py`: exit 0; TestClient: login 303 → дашборд 200, в локальной БД
  591 лид. Честная оговорка: regex-проверки verify.py (`text-blue-600`, счёт строк
  `<tr class="border-t">`) устарели относительно шаблонов фазы 5+ — выводят 0; это
  **предсуществующее** состояние eval-скрипта, вне зоны фазы 24 (не правил).
- `scripts/test_kanban.py`, `test_filters.py` (200, 92 карточки), `test_delete.py`,
  `test_contact_edit.py`, `test_htmx.py`, `test_htmx2.py`: все exit 0
  (test_dashboard.py требует `PYTHONPATH=.` — тоже предсуществующее).
- **Runtime не изменён**: `git status` — правки только в `.planning/`, `.rai-os/`,
  `AGENTS.md`, `scripts/rai_os_validate.py` (новый файл); `app/`, `mcp_server.py`,
  `requirements.txt`, `Dockerfile`, `docker-compose.yml`, данные — не тронуты.

## Долги (по правилу PARTIAL — здесь фаза PASS, долги вне фазы, перечислены для трассируемости)

| Долг | Почему открыт | Когда закроется | Блокирует? |
|---|---|---|---|
| Waivers 001/002 не утверждены | Только Владелец утверждает P0/P1-исключения (governance §4) | Решение Denis по результатам OS-сверки; до этого — proposed, в policy-lock.exceptions не внесены | НЕТ — внедрение протокола принято директивой; утверждение управляет сроком устранения |
| Пробелы CHANGE-001..006 | Директива запрещает править runtime в коммите внедрения | Отдельные фазы по каждому (PLAN обязателен, OS-impact классификация уже действует) | Блокируют целевую интеграцию с rai-ep/rai-mi, НЕ блокируют разработку standalone-CRM |
| Подключение валидатора к CI | CI в репо отсутствует | С появлением CI (долг доставки, CHANGE-006 смежно) | НЕТ |
| Сверка RAI OS (шаг 12 директивы) | Первый снимок собирает RAI OS Architect | Следующая сессия RAI OS | НЕТ (внешний контур) |
