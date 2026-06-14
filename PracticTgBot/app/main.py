import asyncio
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import config
from app.database import init_db
from app.handlers import start, client, executor, admin
from app.api import app as fastapi_app
session = AiohttpSession(api=config.TELEGRAM_API_SERVER)

async def run_bot():
    print("🔄 Инициализация базы данных...")
    await init_db()
    
    print("🤖 Запуск бота...")
    if config.TELEGRAM_API_BASE != "https://api.telegram.org":
        print(f"   📡 Используется прокси: {config.TELEGRAM_API_BASE}")
    else:
        print("   📡 Используется прямой API Telegram")
    
    bot = Bot(token=config.BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    
    dp.include_router(start.router)
    dp.include_router(client.router)
    dp.include_router(executor.router)
    dp.include_router(admin.router)
    
    await bot.delete_webhook()
    
    print("✅ Бот успешно запущен!")
    await dp.start_polling(bot)

async def run_api():
    config_uvicorn = uvicorn.Config(
        fastapi_app,
        host="127.0.0.1",
        port=config.API_PORT,
        log_level="info"
    )
    server = uvicorn.Server(config_uvicorn)
    await server.serve()

async def main():
    await asyncio.gather(run_bot(), run_api())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Остановка бота...")