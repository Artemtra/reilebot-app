import asyncpg
from app.config import config

_pool = None

# ========== ОСНОВНЫЕ ФУНКЦИИ ПОДКЛЮЧЕНИЯ ==========

async def init_db():
    """Инициализация пула соединений с БД"""
    global _pool
    try:
        _pool = await asyncpg.create_pool(
            config.DB_DSN,
            min_size=1,
            max_size=10,
            command_timeout=60
        )
        print("✅ Database connection pool created")
        return _pool
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        raise

async def get_pool():
    """Получить пул соединений"""
    global _pool
    if _pool is None:
        await init_db()
    return _pool

async def close_db():
    """Закрыть пул соединений"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        print("✅ Database connection pool closed")

# ========== ФУНКЦИИ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ==========

async def get_user_by_telegram(telegram_id: int):
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)

async def create_user(telegram_id: int, role: str, full_name: str = None):
    pool = await get_pool()
    return await pool.fetchrow(
        "INSERT INTO users (telegram_id, role, full_name) VALUES ($1, $2, $3) RETURNING *",
        telegram_id, role, full_name
    )

async def get_all_users_with_stats():
    """Получить всех пользователей со статистикой"""
    pool = await get_pool()
    return await pool.fetch("""
        SELECT 
            u.id, u.telegram_id, u.role, u.full_name, u.created_at,
            COUNT(DISTINCT r.id) as total_requests,
            COUNT(DISTINCT CASE WHEN r.status = 'completed' THEN r.id END) as completed_requests
        FROM users u
        LEFT JOIN requests r ON r.client_id = u.id OR r.executor_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """)

# ========== ФУНКЦИИ ДЛЯ ЗАЯВОК ==========

async def create_request(client_id: int, description: str):
    pool = await get_pool()
    return await pool.fetchrow(
        "INSERT INTO requests (client_id, description) VALUES ($1, $2) RETURNING *",
        client_id, description
    )

async def add_media(request_id: int, file_path: str, media_type: str):
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO request_media (request_id, file_path, media_type) VALUES ($1, $2, $3)",
        request_id, file_path, media_type
    )

async def get_user_requests(telegram_id: int):
    pool = await get_pool()
    user = await get_user_by_telegram(telegram_id)
    if not user:
        return []
    return await pool.fetch(
        "SELECT r.*, u.full_name as client_name FROM requests r "
        "LEFT JOIN users u ON r.client_id = u.id "
        "WHERE r.client_id = $1 ORDER BY r.created_at DESC",
        user['id']
    )
async def update_user_role(telegram_id: int, new_role: str):
    """Обновить роль пользователя (только для администратора)"""
    pool = await get_pool()
    return await pool.fetchrow(
        "UPDATE users SET role = $1 WHERE telegram_id = $2 RETURNING *",
        new_role, telegram_id
    )


async def get_all_users():
    """Получить всех пользователей"""
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM users ORDER BY created_at DESC")

async def get_request_by_id(request_id: int):
    """Получить заявку по ID"""
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM requests WHERE id = $1", request_id)

async def cancel_request(request_id: int, client_id: int):
    """Отменить заявку (только если она в статусе new)"""
    pool = await get_pool()
    return await pool.fetchrow(
        "UPDATE requests SET status = 'cancelled' WHERE id = $1 AND client_id = $2 AND status = 'new' RETURNING *",
        request_id, client_id
    )

async def get_new_requests():
    pool = await get_pool()
    return await pool.fetch(
        "SELECT r.*, u.full_name as client_name FROM requests r "
        "LEFT JOIN users u ON r.client_id = u.id "
        "WHERE r.status = 'new' AND r.executor_id IS NULL"
    )

async def assign_executor(request_id: int, executor_telegram_id: int):
    pool = await get_pool()
    executor = await get_user_by_telegram(executor_telegram_id)
    if not executor:
        return None
    return await pool.fetchrow(
        "UPDATE requests SET executor_id = $1, status = 'in_work' WHERE id = $2 RETURNING *",
        executor['id'], request_id
    )

async def get_executor_active_requests(executor_telegram_id: int):
    """Получить активные заявки исполнителя"""
    pool = await get_pool()
    user = await get_user_by_telegram(executor_telegram_id)
    if not user:
        return []
    return await pool.fetch("""
        SELECT r.*, u.full_name as client_name
        FROM requests r
        JOIN users u ON r.client_id = u.id
        WHERE r.executor_id = $1 AND r.status IN ('in_work', 'extended')
        ORDER BY r.created_at DESC
    """, user['id'])

async def get_executor_completed_requests(executor_telegram_id: int, limit: int = 20):
    """Получить историю выполненных заявок исполнителя"""
    pool = await get_pool()
    user = await get_user_by_telegram(executor_telegram_id)
    if not user:
        return []
    return await pool.fetch("""
        SELECT r.*, u.full_name as client_name, rep.text_report, rep.created_at as completed_at
        FROM requests r
        JOIN users u ON r.client_id = u.id
        JOIN reports rep ON r.id = rep.request_id
        WHERE r.executor_id = $1 AND r.status = 'completed'
        ORDER BY rep.created_at DESC
        LIMIT $2
    """, user['id'], limit)

async def complete_request(request_id: int, executor_telegram_id: int, report_text: str):
    pool = await get_pool()
    executor = await get_user_by_telegram(executor_telegram_id)
    if not executor:
        return None
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO reports (request_id, executor_id, text_report) VALUES ($1, $2, $3)",
                request_id, executor['id'], report_text
            )
            result = await conn.fetchrow(
                "UPDATE requests SET status = 'completed' WHERE id = $1 RETURNING *",
                request_id
            )
            return result

async def create_report_with_media(request_id: int, executor_id: int, text_report: str, media_paths: list = None):
    """Создать отчет с медиафайлами"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            report = await conn.fetchrow(
                "INSERT INTO reports (request_id, executor_id, text_report) VALUES ($1, $2, $3) RETURNING *",
                request_id, executor_id, text_report
            )
            await conn.execute(
                "UPDATE requests SET status = 'completed' WHERE id = $1",
                request_id
            )
            if media_paths:
                for path in media_paths:
                    await conn.execute(
                        "INSERT INTO request_media (request_id, file_path, media_type) VALUES ($1, $2, $3)",
                        request_id, path, "report_photo"
                    )
            return report

