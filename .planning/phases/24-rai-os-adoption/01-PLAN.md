---
phase: 24
plan: 1
slice: rai-os-adoption
wave: 1
depends_on: [23]
directive: RAI-OS-DIR-001
files_created:
  - .rai-os/module.yaml
  - .rai-os/policy-lock.yaml
  - .rai-os/directives/RAI-OS-DIR-001.yaml
  - .rai-os/changes/CRM-RAI-OS-CHANGE-001-tenancy.yaml
  - .rai-os/changes/CRM-RAI-OS-CHANGE-002-object-authorization.yaml
  - .rai-os/changes/CRM-RAI-OS-CHANGE-003-integration-api-mcp.yaml
  - .rai-os/changes/CRM-RAI-OS-CHANGE-004-migrations.yaml
  - .rai-os/changes/CRM-RAI-OS-CHANGE-005-outbox-events.yaml
  - .rai-os/changes/CRM-RAI-OS-CHANGE-006-dev-prod-separation.yaml
  - .rai-os/waivers/RAI-OS-WAIVER-001-mcp-direct-rw.yaml
  - .rai-os/waivers/RAI-OS-WAIVER-002-dev-prod-config.yaml
  - .rai-os/changes/.gitkeep
  - .rai-os/waivers/.gitkeep
  - .rai-os/evidence/.gitkeep
  - scripts/rai_os_validate.py
  - AGENTS.md
  - .planning/phases/24-rai-os-adoption/01-PLAN.md
  - .planning/phases/24-rai-os-adoption/README-CONTRACT-PHASE-24.md
files_modified: []
must_haves:
  truths:
    - "T-01: .rai-os/module.yaml валиден по module.schema.json из RAI_OS/protocol; role=domain-module, lifecycle=donor-and-standalone, id=crm-rai (совпадает с registry RAI OS); зафиксированы текущие факты: локальная cookie-auth, single-tenant, SQLite, MCP с прямым доступом к БД; прямые записи MCP НЕ объявлены контрактом OS"
    - "T-02: .rai-os/policy-lock.yaml валиден по policy-lock.schema.json; enforcement=declared; ни одна политика не заявлена adopted/enforced без доказательств; exceptions=[] (waivers только proposed, одобрение Владельца ожидается)"
    - "T-03: Директива RAI-OS-DIR-001 отражена в .rai-os/directives/RAI-OS-DIR-001.yaml (status=acknowledged) со ссылкой на этот PLAN"
    - "T-04: Шесть пробелов зафиксированы proposed change-записями P1 (tenancy, объектная авторизация, стабильный integration API/MCP, миграции, outbox/events, dev/prod); два proposed waiver (MCP direct RW через stdio; dev/prod конфигурация) — runtime в этой фазе НЕ правится"
    - "T-05: Локальная команда валидации `python scripts/rai_os_validate.py` зелёная: валидация схем (module, policy-lock, change, waiver) + перекрёстные проверки (module_id согласован, policy_lock путь существует, evidence-пути существуют, waiver-статусы согласованы); CI в репо отсутствует — подключение отложено до его появления"
    - "T-06: Поведение runtime не изменено: app/, mcp_server.py, requirements.txt, Dockerfile, docker-compose.yml, миграции при старте, данные, /srv/crm-rai — без изменений; git diff вне .planning/.rai-os/scripts(новый файл)/AGENTS.md пуст"
    - "T-07: AGENTS.md в корне репо обязателен к исполнению агентами: классификация OS-impact ДО написания/исполнения PLAN (governance §6), проверка открытых changes/directives/waivers"
  os_impact: |
    Сама фаза — governance-only: .rai-os/ декларации + локальный валидатор + инструкции агента.
    Ни одного изменения общей границы (API/события/схема/владение) не производится;
    все известные границы зафиксированы как proposed changes/waivers.
context: |
  Директива RAI-OS-DIR-001 (APPROVED 2026-09-06, P1) предписывает внедрить RAI OS
  Governance Protocol v1.0.0 без изменения поведения среды исполнения. CRM RAI —
  второй модуль после RAI MI. Канон: CRM RAI — донор проверенных процессов продаж,
  целевой домен CRM/Commerce; текущие монолит, БД, auth и MCP НЕ являются целевой
  системной границей. Схемы/шаблоны — только из F:/RAI_ALL_OS/protocol/.
details:
  - "Владение (по канону): только sales-domain состояние (лид/сделка/КП/активность); каноническая Party-идентичность — must_not_own (владелец rai-ep Party Registry)"
  - "Факты для паспорта взяты из кода: app/auth.py (cookie-сессии itsdangerous + pbkdf2), app/config.py (single .env, dev-дефолты SECRET_KEY/ADMIN_PASSWORD), app/database.py (SQLite, create_all + идемпотентные ALTER при старте), mcp_server.py (16 инструментов, RO-поиски, RW-мутации без auth, изоляция конфигурацией Hermes), деплой docker host-network на rai-dev"
  - "Валидатор без новых зависимостей: stdlib + PyYAML (уже в venv); mini-движок подмножества JSON Schema, достаточного для схем протокола"
  - "Коммит фазы — только файлы внедрения протокола и свидетельства планирования (шаг 11 директивы)"
