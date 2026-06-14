from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import (
    get_pool, get_user_by_telegram, get_all_requests_with_filters,
    get_all_users, update_user_role, get_system_stats,
    admin_force_assign_executor, admin_update_status, admin_delete_request,
    get_request_media, get_request_by_id
)
from app.keyboards import main_menu, back_to_menu_button
from app.utils import save_media_file
import os

router = Router()

class AdminAssignState(StatesGroup):
    waiting_for_executor_telegram = State()

class AdminStatusState(StatesGroup):
    waiting_for_new_status = State()


@router.message(F.text == "📊 Все заявки")
async def all_requests(message: Message):
    """Администратор видит ВСЕ заявки без ограничений"""
    user = await get_user_by_telegram(message.from_user.id)
    
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет доступа к этой функции.")
        return
    requests = await get_all_requests_with_filters()
    
    if not requests:
        await message.answer("📭 Нет ни одной заявки.")
        return
    
    await message.answer(
        f"📊 **Все заявки в системе** (всего: {len(requests)})\n\n"
        f"• Для просмотра файлов введите: `/номер`\n"
        f"• Для управления заявкой нажмите на кнопки",
        parse_mode="Markdown"
    )
    
    for req in requests:
        status_emoji = {
            'new': '🆕',
            'in_work': '🔧',
            'completed': '✅',
            'extended': '🔄',
            'cancelled': '❌'
        }.get(req['status'], '❓')
        
        status_text = {
            'new': 'Новая (ожидает назначения)',
            'in_work': 'В работе',
            'completed': 'Выполнена',
            'extended': 'Продление запрошено',
            'cancelled': 'Отменена'
        }.get(req['status'], req['status'])
        
        media = await get_request_media(req['id'])
        media_text = f"📎 Файлов: {len(media)}" if media else "📎 Нет файлов"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Назначить исполнителя", callback_data=f"admin_assign_{req['id']}"),
                InlineKeyboardButton(text="📝 Сменить статус", callback_data=f"admin_status_{req['id']}")
            ],
            [
                InlineKeyboardButton(text="❌ Удалить заявку", callback_data=f"admin_delete_{req['id']}")
            ],
            [
                InlineKeyboardButton(text="📸 Просмотр файлов", callback_data=f"admin_view_files_{req['id']}")
            ]
        ])
        
        await message.answer(
            f"{status_emoji} **Заявка #{req['id']}**\n"
            f"📝 {req['description'][:200]}\n"
            f"🔄 Статус: {status_text}\n"
            f"{media_text}\n"
            f"👤 Клиент: {req['client_name'] or 'Неизвестен'}\n"
            f"👤 Исполнитель: {req['executor_name'] or 'Не назначен'}\n"
            f"📅 Создана: {req['created_at'].strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown",
            reply_markup=keyboard
        )


@router.callback_query(F.data.startswith("admin_view_files_"))
async def admin_view_files(callback: CallbackQuery):
    """Администратор просматривает файлы заявки"""
    request_id = int(callback.data.split("_")[3])
    
    media_files = await get_request_media(request_id)
    
    if not media_files:
        await callback.answer("В этой заявке нет файлов", show_alert=True)
        return
    
    await callback.answer(f"📎 Найдено {len(media_files)} файлов")
    
    for i, media in enumerate(media_files, 1):
        file_path = media['file_path']
        
        if not os.path.exists(file_path):
            await callback.message.answer(f"❌ Файл {i} не найден на сервере.")
            continue
        
        try:
            if media['media_type'] == 'photo' or file_path.endswith(('.jpg', '.png', '.jpeg', '.gif')):
                from aiogram.types import FSInputFile
                photo = FSInputFile(file_path)
                await callback.message.answer_photo(photo, caption=f"📸 Файл #{i} заявки #{request_id}")
            elif media['media_type'] == 'video' or file_path.endswith(('.mp4', '.avi', '.mov')):
                from aiogram.types import FSInputFile
                video = FSInputFile(file_path)
                await callback.message.answer_video(video, caption=f"🎥 Файл #{i} заявки #{request_id}")
            else:
                from aiogram.types import FSInputFile
                doc = FSInputFile(file_path)
                await callback.message.answer_document(doc, caption=f"📄 Файл #{i} заявки #{request_id}")
        except Exception as e:
            await callback.message.answer(f"❌ Ошибка при отправке файла {i}: {str(e)}")


