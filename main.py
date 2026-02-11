import os
import json
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)

from button_handlers import inlinehandler
from database.database import (
    init_db, close_db, get_user_by_telegram_id, add_to_white_list, delete_user, get_white_list_users,
    remove_from_white_list
)
from config import settings
from telegram.constants import ParseMode
from ai_service import ai_assistant
from datetime import datetime
from keyboard.keyboard import inlinekeyboard
# Импортируем RAG компоненты
from rag_system.rag_system import init_rag_system, get_rag_components, close_rag_system


# --- Настройка логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    force=True
)
logger = logging.getLogger(__name__)

# ================================================================

BOT_TOKEN = settings.BOT_TN
if not BOT_TOKEN:
    raise ValueError("❌ Переменная BOT_TOKEN не найдена в .env")

# ================================================================

ADMIN_IDS = settings.ADMIN_IDS

# ================================================================

# ID картинки приветствия
WELCOME_PHOTO_ID = settings.WELCOME_PHOTO_ID

# ==================== Обработчики команд и кнопок ===============================
# ==================== Команда /start ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} запустил /start")
    registration_check = await get_user_by_telegram_id(user_id)
    if not registration_check:
        logger.info(f"Пользователь {user_id} не зарегистрирован")
        # Очищаем состояние
        context.user_data.clear()
        await update.message.reply_photo(
            photo=WELCOME_PHOTO_ID,
            caption="👋 Добро пожаловать, я твой помощник в мире энергетики, задавай мне вопросы и я обязательно помогу тебе!",
            reply_markup = inlinekeyboard.get_auth_keyboard()
        )
    else:
        await update.message.reply_text(
            "С возвращением!")

# ============================= Команда /exit ===================================

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /exit"""
    user_id = update.effective_user.id
    registration_check = await get_user_by_telegram_id(user_id)
    if not registration_check:
        await update.message.reply_text(
            "❌ You are not logged in.",
            reply_markup=inlinekeyboard.get_auth_keyboard()
        )
        return

    try:
        success = await delete_user(user_id)
        if success:
            # ОЧИЩАЕМ AI-ИСТОРИЮ ПРИ ВЫХОДЕ
            if 'ai_history' in context.user_data:
                del context.user_data['ai_history']

            await update.message.reply_text(
                "✅ Ваши данные успешно удалены из системы.\n\n"
                "🔁 Для повторной регистрации, обратитесь к администратору.\n\n",
                reply_markup=inlinekeyboard.get_auth_keyboard()
            )
        else:
            await update.message.reply_text("❌ Error during logout. Please try again later.")
    except Exception as e:
        logger.error(f"Error in handle_logout_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


# 6 ================= Обработчик текстовых сообщений ===============================

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    registration_check = await get_user_by_telegram_id(user_id)

    if not registration_check:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы в системе",
            reply_markup=inlinekeyboard.get_auth_keyboard()
        )
        return

    # 2. Проверяем состояние ожидания RAG документа
    if context.user_data.get('awaiting_rag_document'):
        await handle_document_upload(update, context)
        return

    # Проверяем, что будет обрабатывать сообщение
    # Если пользователь авторизован в боте и AI включено в .env: используем AI
    if settings.AI_ENABLED:
        logger.info(f"Ответ от AI")
        await handle_ai_message(update, context, text)
        return
    # Иначе используем обработчик неизвестных команд:
    else:
        await handle_unknown_command(update, context)
        return

# ======================= Обработчик AI-сообщений ==================================

async def handle_ai_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Обработчик AI-сообщений"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} asked AI: {text[:50]}...")

    # Получаем историю диалога из context.user_data
    if 'ai_history' not in context.user_data:
        context.user_data['ai_history'] = []

    history = context.user_data['ai_history']


    try:
        await update.message.chat.send_action(action="typing")

        # Проверяем RAG перед обычным AI
        ai_response = None

        # Если RAG включен и пользователь админ или обычный пользователь (в зависимости от настроек)
        if settings.RAG_ENABLED:
            try:
                from rag_system import rag_engine
                if rag_engine:
                    # Пробуем использовать RAG
                    rag_result = await rag_engine.process_query(text, user_id, history)

                    if rag_result['success'] and rag_result['rag_used']:
                        ai_response = rag_result['response']
                        logger.info(f"RAG used for user {user_id}, chunks: {rag_result['chunks_used']}")
                    else:
                        # RAG не сработал или не нашел релевантной информации
                        logger.info(f"RAG fallback for user {user_id}, using regular AI")
            except Exception as rag_error:
                logger.error(f"RAG processing error: {rag_error}")

        # Если RAG не дал ответа или отключен, используем обычный AI
        if not ai_response:
            logger.info(f"RAG пропущен")
            ai_response = await ai_assistant.get_response(
                user_message=text,
                user_id=user_id,
                history=history,
                RAG=False
            )

        # Сохраняем в историю (для контекста в будущем)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": ai_response})

        # Ограничиваем длину истории (последние 3 пары вопрос-ответ)
        max_history_pairs = 3
        if len(history) > max_history_pairs * 2:
            context.user_data['ai_history'] = history[-max_history_pairs * 2:]
        else:
            context.user_data['ai_history'] = history

        # Отправляем ответ пользователю
        await update.message.reply_text(ai_response)

    except Exception as e:
        logger.error(f"AI processing error for user {user_id}: {e}")
        await update.message.reply_text(
            "🤖 Sorry, there was a technical error. "
            "Please use the menu buttons or try again later."
        )

# ========================= Обработчик неизвестных команд ======================

async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик неизвестных команд"""
    user_id = update.effective_user.id

    await update.message.reply_text(
        "🤔 Use the buttons below to interact with the bot."
    )