# ========== ФУНКЦИИ ДЛЯ ПРОДЛЕНИЙ ==========

async def request_extension(request_id: int, executor_telegram_id: int, days: int):
    pool = await get_pool()
    executor = await get_user_by_telegram(executor_telegram_id)
    if not executor:
        return None
    return await pool.fetchrow(
        "INSERT INTO extensions (request_id, requested_days) VALUES ($1, $2) RETURNING *",
        request_id, days
    )

async def create_extension_request(request_id: int, executor_id: int, days: int):
    """Создать запрос на продление"""
    pool = await get_pool()
    return await pool.fetchrow(
        "INSERT INTO extensions (request_id, requested_days) VALUES ($1, $2) RETURNING *",
        request_id, days
    )

async def get_pending_extensions(client_telegram_id: int):
    """Получить ожидающие продления для клиента"""
    pool = await get_pool()
    return await pool.fetch("""
        SELECT e.*, r.description, u.full_name as executor_name
        FROM extensions e
        JOIN requests r ON e.request_id = r.id
        JOIN users u ON r.executor_id = u.id
        WHERE r.client_id = (SELECT id FROM users WHERE telegram_id = $1)
        AND e.status = 'waiting'
    """, client_telegram_id)

async def approve_extension(extension_id: int):
    """Подтвердить продление"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            ext = await conn.fetchrow(
                "UPDATE extensions SET status = 'approved' WHERE id = $1 RETURNING *",
                extension_id
            )
            if ext:
                await conn.execute(
                    "UPDATE requests SET status = 'extended' WHERE id = $1",
                    ext['request_id']
                )
            return ext

async def reject_extension(extension_id: int):
    """Отклонить продление"""
    pool = await get_pool()
    return await pool.fetchrow(
        "UPDATE extensions SET status = 'rejected' WHERE id = $1 RETURNING *",
        extension_id
    )

# ========== ФУНКЦИИ ДЛЯ АДМИНИСТРАТОРА ==========

async def get_all_requests_with_filters(status=None, client_id=None, executor_id=None):
    pool = await get_pool()
    query = """
        SELECT r.*, 
               c.full_name as client_name,
               e.full_name as executor_name
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
    if client_id:
        query += f" AND r.client_id = ${param_index}"
        params.append(client_id)
        param_index += 1
    if executor_id:
        query += f" AND r.executor_id = ${param_index}"
        params.append(executor_id)
    
    query += " ORDER BY r.created_at DESC"
    
    return await pool.fetch(query, *params)

