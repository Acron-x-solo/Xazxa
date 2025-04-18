import os
import sys
from pathlib import Path

# Получаем абсолютный путь к текущей директории
current_dir = Path(__file__).parent.absolute()
db_path = current_dir / 'social_network.db'

# Удаляем существующую базу данных
if db_path.exists():
    os.remove(db_path)
    print(f"База данных удалена: {db_path}")

# Импортируем и инициализируем приложение
from app import app, db

# Создаем новую базу данных
with app.app_context():
    db.drop_all()  # Удаляем все таблицы
    db.create_all()  # Создаем таблицы заново
    print("База данных успешно пересоздана!") 