# --- Команды от администратора ---
# ============================ Команда: /add_wl @username ==================================

async def add_to_wl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда: /add_wl @username
    Добавляет пользователя в white list
    """
    user_id = update.effective_user.id

    # Проверка прав администратора
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return

    # Проверка аргументов
    if not context.args:
        await update.message.reply_text(
            "❌ Использование: `/add_wl @username`\n\n"
            "Примеры:\n"
            "• `/add_wl @ivanov`\n"
            "• `/add_wl @petrov @sidorov` - несколько пользователей",
            parse_mode="Markdown"
        )
        return

    # Обработка каждого username
    added_users = []
    failed_users = []

    for username_arg in context.args:
        # Очищаем username от возможных символов
        username = username_arg.strip()

        # Проверяем формат username
        if not username.startswith('@'):
            await update.message.reply_text(
                f"❌ Неверный формат: `{username}`\n"
                "Username должен начинаться с @ (например: @username)",
                parse_mode="Markdown"
            )
            continue

        # Добавляем в white list
        success, message = await add_to_white_list(username)

        if success:
            added_users.append(username)
            logger.info(f"✅ {username} добавлен в white list")
        else:
            failed_users.append(f"{username}: {message}")
            logger.warning(f"❌ Ошибка добавления {username}: {message}")

    # Формируем ответ
    response_parts = []

    if added_users:
        response_parts.append(f"✅ **Добавлен в white list:**\n" + "\n".join(added_users))

    if failed_users:
        response_parts.append(f"❌ **Не удалось добавить:**\n" + "\n".join(failed_users))

    if not added_users and not failed_users:
        response_parts.append("❌ Не указаны username для добавления.")

    await update.message.reply_text(
        "\n\n".join(response_parts),
        parse_mode="Markdown"
    )

# ============================ Команда: /remove_wl @username ==================================

async def remove_from_wl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда: /remove_wl @username
    Удаляет пользователя из white list
    """
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Использование: `/remove_wl @username`\n\n"
            "Примеры:\n"
            "• `/remove_wl @ivanov`\n"
            "• `/remove_wl @petrov @sidorov` - несколько пользователей",
            parse_mode="Markdown"
        )
        return

    removed_users = []
    failed_users = []

    for username_arg in context.args:
        username = username_arg.strip()

        if not username.startswith('@'):
            await update.message.reply_text(
                f"❌ Неверный формат: `{username}`",
                parse_mode="Markdown"
            )
            continue

        success, message = await remove_from_white_list(username)

        if success:
            removed_users.append(username)
            logger.info(f"✅ Админ {user_id} удалил из white list: {username}")
        else:
            failed_users.append(f"{username}: {message}")
            logger.warning(f"❌ Админ {user_id} не смог удалить {username}: {message}")

    response_parts = []

    if removed_users:
        response_parts.append(f"✅ **Удалены из white list:**\n" + "\n".join(removed_users))

    if failed_users:
        response_parts.append(f"❌ **Не удалось удалить:**\n" + "\n".join(failed_users))

    if not removed_users and not failed_users:
        response_parts.append("❌ Не указаны username для удаления.")

    await update.message.reply_text(
        "\n\n".join(response_parts),
        parse_mode="Markdown"
    )

# ============================ Команда: /show_wl  ==================================

