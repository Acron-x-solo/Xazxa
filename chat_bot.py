from datetime import datetime
from models import BotMessage, BotSettings, db
import random

class ChatBot:
    def __init__(self):
        self.responses = {
            'привет': ['Привет!', 'Здравствуйте!', 'Добрый день!'],
            'как дела': ['Отлично!', 'Всё хорошо, спасибо!', 'Замечательно!'],
            'пока': ['До свидания!', 'До встречи!', 'Всего доброго!'],
            'что ты умеешь': ['Я могу отвечать на простые вопросы и помогать вам!',
                           'Я умею вести диалог и отвечать на базовые вопросы.',
                           'Я простой бот, который может поддержать беседу.'],
        }
        self.default_responses = [
            'Извините, я не совсем понял ваш вопрос.',
            'Можете, пожалуйста, переформулировать?',
            'Я пока не знаю, как ответить на этот вопрос.',
            'Давайте поговорим о чем-то другом?'
        ]

    def get_response(self, message, user_id):
        # Получаем настройки пользователя
        settings = BotSettings.query.filter_by(user_id=user_id).first()
        if not settings:
            settings = BotSettings(user_id=user_id)
            db.session.add(settings)
            db.session.commit()

        # Если бот выключен, возвращаем сообщение об этом
        if not settings.is_active:
            return "Бот в данный момент отключен. Включите его в настройках."

        # Приводим сообщение к нижнему регистру для поиска
        message_lower = message.lower().strip()

        # Ищем подходящий ответ
        response = None
        for key in self.responses:
            if key in message_lower:
                response = random.choice(self.responses[key])
                break

        # Если ответ не найден, используем случайный стандартный ответ
        if not response:
            response = random.choice(self.default_responses)

        # Сохраняем сообщение и ответ в истории
        bot_message = BotMessage(
            user_id=user_id,
            message=message,
            response=response,
            created_at=datetime.utcnow()
        )
        db.session.add(bot_message)
        db.session.commit()

        return response

    def get_conversation_history(self, user_id):
        """Получение истории сообщений для конкретного пользователя"""
        return BotMessage.query.filter_by(user_id=user_id).order_by(BotMessage.created_at.asc()).all()

    def add_custom_response(self, trigger, responses):
        """Добавление пользовательских ответов"""
        if isinstance(responses, list):
            self.responses[trigger.lower()] = responses
        else:
            self.responses[trigger.lower()] = [responses] 