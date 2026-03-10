from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🖼 Картинка"), KeyboardButton(text="🎬 Видео")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="➕ Пополнить")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True
    )


def image_type_kb():
    """Выбор типа генерации картинки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ По промпту", callback_data="img_prompt")],
        [InlineKeyboardButton(text="🖼 Фото + промпт", callback_data="img_photo")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def video_duration_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡ 5 сек — 30₽", callback_data="video_5"),
            InlineKeyboardButton(text="🎥 10 сек — 60₽", callback_data="video_10"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])


def topup_amounts_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="50₽", callback_data="topup_50"),
            InlineKeyboardButton(text="100₽", callback_data="topup_100"),
            InlineKeyboardButton(text="200₽", callback_data="topup_200"),
        ],
        [
            InlineKeyboardButton(text="500₽", callback_data="topup_500"),
            InlineKeyboardButton(text="1000₽", callback_data="topup_1000"),
        ],
        [InlineKeyboardButton(text="💬 Другая сумма", callback_data="topup_custom")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])


def payment_confirm_kb(payment_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_{payment_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])


def admin_payment_kb(payment_id: int, user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm_{payment_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_{payment_id}_{user_id}"),
        ]
    ])


def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💳 Ожидающие оплаты", callback_data="admin_pending")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="👤 Найти пользователя", callback_data="admin_find_user")],
    ])


def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="cancel")]
    ])
