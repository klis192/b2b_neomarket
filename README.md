# NeoMarket B2B — Кабинет продавца

Модуль B2B маркетплейса кофе и чая NeoMarket.  
Продавец управляет товарами, SKU, категориями и накладными.

## Стек

- Python 3.12 + FastAPI
- PostgreSQL 16
- SQLAlchemy 2.0 + Alembic
- PyJWT (HS256)
- Docker Compose

## Запуск

```bash
docker compose up --build
```

| Сервис | URL |
|--------|-----|
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

При первом запуске автоматически создаются таблицы и категории кофе/чая.

## Тесты

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

Тесты используют SQLite in-memory - Docker не требуется.

## Структура

```
src/
├── main.py              # точка входа FastAPI
├── config.py            # настройки из ENV
├── database.py          # подключение к PostgreSQL
├── exceptions.py        # формат ошибок {code, message}
├── seed.py              # тестовые категории
├── auth/                # JWT (register, login, refresh, logout)
├── models/              # ORM-модели
├── schemas/             # Pydantic-схемы
├── routes/              # эндпоинты
└── services/            # бизнес-логика
```

## Команда

Изи 90, синдикат Interface
