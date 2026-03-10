import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import get_user, create_user, create_payment_request
from utils.keyboards import main_menu_kb, topup_amounts_kb, payment_confirm_kb, admin_payment_kb
from config import (
    ADMIN_IDS, PAYMENT_CARD, PAYMENT_PHONE, PAYMENT_QIWI,
    PRICE_IMAGE, PRICE_VIDEO_SHORT, PRICE_VIDEO_LONG
)

logger = logging.getLogger(__name__)
router = Router()


class PaymentStates(StatesGroup):
    waiting_custom_amount = State()
    waiting_payment_confirm = State()


# ===========================
#  ПОПОЛНЕНИЕ БАЛАНСА
# ===========================

@router.message(F.text == "➕ Пополнить")
async def cmd_topup(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        create_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")

    await message.answer(
        f"➕ <b>Пополнение баланса</b>\n\n"
        f"💡 <b>Тарифы для справки:</b>\n"
        f"  • 🖼 Картинка — {PRICE_IMAGE}₽\n"
        f"  • 🎬 Видео 5 сек — {PRICE_VIDEO_SHORT}₽\n"
        f"  • 🎬 Видео 10 сек — {PRICE_VIDEO_LONG}₽\n\n"
        f"Выберите сумму пополнения:",
        parse_mode="HTML",
        reply_markup=topup_amounts_kb()
    )


@router.callback_query(F.data.startswith("topup_"))
async def process_topup_amount(call: CallbackQuery, state: FSMContext):
    data = call.data.replace("topup_", "")

    if data == "custom":
        await call.message.edit_text(
            "💬 Введите сумму пополнения (минимум 30₽):"
        )
        await state.set_state(PaymentStates.waiting_custom_amount)
        await call.answer()
        return

    amount = int(data)
    await show_payment_details(call.message, call.from_user.id, amount, state)
    await call.answer()


@router.message(PaymentStates.waiting_custom_amount)
async def process_custom_amount(message: Message, state: FSMContext):
    await state.clear()
    try:
        amount = int(message.text.strip())
        if amount < 30:
            await message.answer("❌ Минимальная сумма — 30₽")
            return
        if amount > 50000:
            await message.answer("❌ Максимальная сумма — 50 000₽")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return

    await show_payment_details(message, message.from_user.id, amount, state)


async def show_payment_details(message_or_call, user_id: int, amount: int, state: FSMContext):
    """Показывает реквизиты оплаты и создаёт заявку"""
    payment_id = create_payment_request(user_id, amount)

    # Формируем реквизиты
    methods = []
    if PAYMENT_CARD:
        methods.append(f"💳 <b>Карта:</b> <code>{PAYMENT_CARD}</code>")
    if PAYMENT_PHONE:
        methods.append(f"📱 <b>СБП / Телефон:</b> <code>{PAYMENT_PHONE}</code>")
    if PAYMENT_QIWI:
        methods.append(f"🥝 <b>QIWI:</b> <code>{PAYMENT_QIWI}</code>")

    methods_text = "\n".join(methods)

    text = (
        f"💳 <b>Оплата {amount}₽</b>\n\n"
        f"Переведите ровно <b>{amount}₽</b> по реквизитам:\n\n"
        f"{methods_text}\n\n"
        f"📝 <b>В комментарии к переводу укажите:</b>\n"
        f"<code>ID{payment_id}</code>\n\n"
        f"⚠️ После перевода нажмите кнопку ниже.\n"
        f"Баланс пополняется в течение нескольких минут."
    )

    if hasattr(message_or_call, 'edit_text'):
        await message_or_call.edit_text(text, parse_mode="HTML",
                                         reply_markup=payment_confirm_kb(payment_id))
    else:
        await message_or_call.answer(text, parse_mode="HTML",
                                      reply_markup=payment_confirm_kb(payment_id))


@router.callback_query(F.data.startswith("paid_"))
async def payment_sent(call: CallbackQuery, bot: Bot):
    payment_id = int(call.data.replace("paid_", ""))
    user_id = call.from_user.id
    user = get_user(user_id)

    username = f"@{user['username']}" if user and user['username'] else f"ID{user_id}"
    full_name = user['full_name'] if user else "Неизвестно"

    # Уведомляем пользователя
    await call.message.edit_text(
        f"✅ <b>Заявка #{payment_id} отправлена!</b>\n\n"
        f"Ожидайте подтверждения от администратора.\n"
        f"Обычно это занимает несколько минут.",
        parse_mode="HTML"
    )

    # Уведомляем всех администраторов
    for admin_id in ADMIN_IDS:
        try:
            from database.db import get_connection
            conn = get_connection()
            payment = conn.execute(
                "SELECT * FROM transactions WHERE id = ?", (payment_id,)
            ).fetchone()
            conn.close()

            if payment:
                admin_text = (
                    f"💰 <b>Новая заявка на пополнение #{payment_id}</b>\n\n"
                    f"👤 Пользователь: {full_name} ({username})\n"
                    f"🆔 User ID: <code>{user_id}</code>\n"
                    f"💵 Сумма: <b>{payment['amount']}₽</b>\n\n"
                    f"Подтвердите или отклоните:"
                )
                await bot.send_message(
                    admin_id, admin_text,
                    parse_mode="HTML",
                    reply_markup=admin_payment_kb(payment_id, user_id)
                )
        except Exception as e:
            logger.error(f"Error notifying admin {admin_id}: {e}")

    await call.answer("✅ Заявка отправлена!")
