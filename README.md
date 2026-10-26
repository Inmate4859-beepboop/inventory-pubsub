# Склад с pub/sub

Два асинхронных сервиса: `inventory_api` (HTTP API на aiohttp) и `analytics_worker` (подписчик Redis Pub/Sub). Хранилище — PostgreSQL.

## Быстрый старт

Требования: Python 3.10+, Docker с Compose.

1. Поднять Postgres и Redis:

   ```bash
   docker compose up -d
   docker compose ps   # оба сервиса healthy
   ```

   Postgres доступен на `localhost:5433`, Redis — на `localhost:6379`.
   Рядом с основной БД `inventory` автоматически создаётся тестовая `inventory_test`.

2. Создать виртуальное окружение и поставить зависимости:

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows, Git Bash: source .venv/Scripts/activate
                                    # Windows, PowerShell: .venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```

3. (Опционально) Переопределить настройки:

   ```bash
   cp .env.example .env
   ```

   Без `.env` используются дефолты из `common/config.py`, они совпадают с `docker-compose.yml`.
