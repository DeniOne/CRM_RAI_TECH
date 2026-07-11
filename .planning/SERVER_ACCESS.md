# Инструкция подключения к серверу CRM_RAI

## Сервер

- **IP:** 161.35.89.51
- **SSH алиас:** `rai-dev` или `rai-server`
- **Пользователь:** root
- **SSH ключ:** `C:\Users\DeniOne\.ssh\id_ed25519_cloud`
- **Конфиг:** `~/.ssh/config` (Host rai-dev)

## Подключение

```bash
ssh rai-dev
```

## Рабочая директория

```
/srv/crm-rai/
```

**НЕ** `/srv/rai/dev/RAI_EP/` — это другой проект!

## Структура проекта на сервере

```
/srv/crm-rai/
├── app/                    # Код приложения
├── storage/                # БД + документы (volume в Docker)
├── templates_docx/         # Шаблоны документов
├── scripts/                # Скрипты
├── .planning/              # PLAN-файлы техлида
├── .env                    # Конфигурация
├── docker-compose.yml      # Docker Compose
├── Dockerfile              # Docker образ
├── requirements.txt        # Python зависимости
├── run.py                  # Точка входа
├── mcp_server.py           # MCP-сервер для Hermes
├── Екатерина.xlsx          # Данные (только чтение)
└── _Вероника.xlsx          # Данные (только чтение)
```

## Docker

### Контейнер
- **Имя:** `crm-rai-dev`
- **Порт:** `8000` (host network mode)
- **Доступ:** http://161.35.89.51:8000

### Команды

```bash
# Статус контейнера
docker ps | grep crm-rai

# Логи
docker logs crm-rai-dev --tail 50

# Перезапуск
docker restart crm-rai-dev

# Войти в контейнер
docker exec -it crm-rai-dev bash

# Остановить
docker stop crm-rai-dev

# Пересобрать и запустить
cd /srv/crm-rai && docker compose up -d --build
```

## Git

```bash
cd /srv/crm-rai

# Статус
git status

# Лог
git log --oneline -10

# Pull обновлений
git pull origin master

# После pull — пересобрать контейнер
docker compose up -d --build
```

## База данных

- **Тип:** SQLite
- **Путь в контейнере:** `/app/storage/crm.db`
- **Путь на хосте:** `/srv/crm-rai/storage/crm.db`

```bash
# Проверить БД
sqlite3 /srv/crm-rai/storage/crm.db "SELECT COUNT(*) FROM leads;"

# Импорт данных (из контейнера)
docker exec -it crm-rai-dev python scripts/import_xlsx.py
```

## Конфигурация (.env)

```bash
cat /srv/crm-rai/.env
```

Основные переменные:
- `DATABASE_URL` — строка подключения к БД
- `SECRET_KEY` — ключ сессий
- `HERMES_API_URL` — URL Hermes агента
- `HERMES_ENABLED` — включить/выключить агента

## Hermes MCP Server

```bash
# MCP-сервер для интеграции с Hermes
cat /srv/crm-rai/mcp_server.py
```

## Развёртывание с нуля

```bash
# 1. Клонировать репозиторий
cd /srv
git clone <repo-url> crm-rai
cd crm-rai

# 2. Создать .env
cp .env.example .env
# Отредактировать .env

# 3. Собрать и запустить
docker compose up -d --build

# 4. Импортировать данные
docker exec -it crm-rai-dev python scripts/import_xlsx.py

# 5. Проверить
curl http://localhost:8000/docs
```

## Типичные операции

### Обновить код на сервере
```bash
ssh rai-dev
cd /srv/crm-rai
git pull origin master
docker compose up -d --build
```

### Посмотреть логи
```bash
ssh rai-dev "docker logs crm-rai-dev --tail 100"
```

### Перезапустить после изменения .env
```bash
ssh rai-dev "cd /srv/crm-rai && docker compose restart crm"
```

### Проверить доступность
```bash
curl -s -o /dev/null -w '%{http_code}' http://161.35.89.51:8000/
```

## Важно

- Работаем ТОЛЬКО с `/srv/crm-rai/`
- `/srv/rai/` — это проект RAI_EP, не трогаем
- `storage/` монтируется как volume — данные сохраняются между пересборками
- `Екатерина.xlsx` и `_Вероника.xlsx` — исходные данные, не удаляем
- `.planning/` — архив PLAN-файлов, не трогаем
