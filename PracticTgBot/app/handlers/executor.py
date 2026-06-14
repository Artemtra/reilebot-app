from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import (
    get_user_by_telegram, get_new_requests, assign_executor,
    complete_request, request_extension
)

router = Router()

class ReportState(StatesGroup):
    waiting_for_report_text = State()

class ExtensionState(StatesGroup):
    waiting_for_days = State()

@router.message(F.text == "📋 Новые заявки")
async def list_new_requests(message: Message):
    requests = await get_new_requests()
    
    if not requests:
        await message.answer("Нет новых заявок")
        return
    
    for req in requests:
        await message.answer(
            f"🆕 Заявка #{req['id']}\n"
            f"Клиент: {req['client_name'] or 'Неизвестен'}\n"
            f"Описание: {req['description'][:200]}\n"
            f"Создана: {req['created_at']}\n\n"
            f"Чтобы взять заявку, отправьте: /take_{req['id']}"
        )

@router.message(F.text.startswith("/take_"))
async def take_request(message: Message):
    request_id = int(message.text.split("_")[1])
    user = await get_user_by_telegram(message.from_user.id)
    
    if not user or user['role'] != 'executor':
        await message.answer("У вас нет прав исполнителя")
        return
    
    result = await assign_executor(request_id, message.from_user.id)
    
    if result:
        await message.answer(f"✅ Вы взяли заявку #{request_id} в работу!")
    else:
        await message.answer("❌ Не удалось назначить заявку")

@router.message(F.text == "✅ Мои активные заявки")
async def my_active_requests(message: Message):
    await message.answer("Функция в разработке")

@router.message(F.text == "🔄 Запросить продление")
async def list_requests_for_extension(message: Message):
    await message.answer("Функция в разработке")