@router.callback_query(F.data.startswith("admin_assign_"))
async def admin_assign_start(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.split("_")[2])
    await state.update_data(request_id=request_id)
    pool = await get_pool()
    executors = await pool.fetch("SELECT telegram_id, full_name FROM users WHERE role = 'executor'")
    
    if not executors:
        await callback.message.answer("❌ Нет зарегистрированных исполнителей.")
        await callback.answer()
        return
    
    text = "👤 **Выберите исполнителя:**\n\n"
    for ex in executors:
        text += f"🔹 `{ex['telegram_id']}` - {ex['full_name'] or 'Без имени'}\n"
    
    text += "\n➡️ Введите Telegram ID исполнителя:"
    
    await callback.message.answer(text, parse_mode="Markdown")
    await state.set_state(AdminAssignState.waiting_for_executor_telegram)
    await callback.answer()


@router.message(AdminAssignState.waiting_for_executor_telegram)
async def admin_assign_executor(message: Message, state: FSMContext):
    try:
        executor_telegram = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Ошибка: Telegram ID должен быть числом.")
        return
    
    data = await state.get_data()
    request_id = data['request_id']
    
    result = await admin_force_assign_executor(request_id, executor_telegram)
    
    if result:
        await message.answer(f"✅ Исполнитель назначен на заявку #{request_id}!")
        try:
            await message.bot.send_message(
                executor_telegram,
                f"🔔 **Вам назначена новая заявка!**\n\n"
                f"📋 Заявка #{request_id}\n"
                f"📝 {result['description'][:100]}\n\n"
                f"Нажмите /start для просмотра."
            )
        except:
            pass
    else:
        await message.answer(f"❌ Не удалось назначить исполнителя. Проверьте Telegram ID.")
    
    await state.clear()


@router.callback_query(F.data.startswith("admin_status_"))
async def admin_status_start(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.split("_")[2])
    await state.update_data(request_id=request_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 new", callback_data="set_status_new")],
        [InlineKeyboardButton(text="🔧 in_work", callback_data="set_status_in_work")],
        [InlineKeyboardButton(text="✅ completed", callback_data="set_status_completed")],
        [InlineKeyboardButton(text="🔄 extended", callback_data="set_status_extended")],
        [InlineKeyboardButton(text="❌ cancelled", callback_data="set_status_cancelled")]
    ])
    
    await callback.message.answer("📝 **Выберите новый статус:**", reply_markup=keyboard)
    await state.set_state(AdminStatusState.waiting_for_new_status)
    await callback.answer()


@router.callback_query(AdminStatusState.waiting_for_new_status, F.data.startswith("set_status_"))
async def admin_set_status(callback: CallbackQuery, state: FSMContext):
    new_status = callback.data.replace("set_status_", "")
    data = await state.get_data()
    request_id = data['request_id']
    
    result = await admin_update_status(request_id, new_status)
    
    if result:
        await callback.message.answer(f"✅ Статус заявки #{request_id} изменен на '{new_status}'")
    else:
        await callback.message.answer(f"❌ Заявка #{request_id} не найдена")
    
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_"))
async def admin_delete_request_callback(callback: CallbackQuery):
    request_id = int(callback.data.split("_")[2])
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{request_id}"),
            InlineKeyboardButton(text="❌ Нет, отмена", callback_data="cancel_delete")
        ]
    ])
    
    await callback.message.answer(
        f"⚠️ **Вы уверены, что хотите удалить заявку #{request_id}?**\n\n"
        f"Это действие необратимо.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete(callback: CallbackQuery):
    request_id = int(callback.data.split("_")[2])
    
    result = await admin_delete_request(request_id)
    
    if result == "DELETE 1":
        await callback.message.edit_text(f"✅ Заявка #{request_id} успешно удалена!")
    else:
        await callback.message.edit_text(f"❌ Заявка #{request_id} не найдена.")
    
    await callback.answer()


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: CallbackQuery):
    await callback.message.edit_text("❌ Удаление отменено.")
    await callback.answer()


