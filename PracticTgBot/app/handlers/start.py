from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.database import get_user_by_telegram, create_user, update_user_role, get_all_users
from app.keyboards import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = await get_user_by_telegram(message.from_user.id)
    
    if user:
        role_display = "100бальница" if user['role'] == "100ball" else user['role']
        
        await message.answer(
            f"👋 С возвращением, {user['full_name'] or message.from_user.full_name}!\n"
            f"🎭 Ваша роль: {role_display}\n\n"
            f"Используйте кнопки ниже для навигации:",
            reply_markup=main_menu(user['role'])
        )
    else:
        user = await create_user(
            message.from_user.id, 
            "client", 
            message.from_user.full_name
        )
        
        await message.answer(
            f"👋 **Добро пожаловать в систему!**\n\n"
            f"✅ Вы зарегистрированы как **Клиент**.\n\n"
            f"📝 Теперь вы можете создавать заявки.\n\n"
            f"🔄 Если вам нужна другая роль, обратитесь к администратору.\n\n"
            f"Нажмите /start в любое время для возврата в главное меню.",
            parse_mode="Markdown",
            reply_markup=main_menu('client')
        )


@router.message(F.text == "👥 Управление пользователями")
async def admin_user_list(message: Message):
    user = await get_user_by_telegram(message.from_user.id)
    
    if not user or (user['role'] != 'admin' and user['role'] != '100ball'):
        await message.answer("❌ У вас нет доступа к этой функции.")
        return
    
    users = await get_all_users()
    
    if not users:
        await message.answer("📭 Нет зарегистрированных пользователей.")
        return
    
    text = "👥 **Список пользователей:**\n\n"
    for u in users:
        role_display = "100бальница" if u['role'] == "100ball" else u['role']
        role_emoji = {
            'client': '👤',
            'executor': '🔧', 
            'admin': '👑',
            '100ball': '🎓'
        }.get(u['role'], '❓')
        
        text += f"{role_emoji} **{u['full_name'] or u['telegram_id']}**\n"
        text += f"   ID: `{u['telegram_id']}`\n"
        text += f"   Роль: {role_display}\n\n"
    
    text += "📝 **Для смены роли введите команду:**\n"
    text += "`/setrole TelegramID новая_роль`\n\n"
    text += "Доступные роли: `client`, `executor`, `admin`\n\n"
    text += "Пример: `/setrole 123456789 executor`"
    
    await message.answer(text, parse_mode="Markdown")

@router.message(lambda message: message.text and message.text.startswith('/setrole'))
async def admin_set_role(message: Message):
    """Обработчик команды /setrole TelegramID новая_роль"""
    user = await get_user_by_telegram(message.from_user.id)
    
    if not user or (user['role'] != 'admin' and user['role'] != '100ball'):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    parts = message.text.split()
    
    if len(parts) != 3:
        await message.answer(
            "❌ **Неверный формат команды!**\n\n"
            "Правильный формат:\n"
            "`/setrole TelegramID новая_роль`\n\n"
            "**Примеры:**\n"
            "• `/setrole 123456789 client` - назначить клиента\n"
            "• `/setrole 123456789 executor` - назначить исполнителя\n"
            "• `/setrole 123456789 admin` - назначить администратора\n"
            "• `/setrole 123456789 100ball` - назначить 100бальницу\n\n"
            "Доступные роли: `client`, `executor`, `admin`, `100ball`",
            parse_mode="Markdown"
        )
        return
    
    try:
        target_telegram_id = int(parts[1])
        new_role = parts[2].lower()
        
        valid_roles = ['client', 'executor', 'admin', '100ball']
        if new_role not in valid_roles:
            await message.answer(
                f"❌ Недопустимая роль: `{new_role}`\n\n"
                f"Доступные роли: `client`, `executor`, `admin`, `100ball`",
                parse_mode="Markdown"
            )
            return
        target_user = await get_user_by_telegram(target_telegram_id)
        
        if not target_user:
            await message.answer(
                f"❌ Пользователь с Telegram ID `{target_telegram_id}` не найден.\n\n"
                f"Убедитесь, что пользователь отправил команду `/start` боту хотя бы раз.",
                parse_mode="Markdown"
            )
            return
        result = await update_user_role(target_telegram_id, new_role)
        
        if result:
            role_display = "100бальница" if new_role == "100ball" else new_role
            
            await message.answer(
                f"✅ **Роль пользователя изменена!**\n\n"
                f"👤 Пользователь: {target_user['full_name'] or target_telegram_id}\n"
                f"🆔 Telegram ID: `{target_telegram_id}`\n"
                f"🎭 Старая роль: {target_user['role']}\n"
                f"🎭 Новая роль: **{role_display}**",
                parse_mode="Markdown"
            )
            try:
                await message.bot.send_message(
                    target_telegram_id,
                    f"🔔 **Ваша роль изменена!**\n\n"
                    f"🎭 Новая роль: **{role_display}**\n\n"
                    f"Нажмите /start для обновления меню."
                )
            except Exception as e:
                print(f"Не удалось отправить уведомление: {e}")
        else:
            await message.answer(f"❌ Не удалось обновить роль.")
            
    except ValueError:
        await message.answer(
            "❌ **Ошибка!** Telegram ID должен быть числом.\n\n"
            "Пример: `/setrole 123456789 executor`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка: {str(e)}")