"""
NeoMarket B2B — Кабинет продавца кофе и чая.
Точка входа. Создаёт таблицы и загружает seed при старте.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.database import Base, SessionLocal, engine
from src.exceptions import register_exception_handlers
from src.routes import auth, categories, products, skus
from src.seed import seed_database

# Импортируем модели, чтобы Base.metadata знал все таблицы
import src.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создаём таблицы и seed при старте."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="Кабинет продавца NeoMarket. Кофе и чай.",
    lifespan=lifespan,
)

# Кастомные обработчики ошибок — формат {"code": "...", "message": "..."}
register_exception_handlers(app)

# CORS — для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры
app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(products.router)  # Этап 1: US-B2B-01
app.include_router(skus.router)      # Этап 2: US-B2B-02

# Роутеры для следующих этапов:
# app.include_router(skus.router)        # Этап 2
# app.include_router(invoices.router)    # Этап 6
# app.include_router(reserve.router)     # Этап 8
# app.include_router(events.router)      # Этап 9


@app.get("/health", tags=["System"])
def health_check():
    """Проверка работоспособности сервиса."""
    return {"status": "ok", "service": "b2b"}
