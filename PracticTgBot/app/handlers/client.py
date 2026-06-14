from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import (
    get_user_by_telegram, create_request, add_media, get_user_requests,
    cancel_request, get_pending_extensions, approve_extension, reject_extension,
    get_request_media, get_request_by_id
)
from app.keyboards import main_menu, back_to_menu_button
from app.utils import save_media_file
import os

router = Router()

class CreateRequest(StatesGroup):
    waiting_for_description = State()
    waiting_for_media = State()


@router.message(F.text == "📝 Создать заявку")
async def create_request_start(message: Message, state: FSMContext):
    await message.answer(
        "📝 **Создание новой заявки**\n\n"
        "Опишите проблему с пожарной сигнализацией:",
        parse_mode="Markdown",
        reply_markup=back_to_menu_button()
    )
    await state.set_state(CreateRequest.waiting_for_description)


@router.message(CreateRequest.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    if message.text == "🔙 Назад в меню":
        user = await get_user_by_telegram(message.from_user.id)
        await message.answer("Операция отменена.", reply_markup=main_menu(user['role']))
        await state.clear()
        return
    
    if len(message.text) < 10:
        await message.answer("❌ Описание слишком короткое. Напишите подробнее (минимум 10 символов):")
        return
    
    await state.update_data(description=message.text)
    await message.answer(
        "📎 Теперь отправьте **фото или видео** (до 5 файлов).\n\n"
        "Когда закончите, нажмите кнопку '✅ Готово'",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="✅ Готово")], [KeyboardButton(text="🔙 Назад в меню")]],
            resize_keyboard=True
        )
    )
    await state.set_state(CreateRequest.waiting_for_media)


@router.message(CreateRequest.waiting_for_media, F.photo)
async def process_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    media_files = data.get('media_files', [])
    
    if len(media_files) >= 5:
        await message.answer("⚠️ Вы уже загрузили 5 файлов. Нажмите '✅ Готово' для завершения.")
        return
    
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_data = await message.bot.download_file(file.file_path)
    
    temp_path = await save_media_file(file_data.read(), 0, "photo", "jpg")
    media_files.append(temp_path)
    
    await state.update_data(media_files=media_files)
    await message.answer(f"📸 Фото сохранено ({len(media_files)}/5). Отправьте еще или нажмите '✅ Готово'")


@router.message(CreateRequest.waiting_for_media, F.video)
async def process_video(message: Message, state: FSMContext):
    data = await state.get_data()
    media_files = data.get('media_files', [])
    
    if len(media_files) >= 5:
        await message.answer("⚠️ Вы уже загрузили 5 файлов. Нажмите '✅ Готово' для завершения.")
        return
    
    video = message.video
    file = await message.bot.get_file(video.file_id)
    file_data = await message.bot.download_file(file.file_path)
    
    temp_path = await save_media_file(file_data.read(), 0, "video", "mp4")
    media_files.append(temp_path)
    
    await state.update_data(media_files=media_files)
    await message.answer(f"🎥 Видео сохранено ({len(media_files)}/5). Отправьте еще или нажмите '✅ Готово'")


@router.message(CreateRequest.waiting_for_media, F.text == "✅ Готово")
async def finish_request(message: Message, state: FSMContext):
    data = await state.get_data()
    user = await get_user_by_telegram(message.from_user.id)
    
    if not user:
        await message.answer("❌ Ошибка: пользователь не найден")
        await state.clear()
        return
    
    request = await create_request(user['id'], data['description'])
    
    for i, old_path in enumerate(data.get('media_files', [])):
        new_path = old_path.replace("req_0_", f"req_{request['id']}_")
        try:
            os.rename(old_path, new_path)
            await add_media(request['id'], new_path, "photo" if "photo" in new_path else "video")
        except Exception as e:
            print(f"Error saving media: {e}")
    
    await message.answer(
        f"✅ **Заявка #{request['id']} успешно создана!**\n\n"
        f"📝 Описание: {request['description'][:200]}\n"
        f"🔄 Статус: {request['status']}\n\n"
        f"Ожидайте назначения исполнителя.",
        parse_mode="Markdown",
        reply_markup=main_menu('client')
    )
    await state.clear()




