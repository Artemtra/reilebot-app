from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu(role: str):
    """Главное меню в зависимости от роли"""
    
    if role == "client":
        buttons = [
            [KeyboardButton(text="📝 Создать заявку")],
            [KeyboardButton(text="📋 Мои заявки")],
            [KeyboardButton(text="🔄 Подтвердить продление")],
            [KeyboardButton(text="❌ Отменить заявку")]
        ]
    elif role == "executor":
        buttons = [
            [KeyboardButton(text="📋 Новые заявки")],
            [KeyboardButton(text="✅ Мои активные заявки")],
            [KeyboardButton(text="📊 История выполненных")],
            [KeyboardButton(text="🔄 Запросить продление")]
        ]
    elif role == "admin" or role == "100ball":
        buttons = [
            [KeyboardButton(text="📊 Все заявки")],
            [KeyboardButton(text="👥 Управление пользователями")],
            [KeyboardButton(text="📈 Статистика")],
            [KeyboardButton(text="⚙️ Назначить исполнителя")]
        ]
    else:
        buttons = [
            [KeyboardButton(text="📝 Создать заявку")],
            [KeyboardButton(text="📋 Мои заявки")]
        ]
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def back_to_menu_button():
    """Кнопка возврата в главное меню"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад в меню")]],
        resize_keyboard=True
    )

def take_request_inline(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Взять в работу", callback_data=f"take_{request_id}")]
    ])

def extension_inline(extension_id: int, request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"ext_approve_{extension_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"ext_reject_{extension_id}")
        ]
    ])

def admin_actions_inline(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 Назначить исполнителя", callback_data=f"admin_assign_{request_id}"),
            InlineKeyboardButton(text="📝 Сменить статус", callback_data=f"admin_status_{request_id}")
        ],
        [InlineKeyboardButton(text="❌ Удалить заявку", callback_data=f"admin_delete_{request_id}")]
    ])