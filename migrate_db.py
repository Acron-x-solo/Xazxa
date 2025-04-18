from app import app, db
from models import User, Post, Comment, Like, Follow, Friendship, PrivateMessage

def migrate_database():
    with app.app_context():
        # Удаляем все таблицы
        db.drop_all()
        # Создаем таблицы заново
        db.create_all()
        print("База данных успешно мигрирована!")

if __name__ == '__main__':
    migrate_database() 