from flask import Flask, jsonify, request, render_template, redirect, url_for, flash, send_from_directory, session, make_response, g
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from flask_migrate import Migrate
from flask_mail import Mail, Message
from flask_wtf.csrf import CSRFProtect, generate_csrf
import os
from pathlib import Path
from models import db, User, Post, Comment, Follow, Friendship, PrivateMessage, Like, GameSession, Group, Channel, BotSettings, BotMessage
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta, datetime
from werkzeug.utils import secure_filename
from api import api
import random
import string
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_babel import Babel, gettext as _
from simple_bot import SimpleBot

app = Flask(__name__)
app.config.from_object('config.Config')
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = os.urandom(24)  # Отдельный ключ для CSRF
app.config['WTF_CSRF_TIME_LIMIT'] = None  # Отключаем ограничение по времени для CSRF токена
app.config['WTF_CSRF_SSL_STRICT'] = False  # Отключаем строгую проверку SSL для разработки
app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # Отключаем проверку CSRF для всех маршрутов по умолчанию
app.config['BABEL_DEFAULT_LOCALE'] = 'ru'
app.config['BABEL_SUPPORTED_LOCALES'] = ['ru', 'en', 'az', 'tr']

# Инициализация Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*")

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
login_manager.login_message_category = 'info'

# Инициализация бота
chatbot = SimpleBot()

# Конфигурация загрузки файлов
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Создаем необходимые директории
os.makedirs(os.path.join(UPLOAD_FOLDER, 'videos'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'files'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'images'), exist_ok=True)
os.makedirs(os.path.join(app.root_path, 'static', 'avatars'), exist_ok=True)

