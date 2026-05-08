"""
Тестовые данные: дерево категорий кофе и чая.
Товары и SKU НЕ создаём — они добавляются через API (это контракты US-B2B-01/02).
"""

from sqlalchemy.orm import Session

from src.models.category import Category


def seed_database(db: Session) -> None:
    """Создаёт категории, если БД пустая."""
    if db.query(Category).first() is not None:
        return

    print("🌱 Создаём категории кофе и чая...")

    # Корень
    root = Category(name="Напитки")
    db.add(root)
    db.flush()

    # Кофе
    coffee = Category(name="Кофе", parent_id=root.id)
    tea = Category(name="Чай", parent_id=root.id)
    db.add_all([coffee, tea])
    db.flush()

    # Подкатегории кофе
    db.add_all([
        Category(name="Моносорта", parent_id=coffee.id),
        Category(name="Смеси", parent_id=coffee.id),
        Category(name="Декаф", parent_id=coffee.id),
    ])

    # Подкатегории чая
    db.add_all([
        Category(name="Зелёный чай", parent_id=tea.id),
        Category(name="Чёрный чай", parent_id=tea.id),
        Category(name="Травяной чай", parent_id=tea.id),
    ])

    db.commit()
    print("✅ Категории созданы!")
