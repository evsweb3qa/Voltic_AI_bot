# rag_engine.py
# Основной движок RAG системы

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Глобальный экземпляр движка
rag_engine: Optional['RAGEngine'] = None


class RAGEngine:
    """Основной движок RAG для обработки запросов с использованием базы знаний"""

    def __init__(self, db, embedding_service, openai_assistant):
        self.db = db  # RAGDatabase
        self.embedding_service = embedding_service  # EmbeddingService
        self.openai_assistant = openai_assistant  # OpenAIAssistant
        self.similarity_threshold = 0.7 # Порог схожести для фильтрации

# ========================== Обработка запроса через RAG ==============================

    async def process_query(self, query: str, user_id: int, history: Optional[List[Dict]] = None) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает запрос пользователя через RAG.
        1. Создаёт эмбеддинг запроса
        2. Ищет похожие чанки в базе
        3. Формирует контекст и отправляет в ИИ
        """
        start_time = datetime.now()

        try:
            # 1. Создаём эмбеддинг запроса
            query_embedding = await self.embedding_service.create_embedding(query)

            # Если эмбеддинг не создался - используем обычный ИИ
            if query_embedding is None:
                logger.warning("Не удалось создать эмбеддинг запроса")
                return

            # 2. Ищем релевантные чанки в базе
            chunks = await self.db.search_chunks(query_embedding, limit=4)

            # 3. Фильтруем по порогу схожести
            relevant_chunks = [
                chunk for chunk in chunks
                if chunk['similarity'] >= self.similarity_threshold
            ]

            # 4. Если нет релевантных чанков - используем обычный ИИ
            if not relevant_chunks:
                logger.info("Нет релевантных чанков, используем обычный ИИ")
                return None

            # 5. Формируем контекст из найденных чанков
            context = self._build_context(relevant_chunks)

            # 6. Формируем промпт с контекстом
            prompt = self._build_prompt(query, context)

            # 7. Отправляем в OpenAI
            response = await self.openai_assistant.get_response(
                user_message=prompt,
                user_id=user_id,
                history=history,
                RAG=True
            )

            # 8. Очищаем ответ от технических меток
            clean_response = self._clean_response(response)

            response_time = int((datetime.now() - start_time).total_seconds() * 1000)

            # 9. Логируем использование RAG
            await self.db.log_usage(
                user_id=user_id,
                query=query,
                chunks_used=len(relevant_chunks),
                response_time_ms=response_time
            )

            return {
                'success': True,
                'response': clean_response,
                'rag_used': True,
                'chunks_used': len(relevant_chunks),
                'response_time_ms': response_time,
                'chunks': relevant_chunks
            }

        except Exception as e:
            logger.error(f"Ошибка обработки RAG запроса: {e}")
            return None

# ========================== Формирует контекст из найденных чанков ==============================

    def _build_context(self, chunks: List[Dict]) -> str:
        """Формирует контекст из найденных чанков"""
        context_parts = []
        for i, chunk in enumerate(chunks):
            content = chunk['content']
            # Обрезаем слишком длинные чанки
            if len(content) > 500:
                content = content[:500] + "..."

            source = chunk.get('filename', f'Документ {i + 1}')
            similarity = chunk.get('similarity', 0)

            context_parts.append(
                f"[Источник: {source}, релевантность: {similarity:.2f}]:\n{content}"
            )

        return "\n\n".join(context_parts)

# ========================== Строит промпт с контекстом из базы знаний ==============================

    def _build_prompt(self, query: str, context: str) -> str:
        """Строит промпт с контекстом из базы знаний"""
        return f"""Use this information from the knowledge base to answer the question:

INFORMATION FROM THE KNOWLEDGE BASE:
{context}

USER QUESTION:
{query}
"""

# ========================== Очищает ответ от технических меток ==============================

    def _clean_response(self, response: str) -> str:
        """Очищает ответ от технических меток"""
        response = response.replace("[Источник:", "").replace("релевантность:", "")
        return response.strip()

# ========================== Получает статистику RAG системы ==============================

    async def get_stats(self) -> Dict[str, Any]:
        """Получает статистику RAG системы"""
        try:
            db_stats = await self.db.get_document_stats()

            async with self.db.pool.acquire() as conn:
                # Запросы за сегодня
                today_usage = await conn.fetchval("""
                    SELECT COUNT(*) FROM rag_usage_stats 
                    WHERE DATE(created_at) = CURRENT_DATE
                """)

                # Всего запросов
                total_usage = await conn.fetchval("""
                    SELECT COUNT(*) FROM rag_usage_stats
                """)

            return {
                **db_stats,
                'queries_today': today_usage or 0,
                'total_queries': total_usage or 0,
                'status': 'active'
            }

        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {'error': str(e)}


# ========================== Инициализирует глобальный экземпляр RAG движка ==============================

async def init_rag_engine(db, embedding_service, openai_assistant):
    """Инициализирует глобальный экземпляр RAG движка"""
    global rag_engine
    rag_engine = RAGEngine(db, embedding_service, openai_assistant)
    logger.info("✅ RAG Engine инициализирован")
    return rag_engine


def get_rag_engine() -> Optional[RAGEngine]:
    """Возвращает глобальный экземпляр RAG движка"""
    return rag_engine