app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['ALLOWED_VIDEO_EXTENSIONS'] = {'mp4', 'webm', 'avi', 'mov'}
app.config['ALLOWED_FILE_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'txt', 'zip', 'rar'}

# Создаем папку для загрузки аватаров, если она не существует
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Инициализация Babel
babel = Babel()

def get_locale():
    # Сначала проверяем язык в сессии
    if 'lang' in session:
        return session['lang']
    
    # Затем проверяем язык в URL параметрах
    lang = request.args.get('lang')
    if lang and lang in app.config['BABEL_SUPPORTED_LOCALES']:
        session['lang'] = lang
        return lang
    
    # Затем проверяем язык в заголовках браузера
    browser_lang = request.accept_languages.best_match(app.config['BABEL_SUPPORTED_LOCALES'])
    if browser_lang:
        return browser_lang
    
    # Если ничего не найдено, возвращаем язык по умолчанию
    return app.config['BABEL_DEFAULT_LOCALE']

babel.init_app(app, locale_selector=get_locale)

def get_file_type(filename):
    """Определяет тип файла на основе расширения"""
    if not '.' in filename:
        return None
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in app.config['ALLOWED_IMAGE_EXTENSIONS']:
        return 'image'
    elif ext in app.config['ALLOWED_VIDEO_EXTENSIONS']:
        return 'video'
    elif ext in app.config['ALLOWED_FILE_EXTENSIONS']:
        return 'file'
    return None

def allowed_file(filename, allowed_extensions=None):
    """
    Проверяет допустимость файла.
    Если allowed_extensions не указаны, проверяет по всем разрешенным типам.
    """
    if not '.' in filename:
        return False
    
    ext = filename.rsplit('.', 1)[1].lower()
    if allowed_extensions:
        return ext in allowed_extensions
    
    return (ext in app.config['ALLOWED_IMAGE_EXTENSIONS'] or
            ext in app.config['ALLOWED_VIDEO_EXTENSIONS'] or
            ext in app.config['ALLOWED_FILE_EXTENSIONS'])

# Инициализация расширений
db.init_app(app)
migrate = Migrate(app, db)
mail = Mail(app)

# Словарь для хранения кодов подтверждения и их сроков действия
verification_codes = {}

def generate_verification_code():
    """Генерирует случайный 6-значный код подтверждения"""
    return ''.join(random.choices(string.digits, k=6))

def send_verification_email(email, code):
    """Отправляет код подтверждения на указанный email"""
    msg = Message('Код подтверждения',
                 sender=app.config['MAIL_USERNAME'],
                 recipients=[email])
    msg.body = f'Ваш код подтверждения: {code}'
    mail.send(msg)

# Инициализация CSRF-защиты
csrf = CSRFProtect()
csrf.init_app(app)

# Исключаем некоторые маршруты из CSRF защиты
@csrf.exempt
def csrf_exempt_rule():
    return ['/api/posts']

# Регистрация API Blueprint
app.register_blueprint(api, url_prefix='/api')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    # Получаем сначала закрепленные посты
    pinned_posts = Post.query.filter_by(is_pinned=True).order_by(Post.date_posted.desc()).all()
    # Затем получаем обычные посты
    regular_posts = Post.query.filter_by(is_pinned=False).order_by(Post.date_posted.desc()).all()
    # Объединяем посты
    posts = pinned_posts + regular_posts
    
    # Отладочная информация
    print(f"Всего постов: {len(posts)}")
    print(f"Закрепленных постов: {len(pinned_posts)}")
    print(f"Обычных постов: {len(regular_posts)}")
    
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Пользователь с таким email уже существует', 'error')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        
        db.session.add(user)
        db.session.commit()
        
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
            
        flash('Неверное имя пользователя или пароль')
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    session.clear()
    response = make_response(redirect(url_for('login')))
    response.delete_cookie('remember_token')
    response.delete_cookie('session')
    flash('Вы успешно вышли из аккаунта', 'success')
    return response

@app.route('/api/posts', methods=['GET'])
@login_required
def posts():
    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return jsonify([{
        'id': post.id,
        'content': post.content,
        'image_url': post.image_url,
        'created_at': post.date_posted,
        'author': post.author.username
    } for post in posts])

@app.route('/api/posts/<int:post_id>/comments', methods=['GET', 'POST'])
@login_required
def post_comments(post_id):
    if request.method == 'GET':
        post = Post.query.get_or_404(post_id)
        comments = Comment.query.filter_by(post_id=post_id).order_by(Comment.date_posted.asc()).all()
        return jsonify([{
            'id': comment.id,
            'content': comment.content,
            'date_posted': comment.date_posted.isoformat(),
            'author': {
                'id': comment.author.id,
                'username': comment.author.username,
                'avatar': comment.author.avatar
            }
        } for comment in comments])
    
    elif request.method == 'POST':
        content = request.json.get('content')
        if not content:
            return jsonify({'success': False, 'message': 'Комментарий не может быть пустым'}), 400
        
        post = Post.query.get_or_404(post_id)
        comment = Comment(
            content=content,
            post_id=post_id,
            author_id=current_user.id
        )
        
        db.session.add(comment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'comment': {
                'id': comment.id,
                'content': comment.content,
                'date_posted': comment.date_posted.isoformat(),
                'author': {
                    'id': comment.author.id,
                    'username': comment.author.username,
                    'avatar': comment.author.avatar
                }
            }
        })

@app.route('/api/users/<int:user_id>/follow', methods=['POST'])
@login_required
def follow_user(user_id):
    if current_user.id == user_id:
        return jsonify({'message': 'Cannot follow yourself'})
    
    follow = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
    
    if follow:
        db.session.delete(follow)
        db.session.commit()
        return jsonify({'message': 'User unfollowed'})
    
    follow = Follow(follower_id=current_user.id, followed_id=user_id)
    db.session.add(follow)
    db.session.commit()
    
    return jsonify({'message': 'User followed'})

@app.route('/friends')
@login_required
def friends():
    # Получаем список друзей и заявок в друзья
    friends = Friendship.query.filter(
        ((Friendship.user_id == current_user.id) | (Friendship.friend_id == current_user.id)) &
        (Friendship.status == 'accepted')
    ).all()
    
    friend_requests = Friendship.query.filter(
        (Friendship.friend_id == current_user.id) &
        (Friendship.status == 'pending')
    ).all()
    
    return render_template('friends.html', friends=friends, friend_requests=friend_requests)

