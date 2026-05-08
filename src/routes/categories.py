"""
Эндпоинт категорий — дерево для выбора при создании товара.
GET /api/v1/categories — дерево категорий (публичный)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.category import Category

router = APIRouter(prefix="/api/v1/categories", tags=["Categories"])


def _build_tree(categories: list, parent_id=None) -> list[dict]:
    """Рекурсивно строит дерево из плоского списка."""
    return [
        {
            "id": str(cat.id),
            "name": cat.name,
            "parent_id": str(cat.parent_id) if cat.parent_id else None,
            "children": _build_tree(categories, cat.id),
        }
        for cat in categories
        if cat.parent_id == parent_id
    ]


@router.get("")
def get_category_tree(db: Session = Depends(get_db)):
    """Дерево категорий (все уровни)."""
    categories = db.query(Category).all()
    return _build_tree(categories, parent_id=None)
