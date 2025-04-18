from app import app, db
from models import User

def make_admin(username):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if user:
            user.is_admin = True
            db.session.commit()
            print(f"Пользователь {username} теперь администратор!")
        else:
            print(f"Пользователь {username} не найден.")

if __name__ == "__main__":
    username = input("Введите имя пользователя для назначения администратором: ")
    make_admin(username) 