async def admin_force_assign_executor(request_id: int, executor_telegram_id: int):
    """Принудительное назначение исполнителя (админ)"""
    pool = await get_pool()
    executor = await get_user_by_telegram(executor_telegram_id)
    if not executor or executor['role'] != 'executor':
        return None
    return await pool.fetchrow(
        "UPDATE requests SET executor_id = $1, status = 'in_work' WHERE id = $2 RETURNING *",
        executor['id'], request_id
    )

async def admin_update_status(request_id: int, new_status: str):
    """Принудительное изменение статуса (админ)"""
    pool = await get_pool()
    return await pool.fetchrow(
        "UPDATE requests SET status = $1 WHERE id = $2 RETURNING *",
        new_status, request_id
    )

async def admin_delete_request(request_id: int):
    """Удаление заявки (админ)"""
    pool = await get_pool()
    return await pool.execute("DELETE FROM requests WHERE id = $1", request_id)

async def get_request_media(request_id: int):
    """Получить все медиафайлы заявки"""
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM request_media WHERE request_id = $1 ORDER BY id",
        request_id
    )

async def delete_user(telegram_id: int):
    """Удалить пользователя из БД (выход из аккаунта)"""
    pool = await get_pool()
    return await pool.execute("DELETE FROM users WHERE telegram_id = $1", telegram_id)
# ========== ФУНКЦИИ ДЛЯ СТАТИСТИКИ ==========

async def get_system_stats():
    """Получить полную статистику системы"""
    pool = await get_pool()
    stats = {}
    
    stats['total_users'] = await pool.fetchval("SELECT COUNT(*) FROM users")
    stats['total_requests'] = await pool.fetchval("SELECT COUNT(*) FROM requests")
    stats['new_requests'] = await pool.fetchval("SELECT COUNT(*) FROM requests WHERE status = 'new'")
    stats['in_work_requests'] = await pool.fetchval("SELECT COUNT(*) FROM requests WHERE status = 'in_work'")
    stats['completed_requests'] = await pool.fetchval("SELECT COUNT(*) FROM requests WHERE status = 'completed'")
    stats['extended_requests'] = await pool.fetchval("SELECT COUNT(*) FROM requests WHERE status = 'extended'")
    stats['cancelled_requests'] = await pool.fetchval("SELECT COUNT(*) FROM requests WHERE status = 'cancelled'")
    stats['clients_count'] = await pool.fetchval("SELECT COUNT(*) FROM users WHERE role = 'client'")
    stats['executors_count'] = await pool.fetchval("SELECT COUNT(*) FROM users WHERE role = 'executor'")
    stats['admins_count'] = await pool.fetchval("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    
    stats['top_executors'] = await pool.fetch("""
        SELECT u.full_name, COUNT(r.id) as completed_count
        FROM users u
        JOIN requests r ON r.executor_id = u.id
        WHERE r.status = 'completed'
        GROUP BY u.id
        ORDER BY completed_count DESC
        LIMIT 5
    """)
    
    return stats