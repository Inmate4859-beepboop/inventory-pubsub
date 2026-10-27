# Склад с pub/sub

- **`inventory_api`** — HTTP API на aiohttp: принимает приходы и расходы, пишет их в `stock_events`, после коммита публикует событие в Redis, считает остатки и сводку.
- **`analytics_worker`** — подписчик Redis Pub/Sub: на каждое событие обновляет остаток пары `(warehouse, sku)` в `stock_agg`.

PostgreSQL, SQLAlchemy 2 Core поверх asyncpg, Alembic.

## Запуск

Нужны Python 3.10+ и Docker.

```bash
docker compose up -d                 # Postgres на localhost:5433, Redis на localhost:6379
python -m venv .venv
source .venv/bin/activate            # Windows: source .venv/Scripts/activate (Git Bash) или .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head                 # миграции
python -m inventory_api              # http://localhost:8080
python -m analytics_worker           # в отдельном терминале
```

Настройки — переменные окружения или `.env` (см. `.env.example`). Дефолты совпадают с `docker-compose.yml`.

## API

| Метод | Описание |
|---|---|
| `POST /receipts` | приход: `{"sku": "A-100", "qty": 50, "warehouse": "WH-1"}` → `201` |
| `POST /issues` | расход, тело то же → `201`, при нехватке остатка `409` |
| `GET /stock?warehouse=WH-1&sku=A-100` | остатки склада, `sku` опционален |
| `GET /stock/summary?top_n=5` | по складам `total_qty` и `sku_count` (SKU с остатком > 0), плюс топ-N SKU по всем складам |

Невалидный вход → `400` с описанием ошибок.

```bash
curl -X POST localhost:8080/receipts -H 'Content-Type: application/json' -d '{"sku":"A-100","qty":50,"warehouse":"WH-1"}'
curl "localhost:8080/stock?warehouse=WH-1"
curl "localhost:8080/stock/summary?top_n=3"
```

## Тесты

```bash
pytest -v
```

Нужен запущенный `docker compose`: тесты работают с реальной БД `inventory_test` (её создаёт init-скрипт). Redis в тестах API заменён заглушкой, воркер тестируется прямым вызовом `handle_message`.

## Решения и ограничения

- **Источник истины — `stock_events`.** Остатки, summary и проверка при расходе считаются из журнала. `stock_agg` обновляется асинхронно и может отставать, поэтому API его не читает.
- **Гонка при расходе** закрыта: проверка остатка и вставка идут в одной транзакции под `pg_advisory_xact_lock` по паре `(warehouse, sku)`.
- **Pub/Sub — at-most-once.** Пока воркер не запущен, события теряются, и `stock_agg` расходится с журналом. Пересобрать его можно из `stock_events` (`GROUP BY warehouse, sku`) при остановленном воркере.
- **COMMIT и PUBLISH не атомарны.** Если Redis недоступен после коммита, операция сохранена, а событие потеряно (API отвечает `201` и пишет ошибку в лог). Решение — Transactional Outbox.
- **Направление дальнейшей работы:** Redis Streams с consumer group и `XACK` (повторная доставка, несколько воркеров без дублей) плюс идемпотентность по `event_id`.