async def show_wl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда: /show_wl
    Показывает всех пользователей в white list
    """
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return

    try:
        # Получаем список пользователей
        users = await get_white_list_users()

        if not users:
            await update.message.reply_text("📭 White list пуст.")
            return

        # Форматируем вывод
        user_list = []
        for i, username in enumerate(users, 1):
            user_list.append(f"{i}. {username}")

        response = (
                f"📋 **White list пользователей** ({len(users)}):\n\n" +
                "\n".join(user_list)
        )

        # Если список слишком длинный, разбиваем на части
        if len(response) > 4000:
            for i in range(0, len(user_list), 50):
                chunk = user_list[i:i + 50]
                chunk_response = (
                        f"📋 **White list (часть {i // 50 + 1})**\n\n" +
                        "\n".join(chunk)
                )
                await update.message.reply_text(chunk_response, parse_mode="Markdown")
                await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(response, parse_mode="Markdown")

        logger.info(f"✅ Админ {user_id} просмотрел white list ({len(users)} пользователей)")

    except Exception as e:
        logger.error(f"❌ Ошибка при показе white list: {e}")
        await update.message.reply_text("❌ Произошла ошибка при получении списка.")

# ============================ Команда: /wl_help  ==================================

async def wl_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда: /wl_help
    Справка по командам white list
    """
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return

    help_text = """
📋 **Команды управления White List**

`/add_wl @username` - добавить пользователя в white list
`/remove_wl @username` - удалить пользователя из white list  
`/show_wl` - показать всех пользователей в white list
`/check_wl @username` - проверить наличие пользователя
`/wl_help` - эта справка

**Примеры:**
• `/add_wl @ivanov` - добавить одного пользователя
• `/add_wl @petrov @sidorov` - добавить нескольких
• `/remove_wl @ivanov` - удалить пользователя
    """

    await update.message.reply_text(help_text, parse_mode="Markdown")