@app.route('/api/friends/<int:user_id>/add', methods=['POST'])
@login_required
def add_friend(user_id):
    if current_user.id == user_id:
        return jsonify({'message': 'Cannot add yourself as a friend'})
    
    # Проверяем, не существует ли уже заявка
    existing_request = Friendship.query.filter(
        ((Friendship.user_id == current_user.id) & (Friendship.friend_id == user_id)) |
        ((Friendship.user_id == user_id) & (Friendship.friend_id == current_user.id))
    ).first()
    
    if existing_request:
        return jsonify({'message': 'Friend request already exists'})
    
    friendship = Friendship(
        user_id=current_user.id,
        friend_id=user_id,
        status='pending'
    )
    
    db.session.add(friendship)
    db.session.commit()
    
    return jsonify({'message': 'Friend request sent'})

@app.route('/api/friends/<int:request_id>/accept', methods=['POST'])
@login_required
def accept_friend(request_id):
    friendship = Friendship.query.get_or_404(request_id)
    
    if friendship.friend_id != current_user.id:
        return jsonify({'message': 'Unauthorized'})
    
    friendship.status = 'accepted'
    db.session.commit()
    
    return jsonify({'message': 'Friend request accepted'})

@app.route('/api/friends/<int:request_id>/reject', methods=['POST'])
@login_required
def reject_friend(request_id):
    friendship = Friendship.query.get_or_404(request_id)
    
    if friendship.friend_id != current_user.id:
        return jsonify({'message': 'Unauthorized'})
    
    friendship.status = 'rejected'
    db.session.commit()
    
    return jsonify({'message': 'Friend request rejected'})

@app.route('/messages')
@login_required
def messages():
    # Получаем список диалогов
    conversations = db.session.query(
        User, PrivateMessage
    ).join(
        PrivateMessage,
        (User.id == PrivateMessage.sender_id) | (User.id == PrivateMessage.receiver_id)
    ).filter(
        (PrivateMessage.sender_id == current_user.id) | (PrivateMessage.receiver_id == current_user.id)
    ).order_by(PrivateMessage.created_at.desc()).all()
    
    return render_template('messages.html', conversations=conversations)

@app.route('/messages/<int:user_id>')
@login_required
def chat(user_id):
    other_user = User.query.get_or_404(user_id)
    
    # Получаем историю сообщений
    messages = PrivateMessage.query.filter(
        ((PrivateMessage.sender_id == current_user.id) & (PrivateMessage.receiver_id == user_id)) |
        ((PrivateMessage.sender_id == user_id) & (PrivateMessage.receiver_id == current_user.id))
    ).order_by(PrivateMessage.created_at.asc()).all()
    
    # Помечаем сообщения как прочитанные
    for message in messages:
        if message.receiver_id == current_user.id and not message.is_read:
            message.is_read = True
    db.session.commit()
    
    return render_template('chat.html', other_user=other_user, messages=messages)

@app.route('/api/messages/<int:user_id>', methods=['POST'])
@login_required
def send_message(user_id):
    if request.is_json:
        content = request.json.get('content')
    else:
        content = request.form.get('content')
    
    if not content:
        return jsonify({'message': 'Message content is required'}), 400
    
    message = PrivateMessage(
        sender_id=current_user.id,
        receiver_id=user_id,
        content=content
    )
    
    db.session.add(message)
    db.session.commit()
    
    return jsonify({
        'id': message.id,
        'content': message.content,
        'created_at': message.created_at.strftime('%d.%m.%Y %H:%M'),
        'sender': {
            'id': current_user.id,
            'username': current_user.username
        }
    })

@app.route('/users')
@login_required
def users():
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('users.html', users=users)

@app.route('/users/<int:user_id>')
@login_required
def user_profile(user_id):
    user = User.query.get_or_404(user_id)
    # Получаем сначала закрепленные посты, затем обычные
    pinned_posts = Post.query.filter_by(user_id=user_id, is_pinned=True).order_by(Post.date_posted.desc()).all()
    regular_posts = Post.query.filter_by(user_id=user_id, is_pinned=False).order_by(Post.date_posted.desc()).all()
    posts = pinned_posts + regular_posts
    return render_template('user_profile.html', user=user, posts=posts)

