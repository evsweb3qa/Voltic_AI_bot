from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove

class InlineKeyboard:
    def get_auth_begin_keyboard() -> InlineKeyboardMarkup:
        keyboard = [[InlineKeyboardButton("✔️ Регистрация", callback_data="registration")]]
        return InlineKeyboardMarkup(keyboard)
    def get_auth_keyboard() -> InlineKeyboardMarkup:
        button_1 = [InlineKeyboardButton("✔️ Регистрация", callback_data="registration")]
        botton_2 = [InlineKeyboardButton("ℹ️ Info", callback_data="info")]
        keyboard = [button_1, botton_2]
        return InlineKeyboardMarkup(keyboard)
    def get_info_keyboard() -> InlineKeyboardMarkup:
        button_1 = [[InlineKeyboardButton("ℹ️ Info", callback_data="info")]]
        return InlineKeyboardMarkup(button_1)
    def get_cancellation_keyboard() -> InlineKeyboardMarkup:
        button_1 = [InlineKeyboardButton("Отмена", callback_data="cancellation")]
        return InlineKeyboardMarkup(button_1)
# Глобальный экземпляр
inlinekeyboard = InlineKeyboard

class ReplyKeyboard:
    def get_main_keyboard():
        """Создает основную клавиатуру с кнопками"""
        keyboard = [
            [KeyboardButton("📊 Данные"), KeyboardButton("📈 Аналитика")],
            [KeyboardButton("📝 Учёт"), KeyboardButton("ℹ️ Info")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
# Глобальный экземпляр
replykeyboard = ReplyKeyboard