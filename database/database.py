#database
import asyncpg
import logging
import os
import asyncio
from typing import Optional, List, Tuple, Dict, Any
from dotenv import load_dotenv
from config import settings
from database.schemas import TableName, TABLE_SCHEMAS, INDEXES

logger = logging.getLogger(__name__)

# --- Загрузка конфигурации ---
load_dotenv()

# --- Глобальный пул соединений ---
_pool: Optional[asyncpg.Pool] = None


async def init_db():
    """Инициализирует пул соединений с PostgreSQL"""
    global _pool
    try:
        if _pool is None:
            _pool = await asyncpg.create_pool(settings.DATA_BASE_URL, min_size=2, max_size=20)
            logger.info("✅ PostgreSQL connection pool initialized")

            # Проверяем подключение
            async with _pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

            # Создаем все таблицы
            await create_tables()

            logger.info("✅ Database initialization completed successfully")

    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise

# =====================================================================================

async def create_tables():
    """Создает все таблицы из схемы"""
    async with _pool.acquire() as conn:
        for table_name, schema in TABLE_SCHEMAS.items():
            await conn.execute(schema)
            logger.info(f"✅ Table '{table_name.value}' created/verified")

            # Создаем индексы для таблицы
            for index_sql in INDEXES.get(table_name, []):
                await conn.execute(index_sql)

        logger.info("✅ All database tables and indexes created/verified")

# =====================================================================================
async def get_pool() -> asyncpg.Pool:
    """Возвращает пул соединений, инициализирует если нужно"""
    global _pool
    if _pool is None:
        await init_db()
    return _pool


async def close_db():
    """Закрывает пул соединений"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("✅ PostgreSQL connection pool closed")

# --- ДЕКОРАТОР ДЛЯ АВТОМАТИЧЕСКОГО УПРАВЛЕНИЯ СОЕДИНЕНИЯМИ ---
def with_connection(func):
    async def wrapper(*args, **kwargs):
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await func(conn, *args, **kwargs)

    return wrapper


def normalize_username(username: Optional[str]) -> str:
    """
    Нормализует username:
    - Убирает @ в начале
    - Приводит к нижнему регистру
    """
    if not username:
        return ""

    if username.startswith('@'):
        username = username[1:]

    return username.lower().strip()

# ============================== USER_REGISTRATION ==================================

@with_connection
async def get_user_by_telegram_id(conn: asyncpg.Connection, telegram_id: int):
    """Проверяет, есть ли пользователь в user_registration"""
    return await conn.fetchrow("SELECT * FROM user_registration WHERE telegram_id = $1", telegram_id)

@with_connection
async def register_user(conn, user_id: int, username: str) -> Tuple[bool, str]:
    """
    Регистрации с транзакцией
    """
    normalized_username = normalize_username(username)

    if not normalized_username:
        return False, "❌ Установите username в Telegram"

    async with conn.transaction():
        try:
            # 1. Проверка white list в транзакции
            in_white_list = await conn.fetchval(
                "SELECT COUNT(*) > 0 FROM user_white_list WHERE user_name = $1",
                normalized_username
            )

            if not in_white_list:
                return False, "❌ У вас нет доступа к боту.\nОбратитесь к администратору для добавления в white list."

            # 2. Попытка регистрации с обработкой конфликта
            try:
                await conn.execute(
                    "INSERT INTO user_registration (telegram_id, user_name) VALUES ($1, $2)",
                    user_id, normalized_username
                )
                return True, "✅ Вы успешно зарегистрированы! Теперь давай начнем работу! Задавай мне вопросы и я обязательно отвечу на них!"

            except asyncpg.UniqueViolationError:
                # telegram_id уже существует
                return False, "Вы уже зарегистрированы!"

        except Exception as e:
            logger.error(f"Ошибка регистрации для пользователя {user_id}: {e}")
            return False, "❌ Произошла внутренняя ошибка."

# ========================== WHITE LIST =========================================

@with_connection
async def check_white_list(conn: asyncpg.Connection, username: str) -> bool:
    """Проверяет, есть ли пользователь в white list"""
    return await conn.fetchrow("SELECT COUNT(*) FROM user_white_list WHERE user_name = $1",  username)

@with_connection
async def get_white_list_users(conn) -> List[str]:
    """Получить список всех username в white list"""
    rows = await conn.fetch("""
        SELECT user_name FROM user_white_list ORDER BY added_at DESC
    """)

    return [f"@{row['user_name']}" for row in rows]

@with_connection
async def add_to_white_list(conn, username: str) -> Tuple[bool, str]:
    """Добавить username в white list"""
    normalized_username = normalize_username(username)

    if not normalized_username:
        return False, "❌ Неверный username"

    try:
        await conn.execute("""
            INSERT INTO user_white_list (user_name)
            VALUES ($1)
            ON CONFLICT (user_name) DO NOTHING
        """, normalized_username)

        return True, f"✅ @{normalized_username} добавлен в white list"

    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении в white list: {e}")
        return False, f"❌ Ошибка: {e}"

@with_connection
async def remove_from_white_list(conn, username: str) -> Tuple[bool, str]:
    """Удалить username из white list"""
    normalized_username = normalize_username(username)

    try:
        result = await conn.execute("""
            DELETE FROM user_white_list WHERE user_name = $1
        """, normalized_username)

        if result == "DELETE 1":
            logger.info(f"✅ @{normalized_username} удален из white list")
            return True, f"✅ @{normalized_username} удален из white list"
        else:
            return False, "❌ Username не найден в white list"

    except Exception as e:
        logger.error(f"❌ Ошибка при удалении из white list: {e}")
        return False, f"❌ Ошибка: {e}"

# ================================================================================

@with_connection
async def delete_user(
        conn: asyncpg.Connection,
        telegram_id: int
) -> Dict[str, Any]:
    """
    Удаляет пользователя из базы данных

    Args:
        telegram_id: ID пользователя в Telegram
    Returns:
        Словарь с результатом операции
    """
    try:
        # Сначала проверяем, существует ли пользователь
        user_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM user_registration WHERE telegram_id = $1)",
            telegram_id
        )

        if not user_exists:
            logger.warning(f"⚠️ User {telegram_id} not found for deletion")
            return {
                "success": False,
                "message": "User not found",
                "deleted": False,
                "telegram_id": telegram_id
            }

        # Удаляем пользователя
        result = await conn.execute(
            "DELETE FROM user_registration WHERE telegram_id = $1",
            telegram_id
        )

        # Проверяем, была ли удалена хотя бы одна строка
        deleted_count = int(result.split()[1])  # Пример: "DELETE 1"

        if deleted_count > 0:
            logger.info(f"🗑️ User {telegram_id} successfully deleted")
            return {
                "success": True,
                "message": "User deleted successfully",
                "deleted": True,
                "telegram_id": telegram_id,
                "deleted_count": deleted_count
            }
        else:
            logger.warning(f"⚠️ No user deleted for telegram_id {telegram_id}")
            return {
                "success": False,
                "message": "No user was deleted",
                "deleted": False,
                "telegram_id": telegram_id
            }

    except asyncpg.ForeignKeyViolationError as e:
        logger.error(f"❌ Cannot delete user {telegram_id}: foreign key constraint violation")
        return {
            "success": False,
            "message": "Cannot delete user: user has related data. Use cascade=True or delete related data first.",
            "deleted": False,
            "telegram_id": telegram_id,
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"❌ Error deleting user {telegram_id}: {e}")
        return {
            "success": False,
            "message": f"Database error: {str(e)}",
            "deleted": False,
            "telegram_id": telegram_id,
            "error": str(e)
        }