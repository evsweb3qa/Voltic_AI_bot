# test_connection.py
import asyncio
import asyncpg


async def test():
    try:
        conn = await asyncpg.connect(
            host='46.101.166.112',
            port=5432,
            user='postgres',
            password='pass34460702120',
            database='voltic_rag'
        )
        version = await conn.fetchval('SELECT version()')
        print(f"✅ Подключение успешно!")
        print(f"PostgreSQL: {version[:100]}...")

        # Проверяем расширение vector
        has_vector = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
        print(f"✅ pgvector: {'установлен' if has_vector else 'не установлен'}")

        await conn.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")


asyncio.run(test())