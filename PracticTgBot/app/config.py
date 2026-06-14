import os
from dotenv import load_dotenv
from aiogram.client.telegram import TelegramAPIServer

# Загружаем переменные из файла .env
load_dotenv()

class Config:
    """Класс с настройками приложения"""
    
    # Telegram Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # Cloudflare Worker прокси (для обхода блокировок)
    # Если переменная не задана в .env, используем прямой API Telegram
    TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")
    
    # PostgreSQL Database
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "PracticTgBotDB")
    DB_USER = os.getenv("DB_USER", "admin")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "11111123")
    
    # API Security
    API_SECRET_KEY = os.getenv("API_SECRET_KEY", "SuperSecretKeyForMyBot67")
    
    # Media Files
    MEDIA_ROOT = os.getenv("MEDIA_ROOT", "./media")
    
    # API Server
    API_PORT = int(os.getenv("API_PORT", 8000))
    
    @property
    def DB_DSN(self):
        """Строка подключения к PostgreSQL"""
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def TELEGRAM_API_SERVER(self):
        """Возвращает объект TelegramAPIServer для aiogram"""
        return TelegramAPIServer.from_base(self.TELEGRAM_API_BASE)


# Создаем глобальный экземпляр конфигурации
config = Config()