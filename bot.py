import random
from datetime import datetime
from models import BotMessage, BotSettings, db
import re
import os
from openai import OpenAI
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

class ChatBot:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.personalities = {
            'friendly': {
                'system_prompt': """Ты дружелюбный и веселый собеседник. 
                Ты любишь общаться на разные темы, особенно про игры, музыку, фильмы и книги.
                Ты всегда поддерживаешь разговор и задаешь интересные вопросы.
                Ты используешь неформальный стиль общения и эмодзи."""
            },
            'professional': {
                'system_prompt': """Ты профессиональный и вежливый собеседник.
                Ты специализируешься на деловом общении, управлении проектами и карьерном развитии.
                Ты всегда сохраняешь формальный стиль общения и помогаешь с решением задач."""
            }
        }
        self.default_personality = 'friendly'

    def get_ai_response(self, message, personality, conversation_history=None):
        try:
            # Формируем историю диалога
            messages = [
                {"role": "system", "content": self.personalities[personality]['system_prompt']}
            ]
            
            # Добавляем историю диалога, если она есть
            if conversation_history:
                for msg in conversation_history:
                    messages.append({"role": "user", "content": msg.message})
                    messages.append({"role": "assistant", "content": msg.response})
            
            # Добавляем текущее сообщение
            messages.append({"role": "user", "content": message})
            
            # Получаем ответ от GPT
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.7,
                max_tokens=150
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Ошибка при получении ответа от GPT: {e}")
            return "Извините, произошла ошибка при обработке вашего сообщения."

    def get_response(self, message, user_id):
        # Получаем настройки бота
        settings = BotSettings.query.filter_by(user_id=user_id).first()
        if not settings:
            settings = BotSettings(user_id=user_id)
            db.session.add(settings)
            db.session.commit()

        if not settings.is_active:
            return "Бот временно отключен."

        # Определяем личность бота
        personality = settings.personality if settings.personality else self.default_personality
        
        # Получаем историю диалога
        conversation_history = self.get_conversation_history(user_id, limit=5)
        
        # Получаем ответ от ИИ
        response = self.get_ai_response(message, personality, conversation_history)

        # Сохраняем сообщение в историю
        bot_message = BotMessage(
            user_id=user_id,
            message=message,
            response=response,
            timestamp=datetime.utcnow()
        )
        db.session.add(bot_message)
        db.session.commit()

        return response

    def get_conversation_history(self, user_id, limit=50):
        return BotMessage.query.filter_by(user_id=user_id).order_by(BotMessage.timestamp.desc()).limit(limit).all()

    def clear_history(self, user_id):
        BotMessage.query.filter_by(user_id=user_id).delete()
        db.session.commit()

    def update_settings(self, user_id, is_active=None, personality=None):
        settings = BotSettings.query.filter_by(user_id=user_id).first()
        if not settings:
            settings = BotSettings(user_id=user_id)
            db.session.add(settings)

        if is_active is not None:
            settings.is_active = is_active
        if personality is not None and personality in self.personalities:
            settings.personality = personality

        db.session.commit()
        return settings 