@router.message(F.text == "📋 Мои заявки")
async def my_requests(message: Message):
    requests = await get_user_requests(message.from_user.id)
    
    if not requests:
        await message.answer("📭 У вас пока нет заявок.\nСоздайте новую через меню.")
        return
    
    await message.answer(
        "📋 **Ваши заявки:**\n\n"
        "• Для просмотра файлов введите: `/номер`\n"
        "• Для отмены заявки введите: `/cancel номер`",
        parse_mode="Markdown"
    )
    
    for req in requests:
        status_emoji = {
            'new': '🆕', 'in_work': '🔧', 'completed': '✅', 
            'extended': '🔄', 'cancelled': '❌'
        }.get(req['status'], '❓')
        
        media = await get_request_media(req['id'])
        media_text = f"📎 Файлов: {len(media)}" if media else "📎 Нет файлов"
        
        await message.answer(
            f"{status_emoji} **Заявка #{req['id']}**\n"
            f"📝 {req['description'][:150]}\n"
            f"🔄 Статус: {req['status']}\n"
            f"{media_text}\n"
            f"📅 Создана: {req['created_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📸 Просмотр файлов: `/{req['id']}`\n"
            f"🗑 Отмена заявки: `/cancel {req['id']}`",
            parse_mode="Markdown"
        )


@router.message(F.text.regexp(r'^/\d+$'))
async def show_request_files(message: Message):
    """Показывает файлы заявки по команде /номер"""
    request_id = int(message.text[1:])
    user = await get_user_by_telegram(message.from_user.id)
    user_requests = await get_user_requests(message.from_user.id)
    user_request_ids = [r['id'] for r in user_requests]
    
    if request_id not in user_request_ids:
        await message.answer("❌ У вас нет доступа к этой заявке или она не существует.")
        return
    
    request = await get_request_by_id(request_id)
    media_files = await get_request_media(request_id)
    
    if not media_files:
        await message.answer(f"📭 В заявке #{request_id} нет прикрепленных файлов.")
        return
    
    await message.answer(f"📎 **Файлы заявки #{request_id}:**\n\nВсего файлов: {len(media_files)}", parse_mode="Markdown")
    
    for i, media in enumerate(media_files, 1):
        file_path = media['file_path']
        
        if not os.path.exists(file_path):
            await message.answer(f"❌ Файл {i} не найден на сервере.")
            continue
        
        try:
            if media['media_type'] == 'photo' or file_path.endswith(('.jpg', '.png', '.jpeg', '.gif')):
                photo = FSInputFile(file_path)
                await message.answer_photo(photo, caption=f"📸 Файл #{i} заявки #{request_id}")
            elif media['media_type'] == 'video' or file_path.endswith(('.mp4', '.avi', '.mov')):
                video = FSInputFile(file_path)
                await message.answer_video(video, caption=f"🎥 Файл #{i} заявки #{request_id}")
            else:
                doc = FSInputFile(file_path)
                await message.answer_document(doc, caption=f"📄 Файл #{i} заявки #{request_id}")
        except Exception as e:
            await message.answer(f"❌ Ошибка при отправке файла {i}: {str(e)}")



