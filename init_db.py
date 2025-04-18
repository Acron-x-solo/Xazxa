from app import app
from models import db, User, Post, BotSettings

def init_db():
    with app.app_context():
        # Удаляем все таблицы
        db.drop_all()
        # Создаем все таблицы заново
        db.create_all()
        
        # Создаем тестового пользователя
        user = User(
            username='test',
            email='test@example.com',
            password_hash='test'
        )
        db.session.add(user)
        db.session.commit()
        
        # Создаем настройки бота для тестового пользователя
        bot_settings = BotSettings(
            user_id=user.id,
            is_active=True,
            personality='friendly'
        )
        db.session.add(bot_settings)
        db.session.commit()
        
        # Создаем тестовый пост
        post = Post(
            title='Test Post',
            content='This is a test post',
            user_id=user.id
        )
        db.session.add(post)
        db.session.commit()
        
        print("База данных успешно инициализирована!")

if __name__ == '__main__':
    init_db() 