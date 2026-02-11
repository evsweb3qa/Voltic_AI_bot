# ai_service.py
import os
import asyncio
from typing import List, Dict, Optional
from openai import AsyncOpenAI
import logging
from config import settings
#from groq import AsyncGroq

logger = logging.getLogger(__name__)

class OpenAIAssistant:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")

        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        #self.client = AsyncGroq(api_key=settings.OPENAI_API_KEY)

        self.model = settings.AI_MODEL
        self.max_tokens = settings.AI_MAX_TOKENS
        self.temperature = settings.AI_TEMPERATURE
        self.system_prompt = self._load_system_prompt()
        self.system_prompt_rag = self._load_system_prompt_rag()
        logger.info(f"AI Assistant initialized with model: {self.model}")

# 1 ============== Загрузка промпта из файла docs/bot_instructions.txt ==============

    def _load_system_prompt(self) -> str:
        """Загружаем системный промпт из файла"""
        try:
            prompt_path = "docs/bot_instructions_non_RAG.txt"
            if os.path.exists(prompt_path):
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                logger.error(f"Ошибка чтения файла docs/bot_instructions.txt : {e}")
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")

    def _load_system_prompt_rag(self) -> str:
        """Загружаем системный промпт для раг использования"""
        try:
            prompt_path = "docs/bot_instructions_for_rag.txt"
            if os.path.exists(prompt_path):
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                logger.error(f"Ошибка чтения файла docs/bot_instructions_for_rag.txt : {e}")
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")

# 3================= Запрос и ответ от ИИ  ===============================

    async def get_response(
            self,
            user_message: str,
            user_id: int,
            history: Optional[List[Dict]] = None,
            timeout: int = 15,
            RAG: bool = False
    ) -> str:
        """Получить ответ от OpenAI"""

        # Формируем сообщения
        if RAG:
            messages = [
                {"role": "system", "content": self.system_prompt_rag}
            ]
        else:
            messages = [
                {"role": "system", "content": self.system_prompt}
            ]

        # Добавляем историю диалога (если есть)
        if history:
            # Ограничиваем историю (последние 3 пары вопрос-ответ)
            max_history = 3
            if len(history) > max_history * 2:
                history = history[-max_history * 2:]
            messages.extend(history)

        # Добавляем текущий вопрос
        messages.append({"role": "user", "content": user_message})
        logger.info(f'{messages}')
        try:
            # Делаем запрос к OpenAI с таймаутом
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                ),
                timeout=timeout
            )

            ai_response = response.choices[0].message.content.strip()

            # Очищаем ответ от лишних форматирований
            ai_response = ai_response.replace("```", "").strip()

            # Логируем успешный запрос
            logger.info(f"AI response generated for user {user_id}, tokens: {response.usage.total_tokens}")

            return ai_response

        except asyncio.TimeoutError:
            logger.warning(f"OpenAI timeout for user {user_id}")
            return "⏳ Sorry, the response is taking longer than expected. Please try again later or use the menu buttons."

        except Exception as e:
            logger.error(f"OpenAI error for user {user_id}: {str(e)}")
            return "The AI assistant is currently unavailable. Please use the menu buttons or try again later."


# Создаем глобальный экземпляр для использования во всем боте
ai_assistant = OpenAIAssistant()