# ======================= RAG обработчики (только для админов) ====================================

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик загрузки документов для пополнения базы знаний RAG.
    Доступен только админам (ADMIN_IDS из .env).
    Поддерживаемые форматы: PDF, TXT, MD, DOCX
    """
    user_id = update.effective_user.id

    # Проверяем права админа
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Загрузка документов доступна только администраторам.")
        return

    # Получаем компоненты RAG
    rag_components = get_rag_components()
    uploader = rag_components.get('document_uploader')

    if not uploader:
        await update.message.reply_text("❌ RAG система не инициализирована.")
        return

    document = update.message.document
    filename = document.file_name or "unknown"

    # Проверяем формат файла
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    if ext not in ['pdf', 'txt', 'md', 'text', 'docx']:
        await update.message.reply_text(
            f"⚠️ Неподдерживаемый формат: .{ext}\n"
            "Поддерживаются: PDF, TXT, MD"
        )
        return

    # Отправляем сообщение о начале обработки
    status_msg = await update.message.reply_text(f"⏳ Обрабатываю файл: {filename}...")

    try:
        # Скачиваем файл
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()

        # Обрабатываем файл через загрузчик
        result = await uploader.process_file(bytes(file_bytes), filename, user_id)

        if result['success']:
            await status_msg.edit_text(
                f"✅ Документ загружен!\n\n"
                f"📄 Файл: {filename}\n"
                f"📊 Создано чанков: {result['chunks_created']}\n"
                f"📝 Длина текста: {result['total_text_length']} символов"
            )
            logger.info(f"Админ {user_id} загрузил документ: {filename}")
        else:
            await status_msg.edit_text(f"❌ Ошибка: {result['error']}")

    except Exception as e:
        logger.error(f"Ошибка загрузки документа: {e}")
        await status_msg.edit_text(f"❌ Ошибка обработки: {str(e)}")


async def handle_rag_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показывает статистику RAG системы.
    Команда: /rag_stats
    """
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Команда доступна только администраторам.")
        return

    rag_components = get_rag_components()
    engine = rag_components.get('rag_engine')

    if not engine:
        await update.message.reply_text("❌ RAG система не инициализирована.")
        return

    try:
        stats = await engine.get_stats()

        text = (
            "📊 **Статистика RAG системы**\n\n"
            f"📄 Документов: {stats.get('documents_count', 0)}\n"
            f"📦 Чанков: {stats.get('chunks_count', 0)}\n"
            f"🔍 Запросов сегодня: {stats.get('queries_today', 0)}\n"
            f"📈 Всего запросов: {stats.get('total_queries', 0)}\n"
            f"✅ Статус: {stats.get('status', 'неизвестен')}"
        )

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Ошибка получения статистики RAG: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def handle_rag_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показывает список загруженных документов.
    Команда: /rag_docs
    """
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Команда доступна только администраторам.")
        return

    rag_components = get_rag_components()
    uploader = rag_components.get('document_uploader')

    if not uploader:
        await update.message.reply_text("❌ RAG система не инициализирована.")
        return

    try:
        docs = await uploader.get_documents_list()

        if not docs:
            await update.message.reply_text("📂 База знаний пуста. Загрузите документы.")
            return

        text = "📚 Загруженные документы:\n\n"
        for doc in docs:
            filename = doc['filename'].replace('<', '').replace('>', '')
            text += (
                f"📄 ID: {doc['id']} | {filename}\n"
                f"   Чанков: {doc['total_chunks']} | "
                f"Дата: {doc['created_at'].strftime('%d.%m.%Y')}\n\n"
            )

        text += "💡 Для удаления: /rag_delete ID"

        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Ошибка получения списка документов: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def handle_rag_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Удаляет документ из базы знаний.
    Команда: /rag_delete <ID документа>
    """
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Команда доступна только администраторам.")
        return

    if not context.args:
        await update.message.reply_text("❌ Использование: /rag_delete <ID документа>")
        return

    try:
        doc_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return

    rag_components = get_rag_components()
    uploader = rag_components.get('document_uploader')

    if not uploader:
        await update.message.reply_text("❌ RAG система не инициализирована.")
        return

    try:
        success = await uploader.delete_document(doc_id)

        if success:
            await update.message.reply_text(f"✅ Документ ID={doc_id} удалён.")
            logger.info(f"Админ {user_id} удалил документ ID={doc_id}")
        else:
            await update.message.reply_text(f"❌ Не удалось удалить документ ID={doc_id}")

    except Exception as e:
        logger.error(f"Ошибка удаления документа: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


# ======================= --- Функция запуска ---====================================


async def main_async():
    """Точка входа — асинхронная функция"""
    await init_db()

    # ИНИЦИАЛИЗАЦИЯ RAG СИСТЕМЫ
    rag_initialized = False
    if settings.RAG_ENABLED and settings.AI_ENABLED:
        try:
            rag_initialized = await init_rag_system(settings, ai_assistant)
            if rag_initialized:
                logger.info("✅ RAG система инициализирована")
            else:
                logger.warning("⚠️ RAG система не инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации RAG: {e}")
            rag_initialized = False
    else:
        logger.info("ℹ️ RAG отключён в настройках")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # Логируем статус AI
    if settings.AI_ENABLED:
        logger.info(f"✅ AI включен (model: {ai_assistant.model})")
        if settings.COLLECT_TRAINING_DATA:
            logger.info(f"✅ Включена функция фитбэка и записи сообщений")
    else:
        logger.info("❌ AI Assistant отключен в настройках")

    # Основные обработчики
    application.add_handler(CallbackQueryHandler(inlinehandler.handler_begin_registartion, pattern="^(registration|info)$"))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("exit", logout_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(CommandHandler("add_wl", add_to_wl_command))
    application.add_handler(CommandHandler("remove_wl", remove_from_wl_command))
    application.add_handler(CommandHandler("show_wl", show_wl_command))
    application.add_handler(CommandHandler("wl_help", wl_help_command))

    # Обработчики RAG для админов (загрузка документов)
    if rag_initialized:
        # Обработчик загрузки документов (PDF, TXT)
        application.add_handler(MessageHandler(
            filters.Document.ALL,
            handle_document_upload
        ))
        # Команды управления RAG
        application.add_handler(CommandHandler("rag_stats", handle_rag_stats))
        application.add_handler(CommandHandler("rag_docs", handle_rag_docs))
        application.add_handler(CommandHandler("rag_delete", handle_rag_delete))
        logger.info("✅ RAG обработчики добавлены")

    logger.info("Bot starting with PostgreSQL...")

    # Запуск бота
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        logger.info("✅ Bot started successfully with concurrent updates enabled")

        try:
            # Простой цикл ожидания
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            logger.info("Bot stopping by user request...")
        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            # Закрываем RAG соединения
            try:
                await close_rag_system()
            except Exception as e:
                logger.error(f"Ошибка закрытия RAG: {e}")

            await close_db()
            logger.info("✅ PostgreSQL pool closed")
            logger.info("✅ Bot stopped successfully")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main_async())