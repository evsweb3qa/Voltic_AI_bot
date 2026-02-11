# embedding_service.py
# Сервис для создания векторных эмбеддингов через OpenAI

import asyncio
import logging
from typing import List, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Сервис для создания эмбеддингов текста через OpenAI API"""

    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "text-embedding-ada-002"  # 1536 размерность вектора

    async def create_embedding(self, text: str) -> Optional[List[float]]:
        """
        Создаёт эмбеддинг для текста.
        Возвращает список float или None при ошибке.
        """
        try:
            # Обрезаем слишком длинный текст (лимит токенов)
            if len(text) > 8000:
                text = text[:8000]

            response = await self.client.embeddings.create(
                model=self.model,
                input=text
            )
            return response.data[0].embedding

        except Exception as e:
            logger.error(f"Ошибка создания эмбеддинга: {e}")
            # Возвращаем None вместо нулевого вектора чтобы обработать ошибку
            return None

    async def create_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Создаёт эмбеддинги для пакета текстов.
        Возвращает список эмбеддингов (или None для неудачных).
        """
        try:
            # Обрезаем слишком длинные тексты
            processed_texts = [t[:8000] if len(t) > 8000 else t for t in texts]

            response = await self.client.embeddings.create(
                model=self.model,
                input=processed_texts
            )
            return [data.embedding for data in response.data]

        except Exception as e:
            logger.error(f"Ошибка пакетного создания эмбеддингов: {e}")
            # Возвращаем список None для каждого текста
            return [None] * len(texts)


# Глобальный экземпляр
embedding_service: Optional[EmbeddingService] = None
