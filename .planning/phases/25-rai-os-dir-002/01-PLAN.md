---
phase: 25
plan: 1
slice: rai-os-dir-002
wave: 1
depends_on: [24]
directives: [RAI-OS-DIR-001, RAI-OS-DIR-002]
decision_ref: "RAI-OS-DECISION-CRM-001 (первая сверка, 2026-09-07): follow-up §4 п.1–4"
files_created:
  - .planning/phases/25-rai-os-dir-002/01-PLAN.md
  - .planning/phases/25-rai-os-dir-002/EVIDENCE-ROTATION-2026-09-07.md
  - .planning/phases/25-rai-os-dir-002/README-CONTRACT-PHASE-25.md
  - .rai-os/directives/RAI-OS-DIR-002.yaml
files_modified:
  - .rai-os/waivers/RAI-OS-WAIVER-001-mcp-direct-rw.yaml
  - .rai-os/waivers/RAI-OS-WAIVER-002-dev-prod-config.yaml
  - .rai-os/policy-lock.yaml
  - .rai-os/changes/CRM-RAI-OS-CHANGE-003-integration-api-mcp.yaml
  - .rai-os/changes/CRM-RAI-OS-CHANGE-006-dev-prod-separation.yaml
  - .rai-os/module.yaml
  - app/config.py
  - docs/CRM_RAI_TECH.md
  - AGENTS.md
must_haves:
  truths:
    - "T-01: Коммит bad81fd запушен в origin/master (следовал первым, отдельным шагом; OS-снимок ссылается на этот SHA)"
    - "T-02: Waiver-копии синхронизированы с OS-решением RAI-OS-DECISION-CRM-001: W1 proposed→active (approved_by: Denis, 2026-09-07; компенсирующие меры дополнены DRIFT-CRM-001 :8100 docker-подсеть 172.23.0.0/16 и запретом новых мутационных MCP-инструментов до CHANGE-003); W2 proposed→approved, активация (active + policy-lock.exceptions) — после свидетельства ротации по DIR-002"
    - "T-03: policy-lock.exceptions=[RAI-OS-WAIVER-001] после синхронизации; [RAI-OS-WAIVER-001, RAI-OS-WAIVER-002] — после ротации (validator green, статус-согласованность waivers/exceptions проверяется перекрёстно)"
    - "T-04: Мост :8100 объявлен в module.yaml (contracts.provides + platform.ai_control_plane) и в CHANGE-003: run_mcp_http.py (серверный, streamable-http поверх mcp_server.py, consumer rai-ep dev api, ufw 172.23.0.0/16, allowed_hosts=['*'] — контроль только ufw); DRIFT-CRM-001 закрыт как декларация; экспозиция/код моста не меняются"
    - "T-05: DIR-002 (P0) исполнен: прод-админ(ы) на дефолтном пароле ротированы на сервере; перед мутацией снят online-бэкап БД (.backup); повторный boolean re-check: users_on_default_password=0; новый секрет только в root-only файле на сервере (600), в git/evidence не попадает"
    - "T-06: app/config.py: профиль CRM_ENV (dev|prod; guard на опечатку значения) + fail-fast в prod на dev-дефолтах SECRET_KEY/ADMIN_PASSWORD (RuntimeError на import); локальные негативные/позитивные тесты подтверждают оба пути; dev-поведение не изменилось"
    - "T-07: Прод redeployed: .env += CRM_ENV=prod + сильный ADMIN_PASSWORD (генерирован на сервере), git pull, docker compose up -d --build; контейнер healthy, https://raitechnology.online/login → 200, финальные booleans: SECRET_KEY_overridden=true, ADMIN_PASSWORD_overridden=true, CRM_ENV=prod, users_on_default_password=0"
    - "T-08: DIR-002 ack в .rai-os/directives/RAI-OS-DIR-002.yaml доведён до satisfied с evidence: boolean-recheck-result, changed-files, rotation-procedure-record; CHANGE-006 → implemented (fail-fast + профили), W2 exit-критерии объективно выполнены, закрытие — за OS-сверкой"
  os_impact: |
    Затрагивает границы security/deployment (CHANGE-006, обновляется ДО реализации)
    и integration-поверхность MCP (CHANGE-003 — декларация DRIFT-CRM-001 по решению
    OS). Новых межмодульных контрактов не создаётся (блок DIR-002 соблюдён).
    Код: только app/config.py (+docs/AGENTS); runtime-логика домена не меняется.
context: |
  OS-сверка 2026-09-07 приняла декларацию crm-rai (adopted, rev bad81fd) с
  условиями: sync waivers, объявить drift-мост :8100, исполнить P0-директиву
  DIR-002 (ротация дефолтного прод-админа + fail-fast). Блокировка: до верифицированной
  ротации запрещены фазы CRM, затрагивающие auth/deploy; эта фаза — исполнение
  самой директивы (вне очереди, P0).
details:
  - "Ротация: все пользователи, чей hash верифицируется против 'admin', получают новый сгенерированный на сервере пароль (openssl rand); plaintext только в /root/crm-admin-rotation-2026-09-07.txt (600); в evidence — только booleans и counts"
  - "Бэкап до мутации: sqlite3 '.backup' (online, WAL-safe) в storage/crm.db.bak.20260907-dir002"
  - "Fail-fast: явные env-переменные бьют .env (pydantic) — тесты детерминированы; CRM_ENV≠dev|prod → RuntimeError (опечатка не должна молча отключать защиту)"
  - "Мост :8100 НЕ перезапускается и не открывается шире — только декларация (условие W1)"
  - "Коммиты: A=PLAN+governance sync; B=код DIR-002+W2 active+CHANGE-006 implemented+evidence ротации; C=README-CONTRACT+ack satisfied (после prod-verify)"
