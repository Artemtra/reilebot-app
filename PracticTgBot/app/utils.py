import os
import aiofiles
from pathlib import Path
from app.config import config
os.makedirs(config.MEDIA_ROOT, exist_ok=True)

async def save_media_file(file_data: bytes, request_id: int, file_type: str, extension: str = "jpg") -> str:
    """
    Сохраняет медиафайл на диск
    
    Args:
        file_data: содержимое файла в байтах
        request_id: ID заявки
        file_type: тип файла (photo, video, report_photo)
        extension: расширение файла (jpg, mp4)
    
    Returns:
        str: путь к сохраненному файлу
    """
    import uuid
    unique_id = uuid.uuid4().hex[:8]
    filename = f"req_{request_id}_{file_type}_{unique_id}.{extension}"
    filepath = os.path.join(config.MEDIA_ROOT, filename)
    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(file_data)
    
    return filepath

async def delete_media_file(filepath: str):
    """Удаляет медиафайл с диска"""
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False

def get_file_extension(content_type: str, filename: str = None) -> str:
    """Определяет расширение файла по content-type или имени файла"""
    if content_type:
        if content_type.startswith("image/"):
            ext_map = {
                "image/jpeg": "jpg",
                "image/jpg": "jpg",
                "image/png": "png",
                "image/gif": "gif",
                "image/webp": "webp"
            }
            return ext_map.get(content_type, "jpg")
        elif content_type.startswith("video/"):
            ext_map = {
                "video/mp4": "mp4",
                "video/quicktime": "mov",
                "video/x-msvideo": "avi"
            }
            return ext_map.get(content_type, "mp4")
    if filename:
        ext = filename.split('.')[-1].lower()
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            return 'jpg' if ext == 'jpeg' else ext
        elif ext in ['mp4', 'mov', 'avi', 'mkv']:
            return 'mp4' if ext not in ['mov', 'avi', 'mkv'] else ext
    
    return "jpg"  # расширение по умолчанию

def get_media_type(content_type: str, filename: str = None) -> str:
    """Определяет тип медиа (photo или video)"""
    if content_type:
        if content_type.startswith("image/"):
            return "photo"
        elif content_type.startswith("video/"):
            return "video"
    
    if filename:
        ext = filename.split('.')[-1].lower()
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']:
            return "photo"
        elif ext in ['mp4', 'mov', 'avi', 'mkv', 'wmv']:
            return "video"
    
    return "photo"  # тип по умолчанию