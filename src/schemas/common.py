"""Общие Pydantic-схемы: ошибки, стандартные ответы."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Стандартный формат ошибки для всего API."""
    code: str
    message: str


class OkResponse(BaseModel):
    """Простой ответ об успехе."""
    ok: bool = True