@app.route('/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        flash('Файл не выбран')
        return redirect(url_for('user_profile', user_id=current_user.id))
    
    file = request.files['avatar']
    if file.filename == '':
        flash('Файл не выбран')
        return redirect(url_for('user_profile', user_id=current_user.id))
    
    if file and allowed_file(file.filename, app.config['ALLOWED_IMAGE_EXTENSIONS']):
        filename = secure_filename(f"{current_user.id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        # Удаляем старый аватар, если он существует и не является дефолтным
        if current_user.avatar != 'default_avatar.png':
            old_avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.avatar)
            if os.path.exists(old_avatar_path):
                os.remove(old_avatar_path)
        
        current_user.avatar = filename
        db.session.commit()
        flash('Аватар успешно обновлен')
    else:
        flash('Недопустимый формат файла')
    
    return redirect(url_for('user_profile', user_id=current_user.id))

@app.route('/static/uploads/avatars/<filename>')
def uploaded_avatar(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/posts/<int:post_id>/pin', methods=['POST'])
@login_required
def pin_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    # Проверяем, является ли пользователь автором поста или администратором
    if current_user.id != post.author_id and not current_user.is_admin:
        return jsonify({'error': 'Недостаточно прав для закрепления поста'}), 403
    
    post.is_pinned = not post.is_pinned
    db.session.commit()
    
    return jsonify({
        'message': 'Статус закрепления поста обновлен',
        'is_pinned': post.is_pinned
    })

@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    # Проверяем, является ли пользователь автором поста или администратором
    if current_user.id != post.author_id and not current_user.is_admin:
        return jsonify({'error': 'Недостаточно прав для удаления поста'}), 403
    
    try:
        # Удаляем связанные файлы, если они есть
        if post.image_url:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_url)
            if os.path.exists(image_path):
                os.remove(image_path)
        
        if post.video_url:
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], post.video_url)
            if os.path.exists(video_path):
                os.remove(video_path)
        
        if post.file_url:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], post.file_url)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Удаляем все комментарии к посту
        Comment.query.filter_by(post_id=post.id).delete()
        
        # Удаляем все лайки поста
        Like.query.filter_by(post_id=post.id).delete()
        
        # Удаляем сам пост
        db.session.delete(post)
        db.session.commit()
        
        return jsonify({'message': 'Пост успешно удален'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при удалении поста: {str(e)}'}), 500

@app.route('/send_verification_code', methods=['POST'])
def send_verification():
    try:
        email = request.json.get('email')
        if not email:
            return jsonify({'error': 'Email не указан'}), 400

        # Генерируем новый код
        code = generate_verification_code()
        
        # Сохраняем код и время его истечения (15 минут)
        expiration_time = datetime.now() + timedelta(minutes=15)
        verification_codes[email] = {
            'code': code,
            'expiration_time': expiration_time
        }

        # Отправляем код на email
        send_verification_email(email, code)

        return jsonify({'message': 'Код подтверждения отправлен'}), 200

    except Exception as e:
        return jsonify({'error': 'Ошибка при отправке кода подтверждения'}), 500

@app.route('/test_email')
def test_email():
    try:
        msg = Message('Тестовое письмо',
                     sender=app.config['MAIL_DEFAULT_SENDER'],
                     recipients=['sigmastiller@gmail.com'])
        msg.body = 'Это тестовое письмо для проверки работы Flask-Mail'
        mail.send(msg)
        return 'Письмо успешно отправлено!'
    except Exception as e:
        return f'Ошибка при отправке письма: {str(e)}'

@app.route('/uploads/videos/<filename>')
def uploaded_video(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), filename)

@app.route('/uploads/files/<filename>')
def uploaded_file(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'files'), filename)

@app.context_processor
def utility_processor():
    def get_csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = generate_csrf()
        return session['csrf_token']
    return dict(csrf_token=get_csrf_token, get_locale=get_locale)

