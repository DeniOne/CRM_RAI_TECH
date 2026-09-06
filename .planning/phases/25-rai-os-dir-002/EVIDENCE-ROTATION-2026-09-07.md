# EVIDENCE — Ротация прод-админа по RAI-OS-DIR-002 (2026-09-07)

**Директива:** RAI-OS-DIR-002 (P0), approved Denis 2026-09-07.
**Исполнитель:** ZCode (Tech Lead). **Сервер:** rai-dev, `/srv/crm-rai`.
**Секретов в этом файле нет — только booleans, counts и процедуры.**

## 1. Исходное состояние (находка OS-сверки RAI-OS-DECISION-CRM-001)

- `SECRET_KEY` прод-`.env` переопределён: true.
- `ADMIN_PASSWORD` прод-`.env` переопределён: false.
- Пользователей в прод-БД: 6; на дефолтном пароле `admin`: 1 (role=admin,
  is_active=1).

## 2. Процедура ротации (исполнена на сервере)

1. Online WAL-safe бэкап БД ДО мутации: `sqlite3.Connection.backup()` из
   контейнера → `storage/crm.db.bak.20260907-dir002` (в volume, переживает
   пересборку).
2. Пароль сгенерирован на сервере: `openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 28`
   (28 символов A-Za-z0-9, ≈166 бит энтропии); plaintext НЕ покидал сервер
   (не выводился, не попадал в git/транскрипт).
3. Все пользователи, чей хэш верифицируется против `admin`
   (`app.auth.verify_password("admin", hash)` — тот же код, что в проде),
   ротированы на новый пароль (`app.auth.hash_password`, pbkdf2_hmac 100k) —
   UPDATE напрямую в SQLite, одиночная транзакция.
4. Plaintext нового пароля сохранён на сервере: `/root/crm-admin-rotation-2026-09-07.txt`,
   режим 0600, владелец root. **Владельцу выдать доступ к файлу по SSH.**

## 3. Результаты (boolean re-check, повторно после UPDATE)

| Показатель | Значение |
|---|---|
| users_total | 6 |
| users_on_default_password_before | 1 (admin, active) |
| rotated | 1 |
| recheck_users_on_default_password | **0** |
| backup | `storage/crm.db.bak.20260907-dir002` создан до мутации |
| secret storage | `/root/crm-admin-rotation-2026-09-07.txt` (0600, root) |

Ротированные учётки используют один сгенерированный пароль (P0-сдерживание);
рекомендация владельцу: при первом входе задать индивидуальные пароли через
админ-UI (фазовый долг UI смены пароля — вне DIR-002).

## 4. Конфигурация профиля (тот же деплой)

- Прод-`.env` дополнен: `CRM_ENV=prod`, `ADMIN_PASSWORD=<сгенерирован на сервере>`
  (бутстрап-пароль, инертен при существующих пользователях; силён, чтобы
  fail-fast проходил и future-реинициализация не поднимала дефолт).
- Код fail-fast: `app/config.py` `_enforce_profile()` — CRM_ENV=prod падает на
  dev-дефолтах/пустых SECRET_KEY/ADMIN_PASSWORD; опечатка CRM_ENV — отказ старта.
- Локальные тесты: 3 негативных (dev-дефолты / опечатка / пустой ключ) — RuntimeError;
  2 позитивных (prod+сильные / dev по умолчанию) — OK; регрессионные гейты фаз
  (verify.py, kanban/filters/contact_edit/htmx) — без изменений от базовой линии.

## 5. Пост-деплой проверка (после `git pull` + `up -d --build`)

Заполняется после деплоя — см. README-CONTRACT-PHASE-25.md (T-07).
