# rag_system.py
# Модуль инициализации и управления RAG системой

import logging
import asyncio
logger = logging.getLogger(__name__)

# Глобальные переменные для компонентов RAG
rag_db = None  # База данных RAG
embedding_service = None  # Сервис эмбеддингов
document_uploader = None  # Загрузчик документов
rag_engine = None  # Движок RAG


async def init_rag_system(settings, ai_assistant):
    """
    Инициализирует всю RAG систему.
    Вызывается из main.py при запуске бота.

    Параметры:
        settings: объект настроек из config.py
        ai_assistant: инициализированный OpenAI ассистент
    """
    global rag_db, embedding_service, document_uploader, rag_engine

    try:
        # Проверяем настройки
        if not settings.RAG_ENABLED:
            logger.info("RAG отключён в настройках")
            return False

        if not settings.POSTGRES_PORT_RAG:
            logger.error("DATABASE_URL не задан для RAG")
            return False

        # 1. Инициализируем БД для RAG
        from rag_system.rag_database import RAGDatabase
        rag_db = RAGDatabase(settings.POSTGRES_PORT_RAG)
        # Добавляем повторные попытки с экспоненциальной задержкой
        max_retries = 5
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                await rag_db.connect()
                break  # Успешно подключились
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # Экспоненциальная задержка
                    logger.warning(f"⏳ Попытка {attempt + 1}/{max_retries} подключения к RAG БД не удалась. "
                                   f"Ожидание {wait_time}с... Ошибка: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Не удалось подключиться к RAG БД после {max_retries} попыток")
                    raise

        logger.info("✅ RAG база данных подключена")
        # await rag_db.connect()
        # logger.info("✅ RAG база данных подключена")

        # 2. Инициализируем сервис эмбеддингов
        from rag_system.embedding_service import EmbeddingService
        embedding_service = EmbeddingService(settings.OPENAI_API_KEY)
        logger.info("✅ Сервис эмбеддингов инициализирован")

        # 3. Инициализируем загрузчик документов
        from rag_system.document_uploader import DocumentUploader
        document_uploader = DocumentUploader(rag_db, embedding_service)
        logger.info("✅ Загрузчик документов инициализирован")

        # 4. Инициализируем RAG движок
        from rag_system.rag_engine import init_rag_engine
        rag_engine = await init_rag_engine(rag_db, embedding_service, ai_assistant)
        logger.info("✅ RAG движок инициализирован")

        # 5. Логируем статистику
        stats = await rag_engine.get_stats()
        logger.info(f"📊 RAG статистика: документов={stats.get('documents_count', 0)}, "
                    f"чанков={stats.get('chunks_count', 0)}")

        return True

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации RAG системы: {e}")
        return False


async def close_rag_system():
    """Закрывает соединения RAG системы"""
    global rag_db
    if rag_db and rag_db.pool:
        await rag_db.pool.close()
        logger.info("✅ RAG соединения закрыты")


def get_rag_components():
    """Возвращает все компоненты RAG системы"""
    return {
        'db': rag_db,
        'embedding_service': embedding_service,
        'document_uploader': document_uploader,
        'rag_engine': rag_engine
    }