@router.message(F.text == "👥 Управление пользователями")
async def admin_user_list(message: Message):
    user = await get_user_by_telegram(message.from_user.id)
    
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет доступа к этой функции.")
        return
    
    users = await get_all_users()
    
    if not users:
        await message.answer("📭 Нет зарегистрированных пользователей.")
        return
    
    text = "👥 **Список пользователей:**\n\n"
    for u in users:
        role_emoji = {
            'client': '👤',
            'executor': '🔧', 
            'admin': '👑',
            'accountant': '💰',
            'director': '📈'
        }.get(u['role'], '❓')
        
        text += f"{role_emoji} **{u['full_name'] or u['telegram_id']}**\n"
        text += f"   ID: `{u['telegram_id']}`\n"
        text += f"   Роль: {u['role']}\n\n"
    
    text += "📝 **Для смены роли введите:**\n"
    text += "`/setrole TelegramID новая_роль`\n\n"
    text += "Доступные роли: client, executor, admin, accountant, director\n\n"
    text += "Пример: `/setrole 123456789 executor`"
    
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text.startswith("/setrole"))
async def admin_set_role(message: Message):
    user = await get_user_by_telegram(message.from_user.id)
    
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(
            "❌ **Неверный формат команды!**\n\n"
            "Правильный формат:\n"
            "`/setrole TelegramID новая_роль`\n\n"
            "Пример: `/setrole 123456789 executor`\n\n"
            "Доступные роли: client, executor, admin",
            parse_mode="Markdown"
        )
        return
    
    try:
        target_telegram_id = int(parts[1])
        new_role = parts[2].lower()
        
        valid_roles = ['client', 'executor', 'admin']
        if new_role not in valid_roles:
            await message.answer(f"❌ Недопустимая роль: {new_role}\n\nДоступные роли: {', '.join(valid_roles)}")
            return
        
        result = await update_user_role(target_telegram_id, new_role)
        
        if result:
            target_user = await get_user_by_telegram(target_telegram_id)
            await message.answer(
                f"✅ **Роль пользователя изменена!**\n\n"
                f"👤 Пользователь: {target_user['full_name'] or target_telegram_id}\n"
                f"🆔 Telegram ID: {target_telegram_id}\n"
                f"🎭 Новая роль: {new_role}"
            )
            
            try:
                await message.bot.send_message(
                    target_telegram_id,
                    f"🔔 **Ваша роль изменена администратором!**\n\n"
                    f"🎭 Новая роль: **{new_role}**\n\n"
                    f"Нажмите /start для обновления меню."
                )
            except:
                pass
        else:
            await message.answer(f"❌ Пользователь с Telegram ID {target_telegram_id} не найден.")
            
    except ValueError:
        await message.answer("❌ Telegram ID должен быть числом.\nПример: `/setrole 123456789 executor`", parse_mode="Markdown")


@router.message(F.text == "📈 Статистика")
async def admin_stats(message: Message):
    user = await get_user_by_telegram(message.from_user.id)
    
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет доступа к этой функции.")
        return
    
    stats = await get_system_stats()
    
    text = (
        f"📊 **Статистика системы**\n\n"
        f"👥 **Пользователи:**\n"
        f"   • Всего: {stats['total_users']}\n"
        f"   • Клиенты: {stats['clients_count']}\n"
        f"   • Исполнители: {stats['executors_count']}\n"
        f"   • Администраторы: {stats['admins_count']}\n\n"
        f"📋 **Заявки:**\n"
        f"   • Всего: {stats['total_requests']}\n"
        f"   • 🆕 Новые: {stats['new_requests']}\n"
        f"   • 🔧 В работе: {stats['in_work_requests']}\n"
        f"   • ✅ Выполнены: {stats['completed_requests']}\n"
        f"   • 🔄 Продлены: {stats['extended_requests']}\n"
        f"   • ❌ Отменены: {stats['cancelled_requests']}\n\n"
        f"🏆 **Топ исполнителей:**\n"
    )
    
    for ex in stats['top_executors']:
        text += f"   • {ex['full_name']}: {ex['completed_count']} заявок\n"
    
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "⚙️ Назначить исполнителя")
async def admin_force_assign(message: Message, state: FSMContext):
    user = await get_user_by_telegram(message.from_user.id)
    
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет доступа к этой функции.")
        return
    
    requests = await get_all_requests_with_filters()
    new_requests = [r for r in requests if r['status'] == 'new']
    
    if not new_requests:
        await message.answer("📭 Нет новых заявок для назначения.")
        return
    
    text = "📋 **Заявки без исполнителя:**\n\n"
    for req in new_requests:
        text += f"🔹 Заявка #{req['id']}: {req['description'][:80]}...\n"
    
    text += "\n➡️ Введите `/assign НомерЗаявки TelegramID` для назначения\n"
    text += "Пример: `/assign 1 123456789`"
    
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text.startswith("/assign"))
async def admin_assign_command(message: Message):
    user = await get_user_by_telegram(message.from_user.id)
    
    if not user or (user['role'] != 'admin' and user['role'] != '100ball'):
        await message.answer("❌ У вас нет доступа к этой функции.")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Формат: `/assign request_id telegram_id`\nПример: `/assign 1 123456789`", parse_mode="Markdown")
        return
    
    try:
        request_id = int(parts[1])
        executor_telegram = int(parts[2])
    except ValueError:
        await message.answer("❌ Номера должны быть числами.")
        return
    
    result = await admin_force_assign_executor(request_id, executor_telegram)
    
    if result:
        await message.answer(f"✅ Исполнитель назначен на заявку #{request_id}!")
        
        try:
            await message.bot.send_message(
                executor_telegram,
                f"🔔 **Вам назначена новая заявка!**\n\n"
                f"📋 Заявка #{request_id}\n"
                f"📝 {result['description'][:100]}"
            )
        except:
            pass
    else:
        await message.answer(f"❌ Не удалось назначить. Проверьте ID заявки и исполнителя.")