@router.message(F.text.lower().startswith("/cancel"))
async def cancel_request_command(message: Message):
    """Отмена заявки по команде /cancel, /cancel 1 или /cancel1"""
    text = message.text.strip()
    if text.lower().startswith("/cancel"):
        after_cancel = text[7:].strip()
        if not after_cancel:
            await message.answer(
                "❌ **Укажите номер заявки для отмены:**\n\n"
                "Примеры:\n"
                "• `/cancel 1`\n"
                "• `/cancel1`\n\n"
                "Или нажмите кнопку '❌ Отменить заявку' для просмотра списка.",
                parse_mode="Markdown"
            )
            return
        request_id_str = after_cancel.replace(" ", "")
        if not request_id_str.isdigit():
            await message.answer(f"❌ Некорректный номер заявки: '{after_cancel}'\nПример: `/cancel 1`", parse_mode="Markdown")
            return
        
        request_id = int(request_id_str)
        
    else:
        await message.answer("❌ Неверная команда. Используйте: `/cancel 1`", parse_mode="Markdown")
        return
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("❌ Пользователь не найден. Нажмите /start")
        return
    request = await get_request_by_id(request_id)
    if not request:
        await message.answer(f"❌ Заявка #{request_id} не найдена.")
        return
    if request['client_id'] != user['id']:
        await message.answer(f"❌ Заявка #{request_id} не принадлежит вам.")
        return
    

    if request['status'] not in ['new', 'in_work']:
        await message.answer(
            f"❌ Заявка #{request_id} не может быть отменена.\n"
            f"Текущий статус: {request['status']}\n\n"
            "Отменить можно только заявки в статусе 'new' или 'in_work'."
        )
        return
    result = await cancel_request(request_id, user['id'])
    
    if result:
        await message.answer(
            f"✅ **Заявка #{request_id} успешно отменена!**\n\n"
            f"📝 {request['description'][:100]}",
            parse_mode="Markdown",
            reply_markup=main_menu('client')
        )
    else:
        await message.answer(f"❌ Не удалось отменить заявку #{request_id}.")

@router.message(F.text == "❌ Отменить заявку")
async def cancel_request_start(message: Message):
    """Показывает активные заявки для отмены"""
    requests = await get_user_requests(message.from_user.id)
    active_requests = [r for r in requests if r['status'] in ['new', 'in_work']]
    
    if not active_requests:
        await message.answer("📭 Нет активных заявок для отмены.")
        return
    
    text = "🗑 **Ваши активные заявки:**\n\n"
    for req in active_requests:
        media = await get_request_media(req['id'])
        media_text = f" (📎 {len(media)} файлов)" if media else ""
        text += f"🔹 Заявка **#{req['id']}** - {req['status']}{media_text}\n"
        text += f"   📝 {req['description'][:80]}...\n\n"
    
    text += "➡️ **Для отмены введите команду:**\n"
    text += "`/cancel номер_заявки`\n\n"
    text += "Пример: `/cancel 1`"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=back_to_menu_button())

@router.message(F.text == "🔄 Подтвердить продление")
async def list_pending_extensions(message: Message):
    extensions = await get_pending_extensions(message.from_user.id)
    
    if not extensions:
        await message.answer("📭 Нет ожидающих запросов на продление.")
        return
    
    for ext in extensions:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"client_ext_approve_{ext['id']}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"client_ext_reject_{ext['id']}")
            ]
        ])
        
        media = await get_request_media(ext['request_id'])
        media_text = f"\n📎 Файлов: {len(media)}" if media else ""
        
        await message.answer(
            f"🔄 **Запрос на продление**\n\n"
            f"📋 Заявка #{ext['request_id']}\n"
            f"📝 {ext['description'][:100]}{media_text}\n"
            f"📅 Запрошено дней: {ext['requested_days']}\n"
            f"👤 Исполнитель: {ext['executor_name']}\n\n"
            f"📸 Просмотр файлов: `/{ext['request_id']}`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )


@router.callback_query(F.data.startswith("client_ext_approve_"))
async def approve_extension_callback(callback: CallbackQuery):
    extension_id = int(callback.data.split("_")[3])
    result = await approve_extension(extension_id)
    
    if result:
        await callback.answer("✅ Продление подтверждено!")
        await callback.message.edit_text(f"✅ Продление подтверждено!\nЗаявка #{result['request_id']}: статус 'extended'")
    else:
        await callback.answer("❌ Ошибка при подтверждении", show_alert=True)


@router.callback_query(F.data.startswith("client_ext_reject_"))
async def reject_extension_callback(callback: CallbackQuery):
    extension_id = int(callback.data.split("_")[3])
    result = await reject_extension(extension_id)
    
    if result:
        await callback.answer("❌ Продление отклонено!")
        await callback.message.edit_text(f"❌ Продление отклонено.\nЗаявка #{result['request_id']} остается в работе.")
    else:
        await callback.answer("❌ Ошибка при отклонении", show_alert=True)