@app.after_request
def after_request(response):
    if 'csrf_token' not in session:
        session['csrf_token'] = generate_csrf()
    
    response.headers.set('X-CSRF-Token', session['csrf_token'])
    
    # Добавляем заголовки безопасности
    response.headers.set('Access-Control-Allow-Origin', '*')
    response.headers.set('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-CSRF-Token')
    response.headers.set('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    
    return response

# Обработчик OPTIONS запросов для CORS
@app.route('/', methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def options_handler(path=None):
    return '', 200

@app.route('/api/posts', methods=['POST'])
@csrf.exempt
@login_required
def create_post():
    if 'content' not in request.form:
        return jsonify({'error': 'Текст поста обязателен'}), 400
    
    content = request.form['content']
    is_pinned = request.form.get('is_pinned', 'false').lower() == 'true'
    
    post = Post(
        content=content,
        author_id=current_user.id,
        is_pinned=is_pinned,
        date_posted=datetime.utcnow()
    )
    
    # Обработка изображений
    if 'image' in request.files:
        image = request.files['image']
        if image and image.filename and allowed_file(image.filename, app.config['ALLOWED_IMAGE_EXTENSIONS']):
            try:
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image.filename}")
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], 'images', filename)
                os.makedirs(os.path.dirname(image_path), exist_ok=True)
                image.save(image_path)
                post.image_url = f"images/{filename}"
            except Exception as e:
                return jsonify({'error': f'Ошибка при загрузке изображения: {str(e)}'}), 500
        elif image and image.filename:
            return jsonify({'error': 'Недопустимый формат изображения'}), 400
    
    # Обработка видео
    if 'video' in request.files:
        video = request.files['video']
        if video and video.filename and allowed_file(video.filename, app.config['ALLOWED_VIDEO_EXTENSIONS']):
            try:
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{video.filename}")
                video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'videos', filename)
                os.makedirs(os.path.dirname(video_path), exist_ok=True)
                video.save(video_path)
                post.video_url = f"videos/{filename}"
            except Exception as e:
                return jsonify({'error': f'Ошибка при загрузке видео: {str(e)}'}), 500
        elif video and video.filename:
            return jsonify({'error': 'Недопустимый формат видео'}), 400
    
    # Обработка файлов
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename and allowed_file(file.filename, app.config['ALLOWED_FILE_EXTENSIONS']):
            try:
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'files', filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                file.save(file_path)
                post.file_url = f"files/{filename}"
                post.file_name = file.filename
                post.file_type = file.filename.rsplit('.', 1)[1].lower()
            except Exception as e:
                return jsonify({'error': f'Ошибка при загрузке файла: {str(e)}'}), 500
        elif file and file.filename:
            return jsonify({'error': 'Недопустимый формат файла'}), 400
    
    try:
        db.session.add(post)
        db.session.commit()
        
        return jsonify({
            'message': 'Пост успешно создан',
            'post': {
                'id': post.id,
                'content': post.content,
                'image_url': post.image_url if hasattr(post, 'image_url') else None,
                'video_url': post.video_url if hasattr(post, 'video_url') else None,
                'file_url': post.file_url if hasattr(post, 'file_url') else None,
                'file_name': post.file_name if hasattr(post, 'file_name') else None,
                'created_at': post.date_posted,
                'author': {
                    'id': current_user.id,
                    'username': current_user.username,
                    'avatar': current_user.avatar
                }
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при сохранении поста: {str(e)}'}), 500

@app.route('/games')
@login_required
def games():
    # Получаем активные игровые сессии
    game_sessions = GameSession.query.filter(
        (GameSession.status == 'waiting') & 
        (GameSession.player1_id != current_user.id)
    ).all()
    return render_template('games.html', game_sessions=game_sessions)

@app.route('/api/games/create', methods=['POST'])
@login_required
def create_game():
    game_type = request.json.get('game_type')
    if not game_type:
        return jsonify({'error': 'Тип игры не указан'}), 400

    try:
        session = GameSession(
            game_type=game_type,
            player1_id=current_user.id,
            game_data={}
        )
        db.session.add(session)
        db.session.commit()

        return jsonify({
            'success': True,
            'session': {
                'id': session.id,
                'game_type': session.game_type,
                'status': session.status
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/games/<int:session_id>/join', methods=['POST'])
@login_required
def join_game(session_id):
    session = GameSession.query.get_or_404(session_id)
    
    if session.status != 'waiting':
        return jsonify({'error': 'Игра уже началась'}), 400
    
    if session.player1_id == current_user.id:
        return jsonify({'error': 'Вы не можете присоединиться к своей игре'}), 400

    try:
        session.player2_id = current_user.id
        session.status = 'active'
        session.current_turn = session.player1_id
        db.session.commit()

        # Уведомляем игроков о начале игры
        socketio.emit('game_start', {
            'session_id': session.id,
            'game_type': session.game_type,
            'current_turn': session.current_turn
        }, room=f'game_{session.id}')

        return jsonify({
            'success': True,
            'session': {
                'id': session.id,
                'game_type': session.game_type,
                'status': session.status
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('join_game')
def handle_join_game(data):
    session_id = data['session_id']
    join_room(f'game_{session_id}')
    print(f'Client {request.sid} joined game {session_id}')

@socketio.on('game_move')
def handle_game_move(data):
    session_id = data['session_id']
    move = data['move']
    
    session = GameSession.query.get(session_id)
    if not session:
        return
    
    if session.current_turn != current_user.id:
        return
    
    # Обновляем состояние игры
    game_data = session.game_data
    game_data['moves'] = game_data.get('moves', []) + [move]
    session.game_data = game_data
    
    # Меняем текущего игрока
    session.current_turn = session.player2_id if session.current_turn == session.player1_id else session.player1_id
    
    db.session.commit()
    
    # Отправляем обновление всем игрокам
    emit('game_update', {
        'move': move,
        'current_turn': session.current_turn
    }, room=f'game_{session_id}')

@socketio.on('game_over')
def handle_game_over(data):
    session_id = data['session_id']
    winner_id = data.get('winner_id')
    
    session = GameSession.query.get(session_id)
    if not session:
        return
    
    session.status = 'finished'
    session.winner_id = winner_id
    db.session.commit()
    
    emit('game_ended', {
        'winner_id': winner_id
    }, room=f'game_{session_id}')

@app.route('/groups')
@login_required
def groups():
    user_groups = current_user.groups
    all_groups = Group.query.filter(Group.id.notin_([g.id for g in user_groups])).all()
    return render_template('groups.html', user_groups=user_groups, all_groups=all_groups)

@app.route('/channels')
@login_required
def channels():
    user_channels = current_user.channels
    all_channels = Channel.query.filter(Channel.id.notin_([c.id for c in user_channels])).all()
    return render_template('channels.html', user_channels=user_channels, all_channels=all_channels)

@app.route('/group/<int:group_id>')
@login_required
def group(group_id):
    group = Group.query.get_or_404(group_id)
    posts = Post.query.filter_by(group_id=group_id).order_by(Post.date_posted.desc()).all()
    return render_template('group.html', group=group, posts=posts)

@app.route('/channel/<int:channel_id>')
@login_required
def channel(channel_id):
    channel = Channel.query.get_or_404(channel_id)
    posts = Post.query.filter_by(channel_id=channel_id).order_by(Post.date_posted.desc()).all()
    return render_template('channel.html', channel=channel, posts=posts)

@app.route('/create_group', methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        if not name:
            flash('Название группы обязательно', 'error')
            return redirect(url_for('create_group'))
        
        group = Group(name=name, description=description, created_by=current_user.id)
        group.members.append(current_user)
        db.session.add(group)
        db.session.commit()
        
        flash('Группа успешно создана', 'success')
        return redirect(url_for('group', group_id=group.id))
    
    return render_template('create_group.html')

@app.route('/create_channel', methods=['GET', 'POST'])
@login_required
def create_channel():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        if not name:
            flash('Название канала обязательно', 'error')
            return redirect(url_for('create_channel'))
        
        channel = Channel(name=name, description=description, created_by=current_user.id)
        channel.members.append(current_user)
        db.session.add(channel)
        db.session.commit()
        
        flash('Канал успешно создан', 'success')
        return redirect(url_for('channel', channel_id=channel.id))
    
    return render_template('create_channel.html')

@app.route('/join_group/<int:group_id>')
@login_required
def join_group(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user not in group.members:
        group.members.append(current_user)
        db.session.commit()
        flash('Вы успешно присоединились к группе', 'success')
    return redirect(url_for('group', group_id=group_id))

@app.route('/join_channel/<int:channel_id>')
@login_required
def join_channel(channel_id):
    channel = Channel.query.get_or_404(channel_id)
    if current_user not in channel.members:
        channel.members.append(current_user)
        db.session.commit()
        flash('Вы успешно присоединились к каналу', 'success')
    return redirect(url_for('channel', channel_id=channel_id))

@app.route('/leave_group/<int:group_id>')
@login_required
def leave_group(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user in group.members:
        group.members.remove(current_user)
        db.session.commit()
        flash('Вы покинули группу', 'info')
    return redirect(url_for('groups'))

@app.route('/leave_channel/<int:channel_id>')
@login_required
def leave_channel(channel_id):
    channel = Channel.query.get_or_404(channel_id)
    if current_user in channel.members:
        channel.members.remove(current_user)
        db.session.commit()
        flash('Вы покинули канал', 'info')
    return redirect(url_for('channels'))

@app.route('/post_to_group/<int:group_id>', methods=['POST'])
@login_required
def post_to_group(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user not in group.members:
        flash('Вы не состоите в этой группе', 'error')
        return redirect(url_for('group', group_id=group_id))
    
    title = request.form.get('title')
    content = request.form.get('content')
    
    if not content:
        flash('Содержание поста обязательно', 'error')
        return redirect(url_for('group', group_id=group_id))
    
    post = Post(title=title, content=content, user_id=current_user.id, group_id=group_id)
    db.session.add(post)
    db.session.commit()
    
    flash('Пост успешно опубликован', 'success')
    return redirect(url_for('group', group_id=group_id))

@app.route('/post_to_channel/<int:channel_id>', methods=['POST'])
@login_required
def post_to_channel(channel_id):
    channel = Channel.query.get_or_404(channel_id)
    if current_user not in channel.members:
        flash('Вы не состоите в этом канале', 'error')
        return redirect(url_for('channel', channel_id=channel_id))
    
    title = request.form.get('title')
    content = request.form.get('content')
    
    if not content:
        flash('Содержание поста обязательно', 'error')
        return redirect(url_for('channel', channel_id=channel_id))
    
    post = Post(title=title, content=content, user_id=current_user.id, channel_id=channel_id)
    db.session.add(post)
    db.session.commit()
    
    flash('Пост успешно опубликован', 'success')
    return redirect(url_for('channel', channel_id=channel_id))

@app.route('/set_language/<lang>')
def set_language(lang):
    if lang in app.config['BABEL_SUPPORTED_LOCALES']:
        session['lang'] = lang
        g.locale = lang
    return redirect(request.referrer or url_for('index'))

@app.before_request
def before_request():
    g.locale = get_locale()

@app.route('/api/posts/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    
    if like:
        db.session.delete(like)
        is_liked = False
    else:
        like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(like)
        is_liked = True
    
    db.session.commit()
    
    likes_count = Like.query.filter_by(post_id=post_id).count()
    return jsonify({
        'success': True,
        'is_liked': is_liked,
        'likes_count': likes_count
    })

@app.route('/bot')
@login_required
def bot_chat():
    return render_template('bot_chat.html')

@app.route('/api/bot/message', methods=['POST'])
@login_required
def send_message_to_bot():
    data = request.get_json()
    message = data.get('message')
    
    if not message:
        return jsonify({'error': 'Сообщение не может быть пустым'}), 400
        
    response = chatbot.get_response(current_user.id, message)
    return jsonify({'response': response['response']})

@app.route('/api/bot/history', methods=['GET'])
@login_required
def get_bot_history():
    messages = chatbot.get_history(current_user.id)
    return jsonify(messages)

@app.route('/api/bot/settings', methods=['GET', 'POST'])
@login_required
def bot_settings():
    if request.method == 'GET':
        settings = BotSettings.query.filter_by(user_id=current_user.id).first()
        if not settings:
            settings = BotSettings(user_id=current_user.id)
            db.session.add(settings)
            db.session.commit()
        return jsonify({
            'is_active': settings.is_active,
            'personality': settings.personality
        })
    else:
        data = request.get_json()
        settings = BotSettings.query.filter_by(user_id=current_user.id).first()
        if not settings:
            settings = BotSettings(user_id=current_user.id)
            db.session.add(settings)
        
        if 'is_active' in data:
            settings.is_active = data['is_active']
        if 'personality' in data:
            settings.personality = data['personality']
        
        db.session.commit()
        return jsonify({
            'is_active': settings.is_active,
            'personality': settings.personality
        })

@app.route('/api/bot/clear', methods=['POST'])
@login_required
def clear_bot_history():
    BotMessage.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'message': 'История чата очищена'})

if __name__ == '__main__':
    socketio.run(app, debug=True) 