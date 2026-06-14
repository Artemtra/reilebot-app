from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import asyncpg
import os
from datetime import datetime

from app.database import get_pool, assign_executor, complete_request, request_extension, get_user_by_telegram
from app.config import config
from app.utils import save_media_file, get_media_type, get_file_extension

# Создаем экземпляр FastAPI приложения
app = FastAPI(
    title="PS Service API",
    description="API для обслуживания пожарной сигнализации",
    version="1.0.0"
)

# Добавляем CORS для ngrok
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# ========== Аутентификация ==========

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Проверка токена доступа к API"""
    if credentials.credentials != config.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"token": credentials.credentials}


# ========== ЛОГИ ==========

async def log_action(user_id: int, action: str, details: str = None):
    """Запись действия в лог"""
    try:
        pool = await get_pool()
        await pool.execute(
            "INSERT INTO logs (user_id, action, details) VALUES ($1, $2, $3)",
            user_id, action, details
        )
    except Exception as e:
        print(f"Log error: {e}")


async def get_user_id_by_telegram(telegram_id: int):
    """Получить id пользователя по telegram_id"""
    pool = await get_pool()
    user = await pool.fetchrow("SELECT id FROM users WHERE telegram_id = $1", telegram_id)
    return user['id'] if user else None


# ========== Пользователи ==========

@app.post("/api/users", dependencies=[Depends(verify_token)])
async def create_user(
    telegram_id: int,
    role: str,
    full_name: Optional[str] = None
):
    """Создание нового пользователя"""
    pool = await get_pool()
    try:
        result = await pool.fetchrow(
            "INSERT INTO users (telegram_id, role, full_name) VALUES ($1, $2, $3) RETURNING *",
            telegram_id, role, full_name
        )
        # Лог
        await log_action(result['id'], "Регистрация", f"Роль: {role}")
        return dict(result)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=400, detail="User already exists")


@app.get("/api/users/{telegram_id}", dependencies=[Depends(verify_token)])
async def get_user(telegram_id: int):
    """Получение данных пользователя по Telegram ID"""
    pool = await get_pool()
    user = await pool.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(user)


@app.get("/api/users", dependencies=[Depends(verify_token)])
async def get_all_users(
    role: Optional[str] = Query(None, description="Фильтр по роли (client/executor/admin)")
):
    """Получение списка всех пользователей"""
    pool = await get_pool()
    if role:
        users = await pool.fetch("SELECT * FROM users WHERE role = $1 ORDER BY id", role)
    else:
        users = await pool.fetch("SELECT * FROM users ORDER BY id")
    return [dict(user) for user in users]


@app.put("/api/users/{telegram_id}/role", dependencies=[Depends(verify_token)])
async def update_user_role(telegram_id: int, role: str):
    """Изменение роли пользователя"""
    pool = await get_pool()
    
    valid_roles = ['client', 'executor', 'admin', '100ball']
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Use: {', '.join(valid_roles)}")
    
    user = await pool.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    old_role = user['role']
    result = await pool.fetchrow(
        "UPDATE users SET role = $1 WHERE telegram_id = $2 RETURNING *",
        role, telegram_id
    )
    
    # Лог
    await log_action(result['id'], "Смена роли", f"{old_role} → {role}")
    
    return dict(result)


# ========== Заявки ==========

@app.post("/api/requests", dependencies=[Depends(verify_token)])
async def create_request_endpoint(
    client_telegram_id: int,
    description: str
):
    """Создание новой заявки"""
    pool = await get_pool()
    user = await pool.fetchrow("SELECT id FROM users WHERE telegram_id = $1", client_telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="Client not found")
    
    result = await pool.fetchrow(
        "INSERT INTO requests (client_id, description) VALUES ($1, $2) RETURNING *",
        user['id'], description
    )
    
    # Лог
    await log_action(user['id'], "Создание заявки", f"Заявка #{result['id']}: {description[:100]}")
    
    return dict(result)


@app.get("/api/requests", dependencies=[Depends(verify_token)])
async def get_all_requests(
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    client_telegram_id: Optional[int] = Query(None, description="Фильтр по клиенту"),
    executor_telegram_id: Optional[int] = Query(None, description="Фильтр по исполнителю")
):
    """Получение всех заявок с фильтрацией"""
    pool = await get_pool()
    
    query = """
        SELECT r.*, 
               c.full_name as client_name,
               c.telegram_id as client_telegram_id,
               e.full_name as executor_name,
               e.telegram_id as executor_telegram_id
        FROM requests r
        LEFT JOIN users c ON r.client_id = c.id
        LEFT JOIN users e ON r.executor_id = e.id
        WHERE 1=1
    """
    params = []
    param_index = 1
    
    if status:
        query += f" AND r.status = ${param_index}"
        params.append(status)
        param_index += 1
    if client_telegram_id:
        query += f" AND c.telegram_id = ${param_index}"
        params.append(client_telegram_id)
        param_index += 1
    if executor_telegram_id:
        query += f" AND e.telegram_id = ${param_index}"
        params.append(executor_telegram_id)
    
    query += " ORDER BY r.created_at DESC"
    
    rows = await pool.fetch(query, *params)
    return [dict(row) for row in rows]


@app.get("/api/requests/{request_id}", dependencies=[Depends(verify_token)])
async def get_request(request_id: int):
    """Получение конкретной заявки по ID"""
    pool = await get_pool()
    row = await pool.fetchrow("""
        SELECT r.*, 
               c.full_name as client_name,
               c.telegram_id as client_telegram_id,
               e.full_name as executor_name,
               e.telegram_id as executor_telegram_id
        FROM requests r
        LEFT JOIN users c ON r.client_id = c.id
        LEFT JOIN users e ON r.executor_id = e.id
        WHERE r.id = $1
    """, request_id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    return dict(row)


@app.put("/api/requests/assign", dependencies=[Depends(verify_token)])
async def assign_executor_endpoint(
    request_id: int,
    executor_telegram_id: int
):
    """Назначение исполнителя на заявку"""
    result = await assign_executor(request_id, executor_telegram_id)
    if not result:
        raise HTTPException(status_code=404, detail="Request or executor not found")
    
    # Лог
    executor = await get_user_by_telegram(executor_telegram_id)
    if executor:
        await log_action(executor['id'], "Назначение исполнителя", f"Заявка #{request_id}")
    
    return dict(result)

@app.put("/api/requests/{request_id}/status", dependencies=[Depends(verify_token)])
async def update_request_status(request_id: int, status: str):
    """Изменение статуса заявки"""
    pool = await get_pool()
    
    valid_statuses = ['new', 'in_work', 'completed', 'extended', 'cancelled']
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use: {', '.join(valid_statuses)}")
    
    try:
        # Проверяем существование заявки
        req = await pool.fetchrow("SELECT * FROM requests WHERE id = $1", request_id)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        
        # Обновляем статус
        result = await pool.fetchrow(
            "UPDATE requests SET status = $1 WHERE id = $2 RETURNING *",
            status, request_id
        )
        
        return dict(result)
        
    except Exception as e:
        print(f"Error updating status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/requests/{request_id}", dependencies=[Depends(verify_token)])
async def delete_request(request_id: int):
    """Удаление заявки"""
    pool = await get_pool()
    
    # Получаем информацию для лога
    req = await pool.fetchrow("SELECT client_id FROM requests WHERE id = $1", request_id)
    
    result = await pool.execute("DELETE FROM requests WHERE id = $1", request_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Лог
    if req:
        await log_action(req['client_id'], "Удаление заявки", f"Заявка #{request_id}")
    
    return {"message": "Request deleted successfully", "success": True}


@app.post("/api/requests/{request_id}/media", dependencies=[Depends(verify_token)])
async def upload_media(
    request_id: int, 
    file: UploadFile = File(...)
):
    """Загрузка фото/видео для заявки"""
    pool = await get_pool()
    req = await pool.fetchrow("SELECT id, client_id FROM requests WHERE id = $1", request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    file_data = await file.read()
    media_type = get_media_type(file.content_type, file.filename)
    extension = get_file_extension(file.content_type, file.filename)
    
    file_path = await save_media_file(file_data, request_id, media_type, extension)
    
    result = await pool.fetchrow(
        "INSERT INTO request_media (request_id, file_path, media_type) VALUES ($1, $2, $3) RETURNING *",
        request_id, file_path, media_type
    )
    
    # Лог
    await log_action(req['client_id'], "Загрузка файла", f"Заявка #{request_id}, тип: {media_type}")
    
    return dict(result)


@app.get("/api/requests/{request_id}/media", dependencies=[Depends(verify_token)])
async def get_request_media(request_id: int):
    """Получение всех медиафайлов заявки"""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM request_media WHERE request_id = $1 ORDER BY id",
        request_id
    )
    return [dict(row) for row in rows]


@app.get("/api/requests/{request_id}/media/{media_id}")
async def get_media_file(request_id: int, media_id: int):
    """Получение файла по ID"""
    from fastapi.responses import FileResponse
    
    pool = await get_pool()
    media = await pool.fetchrow(
        "SELECT * FROM request_media WHERE id = $1 AND request_id = $2", 
        media_id, request_id
    )
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    return FileResponse(media['file_path'])


# ========== Отчеты ==========

@app.post("/api/reports", dependencies=[Depends(verify_token)])
async def create_report(
    request_id: int,
    executor_telegram_id: int,
    text_report: str
):
    """Создание отчета по выполненной работе"""
    result = await complete_request(request_id, executor_telegram_id, text_report)
    if not result:
        raise HTTPException(status_code=404, detail="Request or executor not found")
    
    # Лог
    executor = await get_user_by_telegram(executor_telegram_id)
    if executor:
        await log_action(executor['id'], "Отчет", f"Заявка #{request_id}")
    
    return dict(result)


@app.get("/api/reports/request/{request_id}", dependencies=[Depends(verify_token)])
async def get_reports_by_request(request_id: int):
    """Получение всех отчетов по заявке"""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM reports WHERE request_id = $1 ORDER BY created_at DESC",
        request_id
    )
    return [dict(row) for row in rows]


# ========== Продления ==========

@app.post("/api/extensions", dependencies=[Depends(verify_token)])
async def request_extension_endpoint(
    request_id: int,
    executor_telegram_id: int,
    days: int
):
    """Запрос на продление срока выполнения"""
    result = await request_extension(request_id, executor_telegram_id, days)
    if not result:
        raise HTTPException(status_code=404, detail="Request or executor not found")
    
    # Лог
    executor = await get_user_by_telegram(executor_telegram_id)
    if executor:
        await log_action(executor['id'], "Запрос продления", f"Заявка #{request_id}, на {days} дней")
    
    return dict(result)


@app.get("/api/extensions/request/{request_id}", dependencies=[Depends(verify_token)])
async def get_extensions_by_request(request_id: int):
    """Получение всех запросов на продление по заявке"""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM extensions WHERE request_id = $1 ORDER BY created_at DESC",
        request_id
    )
    return [dict(row) for row in rows]


# ========== Статистика ==========

@app.get("/api/stats", dependencies=[Depends(verify_token)])
async def get_statistics():
    """Получение статистики по системе"""
    pool = await get_pool()
    
    stats = {}
    stats['total_users'] = await pool.fetchval("SELECT COUNT(*) FROM users")
    stats['total_requests'] = await pool.fetchval("SELECT COUNT(*) FROM requests")
    stats['new_requests'] = await pool.fetchval("SELECT COUNT(*) FROM requests WHERE status = 'new'")
    stats['in_work_requests'] = await pool.fetchval("SELECT COUNT(*) FROM requests WHERE status = 'in_work'")
    stats['completed_requests'] = await pool.fetchval("SELECT COUNT(*) FROM requests WHERE status = 'completed'")
    stats['clients_count'] = await pool.fetchval("SELECT COUNT(*) FROM users WHERE role = 'client'")
    stats['executors_count'] = await pool.fetchval("SELECT COUNT(*) FROM users WHERE role = 'executor'")
    stats['admins_count'] = await pool.fetchval("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    
    return stats


# ========== ЛОГИ ==========

@app.get("/api/logs", dependencies=[Depends(verify_token)])
async def get_logs():
    """Получение логов (только для админа)"""
    pool = await get_pool()
    logs = await pool.fetch("""
        SELECT l.*, u.full_name 
        FROM logs l 
        LEFT JOIN users u ON l.user_id = u.id 
        ORDER BY l.created_at DESC 
        LIMIT 200
    """)
    return [dict(log) for log in logs]


# ========== Health check ==========

@app.get("/health")
async def health_check():
    """Проверка работоспособности API"""
    try:
        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        return {"message": "API is healthy", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")


# ========== СТАТИЧЕСКИЕ ФАЙЛЫ (index.html) ==========

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")