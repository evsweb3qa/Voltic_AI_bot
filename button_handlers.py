from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove
import logging
from keyboard.keyboard import replykeyboard, inlinekeyboard
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from database.database import get_user_by_telegram_id, register_user
# --- Настройка логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    force=True
)
logger = logging.getLogger(__name__)


class InlineHandler:
    async def handler_begin_registartion(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        #user = update.effective_user
        await query.answer()
        user_id = query.from_user.id
        username = query.from_user.username
        logger.info(f"button_handler: action={query.data}, user_id={user_id}")

        action = query.data

        try:
            if action == "registration":
                success, message = await register_user(user_id, username)
                if success:
                    await query.message.reply_text(
                        message, reply_markup=inlinekeyboard.get_info_keyboard(),
                        parse_mode="Markdown")
                else:
                    await query.message.reply_text(message)

            elif action == "info":
                registration_check = await get_user_by_telegram_id(user_id)
                if not registration_check:
                    await query.message.reply_text(
                        " *Возникли вопросы? Не знаешь,Что делать?*\n\n",
                        reply_markup=inlinekeyboard.get_auth_begin_keyboard(),
                        parse_mode="Markdown"
                    )
                else:
                    await query.message.reply_text(
                        "*Возникли вопросы? Я помогу тебе найти на них ответы.*\n"
                        "*Ознакомься с моими основными командами:*\n"
                        "1. /exit - выход из системы\n",
                        parse_mode="Markdown"
                    )
            else:
                await query.message.reply_text("Неизвестная команда")
                return
        except Exception as e:
            logger.error(f"Error in button_handler: {e}", exc_info=True)
            await query.message.reply_text(f"❌ Ошибка при получении данных: {e}")

inlinehandler = InlineHandler


class ReplyHandler:

    async def handle_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE, async_w3):
        """Обработчик кнопки Данные"""
        user_id = update.effective_user.id
        get_user = await get_user_by_telegram_id(user_id)
        registration_check = bool(get_user)

        if not registration_check:
            await update.message.reply_text(
                "❌ Вы не зарегистрированы в системе",
                reply_markup=inlinekeyboard.get_auth_keyboard()
            )
            return

        try:
            message = await update.message.reply_text("🔄 Receiving data, please wait...")
            data = await process_user_data(user_id, async_w3)
            await message.edit_text(text=data, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error in handle_data_command: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")


replyhandler = ReplyHandler()