from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import os


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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ По промпту", callback_data="img_prompt")],
        [InlineKeyboardButton(text="🖼 Фото + промпт", callback_data="img_photo")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def api_choice_kb(mode: str):
    buttons = []
    if mode == "prompt":
        if os.getenv("HF_TOKEN"):
            buttons.append([InlineKeyboardButton(text="⚡ HuggingFace FLUX — лучшее", callback_data="api_hf")])
        if os.getenv("TOGETHER_TOKEN"):
            buttons.append([InlineKeyboardButton(text="🔥 Together.ai FLUX Free", callback_data="api_together")])
        if os.getenv("GETIMG_TOKEN"):
            buttons.append([InlineKeyboardButton(text="🎨 GetImg.ai FLUX", callback_data="api_getimg")])
        buttons.append([InlineKeyboardButton(text="🔀 Авто (лучший доступный)", callback_data="api_auto")])
    elif mode == "img2img":
        if os.getenv("TOGETHER_TOKEN"):
            buttons.append([InlineKeyboardButton(text="🔥 Together.ai FLUX Depth", callback_data="api_together")])
        if os.getenv("REPLICATE_TOKEN"):
            buttons.append([InlineKeyboardButton(text="🎬 Replicate FLUX Dev", callback_data="api_together_rep")])
        buttons.append([InlineKeyboardButton(text="🔀 Авто (лучший доступный)", callback_data="api_auto")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def topup_method_kb():
    buttons = []
    if os.getenv("YUKASSA_SHOP_ID"):
        buttons.append([InlineKeyboardButton(text="💳 Карта / СБП (ЮКасса)", callback_data="pay_yukassa")])
    buttons.append([InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="pay_stars")])
    buttons.append([InlineKeyboardButton(text="💵 Перевод на карту (вручную)", callback_data="pay_manual")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def yukassa_amounts_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="60₽", callback_data="yukassa_60"),
            InlineKeyboardButton(text="100₽", callback_data="yukassa_100"),
            InlineKeyboardButton(text="200₽", callback_data="yukassa_200"),
        ],
        [
            InlineKeyboardButton(text="500₽", callback_data="yukassa_500"),
            InlineKeyboardButton(text="1000₽", callback_data="yukassa_1000"),
        ],
        [InlineKeyboardButton(text="💬 Любая сумма", callback_data="yukassa_custom")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def stars_amounts_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="50 ⭐ → 60₽", callback_data="stars_50"),
            InlineKeyboardButton(text="100 ⭐ → 125₽", callback_data="stars_100"),
        ],
        [
            InlineKeyboardButton(text="200 ⭐ → 260₽", callback_data="stars_200"),
            InlineKeyboardButton(text="500 ⭐ → 650₽", callback_data="stars_500"),
        ],
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
