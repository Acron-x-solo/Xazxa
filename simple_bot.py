from datetime import datetime
import random
from models import BotMessage, BotSettings, db
import logging

class SimpleBot:
    def __init__(self):
        self.responses = {
            'greeting': [
                'Привет! Как я могу помочь?',
                'Здравствуйте! Чем могу быть полезен?',
                'Добрый день! Готов помочь вам.'
            ],
            'general': [
                'Интересный вопрос! Давайте обсудим это.',
                'Я постараюсь помочь вам с этим.',
                'Хороший вопрос. Давайте разберемся.'
            ],
            'unknown': [
                'Извините, я не совсем понял вопрос. Можете переформулировать?',
                'Не уверен, что правильно понял. Можете пояснить?',
                'Давайте попробуем выразить это по-другому.'
            ]
        }
        self.custom_responses = {}
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)

    def get_response(self, user_id, message):
        try:
            self.logger.debug(f"Получено сообщение от пользователя {user_id}: {message}")
            
            # Получаем настройки бота для пользователя
            settings = BotSettings.query.filter_by(user_id=user_id).first()
            if not settings:
                settings = BotSettings(user_id=user_id)
                db.session.add(settings)
                db.session.commit()
            
            if not settings.is_active:
                response_text = "Бот отключен. Включите его в настройках для общения."
            else:
                # Определяем тип ответа
                message_lower = message.lower()
                if any(word in message_lower for word in ['привет', 'здравствуй', 'добрый']):
                    response_text = random.choice(self.responses['greeting'])
                elif message_lower in self.custom_responses:
                    response_text = self.custom_responses[message_lower]
                else:
                    response_text = random.choice(self.responses['general'])

            # Сохраняем сообщение в базу данных
            bot_message = BotMessage(
                user_id=user_id,
                message=message,
                response=response_text,
                timestamp=datetime.utcnow()
            )
            db.session.add(bot_message)
            
            try:
                db.session.commit()
                self.logger.debug(f"Сообщение успешно сохранено в базу данных")
            except Exception as e:
                self.logger.error(f"Ошибка при сохранении в базу данных: {str(e)}")
                db.session.rollback()
                response_text = "Извините, произошла ошибка при обработке сообщения."

            return {
                'response': response_text,
                'timestamp': bot_message.timestamp.isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка в методе get_response: {str(e)}")
            return {
                'response': "Извините, произошла ошибка при обработке сообщения.",
                'timestamp': datetime.utcnow().isoformat()
            }

    def get_history(self, user_id, limit=50):
        messages = BotMessage.query.filter_by(user_id=user_id)\
            .order_by(BotMessage.timestamp.desc())\
            .limit(limit)\
            .all()
        return [{
            'message': msg.message,
            'response': msg.response,
            'timestamp': msg.timestamp.isoformat()
        } for msg in messages][::-1]

    def add_custom_response(self, trigger, response):
        self.custom_responses[trigger.lower()] = response 