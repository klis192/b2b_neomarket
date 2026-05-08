"""
Кастомные обработчики ошибок.
Спека требует формат {"code": "...", "message": "..."} на верхнем уровне.
FastAPI по умолчанию оборачивает в {"detail": ...} — исправляем.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует кастомные обработчики ошибок в приложении."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """
        HTTPException → {"code": "...", "message": "..."}.
        Если detail — dict с code/message, выносим на верхний уровень.
        Если detail — строка, оборачиваем в стандартный формат.
        """
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            # Наш формат: {"code": "...", "message": "..."}
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
            )
        else:
            # Строка или другой формат — оборачиваем
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "code": "ERROR",
                    "message": str(exc.detail),
                },
            )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """
        Pydantic ValidationError → 400 {"code": "INVALID_REQUEST", "message": "..."}.
        Спека требует 400 вместо дефолтного 422.
        """
        # Собираем читаемое описание первой ошибки
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = " → ".join(str(l) for l in first.get("loc", []))
            msg = first.get("msg", "Validation error")
            message = f"{loc}: {msg}" if loc else msg
        else:
            message = "Invalid request data"

        return JSONResponse(
            status_code=400,
            content={
                "code": "INVALID_REQUEST",
                "message": message,
            },
        )
