# rag_database.py
# Модуль для работы с векторной базой данных RAG

import asyncpg
import logging
from typing import Optional, List, Dict, Any
import json

logger = logging.getLogger(__name__)

# Глобальный пул соединений для RAG
_rag_pool: Optional[asyncpg.Pool] = None

class RAGDatabase:
    """Класс для работы с RAG базой данных"""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Подключается к базе данных"""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=10
        )
        await self._create_tables()
        logger.info("✅ RAGDatabase connected")

    async def _create_tables(self):
        """Создаёт таблицы для RAG"""
        async with self.pool.acquire() as conn:
            # Расширение pgvector
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            # Таблица документов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id SERIAL PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    file_hash VARCHAR(64) UNIQUE NOT NULL,
                    uploaded_by BIGINT NOT NULL,
                    total_chunks INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица чанков с векторами
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER REFERENCES rag_documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector(1536),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица статистики
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_usage_stats (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    query TEXT,
                    chunks_used INTEGER DEFAULT 0,
                    response_time_ms INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            logger.info("✅ RAG tables initialized")

    async def add_document(self, filename: str, file_hash: str, user_id: int) -> int:
        """Добавляет документ в базу, возвращает ID"""
        async with self.pool.acquire() as conn:
            doc_id = await conn.fetchval("""
                INSERT INTO rag_documents (filename, file_hash, uploaded_by)
                VALUES ($1, $2, $3)
                RETURNING id
            """, filename, file_hash, user_id)
            return doc_id

    async def add_chunk(self, document_id: int, chunk_index: int,
                        content: str, embedding: List[float],
                        metadata: Dict[str, Any] = None):
        """Добавляет чанк с эмбеддингом в базу"""
        async with self.pool.acquire() as conn:
            # Преобразуем список в строку для pgvector
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            metadata_json = json.dumps(metadata or {})

            await conn.execute("""
                INSERT INTO rag_chunks (document_id, chunk_index, content, embedding, metadata)
                VALUES ($1, $2, $3, $4::vector, $5::jsonb)
            """, document_id, chunk_index, content, embedding_str, metadata_json)

    async def search_chunks(self, query_embedding: List[float], limit: int = 5) -> List[Dict]:
        """
        Ищет похожие чанки по эмбеддингу.
        Возвращает список чанков с оценкой схожести.
        """
        async with self.pool.acquire() as conn:
            # Преобразуем эмбеддинг в строку для pgvector
            embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

            # Поиск по косинусному сходству (1 - distance = similarity)
            rows = await conn.fetch("""
                SELECT 
                    c.id,
                    c.content,
                    c.metadata,
                    d.filename,
                    1 - (c.embedding <=> $1::vector) as similarity
                FROM rag_chunks c
                JOIN rag_documents d ON c.document_id = d.id
                ORDER BY c.embedding <=> $1::vector
                LIMIT $2
            """, embedding_str, limit)

            results = []
            for row in rows:
                results.append({
                    'id': row['id'],
                    'content': row['content'],
                    'metadata': json.loads(row['metadata']) if row['metadata'] else {},
                    'filename': row['filename'],
                    'similarity': float(row['similarity'])
                })

            return results

    async def log_usage(self, user_id: int, query: str,
                        chunks_used: int, response_time_ms: int):
        """Логирует использование RAG системы"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO rag_usage_stats (user_id, query, chunks_used, response_time_ms)
                VALUES ($1, $2, $3, $4)
            """, user_id, query, chunks_used, response_time_ms)

    async def get_document_stats(self) -> Dict[str, Any]:
        """Возвращает статистику документов"""
        async with self.pool.acquire() as conn:
            docs_count = await conn.fetchval("SELECT COUNT(*) FROM rag_documents")
            chunks_count = await conn.fetchval("SELECT COUNT(*) FROM rag_chunks")

            return {
                'documents_count': docs_count or 0,
                'chunks_count': chunks_count or 0
            }

    async def get_all_documents(self) -> List[Dict]:
        """Возвращает список всех документов"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, filename, total_chunks, uploaded_by, created_at
                FROM rag_documents
                ORDER BY created_at DESC
            """)
            return [dict(row) for row in rows]

    async def delete_document(self, doc_id: int) -> bool:
        """Удаляет документ и все его чанки"""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM rag_documents WHERE id = $1",
                doc_id
            )
            return "DELETE 1" in result


# Глобальный экземпляр
rag_db: Optional[RAGDatabase] = None