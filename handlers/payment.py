import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    LabeledPrice, PreCheckoutQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import get_user, create_user, create_payment_request, get_payment, add_balance
from utils.keyboards import main_menu_kb, topup_amounts_kb, topup_method_kb, payment_confirm_kb, admin_payment_kb, stars_amounts_kb
from config import ADMIN_IDS, PAYMENT_CARD, PAYMENT_PHONE, PAYMENT_QIWI, PRICE_IMAGE, PRICE_VIDEO_SHORT, PRICE_VIDEO_LONG

logger = logging.getLogger(__name__)
router = Router()

# 1 звезда ≈ 0.013$ ≈ 1.2₽ (примерный курс)
# Сколько рублей даём за N звёзд:
STARS_TO_RUB = {
    50:  60,   # 50 звёзд → 60₽
    100: 125,  # 100 звёзд → 125₽
    200: 260,  # 200 звёзд → 260₽
    500: 650,  # 500 звёзд → 650₽
}


class PaymentStates(StatesGroup):
    waiting_custom_amount = State()


# ===========================
#  ВЫБОР СПОСОБА ОПЛАТЫ
# ===========================

@router.message(F.text == "➕ Пополнить")
async def cmd_topup(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        create_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    await message.answer(
        f"➕ <b>Пополнение баланса</b>\n\n"
        f"💡 Тарифы:\n"
        f"  • 🖼 Картинка — {PRICE_IMAGE}₽\n"
        f"  • 🎬 Видео 5 сек — {PRICE_VIDEO_SHORT}₽\n"
        f"  • 🎬 Видео 10 сек — {PRICE_VIDEO_LONG}₽\n\n"
        f"Выберите способ оплаты:",
        parse_mode="HTML",
        reply_markup=topup_method_kb()
    )


# ===========================
#  СПОСОБ 1: Telegram Stars
# ===========================

@router.callback_query(F.data == "pay_stars")
async def pay_stars_menu(call: CallbackQuery):
    await call.message.edit_text(
        "⭐ <b>Оплата Telegram Stars</b>\n\n"
        "Звёзды можно купить прямо в Telegram.\n"
        "Выберите количество:",
        parse_mode="HTML",
        reply_markup=stars_amounts_kb()
    )
    await call.answer()


@router.callback_query(F.data.startswith("stars_"))
async def process_stars_payment(call: CallbackQuery, bot: Bot):
    stars = int(call.data.replace("stars_", ""))
    rubles = STARS_TO_RUB.get(stars, stars)

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=f"Пополнение баланса на {rubles}₽",
        description=f"После оплаты {stars} ⭐ на ваш счёт будет зачислено {rubles}₽",
        payload=f"stars_{stars}_{rubles}",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label=f"{rubles}₽", amount=stars)],
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Telegram требует подтвердить заказ в течение 10 секунд"""
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    """Автоматически зачисляем рубли после успешной оплаты звёздами"""
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")  # stars_50_60
    rubles = int(parts[2])
    stars = int(parts[1])
    user_id = message.from_user.id

    add_balance(user_id, rubles, f"Telegram Stars ({stars}⭐)")
    logger.info(f"Stars payment: user={user_id} stars={stars} rubles={rubles}")

    await message.answer(
        f"✅ <b>Оплата прошла!</b>\n\n"
        f"⭐ Звёзд: {stars}\n"
        f"💰 Зачислено: <b>{rubles}₽</b>\n\n"
        f"Можете генерировать!",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )


# ===========================
#  СПОСОБ 2: Ручная оплата (карта/СБП)
# ===========================

@router.callback_query(F.data == "pay_manual")
async def pay_manual_menu(call: CallbackQuery):
    await call.message.edit_text(
        "💳 <b>Оплата переводом</b>\n\nВыберите сумму:",
        parse_mode="HTML",
        reply_markup=topup_amounts_kb()
    )
    await call.answer()


@router.callback_query(F.data.startswith("topup_"))
async def process_topup_amount(call: CallbackQuery, state: FSMContext):
    data = call.data.replace("topup_", "")
    if data == "custom":
        await call.message.edit_text("💬 Введите сумму (минимум 30₽):")
        await state.set_state(PaymentStates.waiting_custom_amount)
        await call.answer()
        return
    amount = int(data)
    await show_payment_details(call.message, call.from_user.id, amount)
    await call.answer()


@router.message(PaymentStates.waiting_custom_amount)
async def process_custom_amount(message: Message, state: FSMContext):
    await state.clear()
    try:
        amount = int(message.text.strip())
        if amount < 30:
            await message.answer("❌ Минимум 30₽")
            return
        if amount > 50000:
            await message.answer("❌ Максимум 50 000₽")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    await show_payment_details(message, message.from_user.id, amount)


async def show_payment_details(msg, user_id: int, amount: int):
    payment_id = create_payment_request(user_id, amount)
    methods = []
    if PAYMENT_CARD:
        methods.append(f"💳 <b>Карта:</b> <code>{PAYMENT_CARD}</code>")
    if PAYMENT_PHONE:
        methods.append(f"📱 <b>СБП:</b> <code>{PAYMENT_PHONE}</code>")
    if PAYMENT_QIWI:
        methods.append(f"🥝 <b>QIWI:</b> <code>{PAYMENT_QIWI}</code>")
    if not methods:
        methods = ["⚠️ Реквизиты не настроены (добавьте PAYMENT_CARD в Railway Variables)"]
    text = (
        f"💳 <b>Оплата {amount}₽</b>\n\n"
        f"Переведите <b>ровно {amount}₽</b>:\n\n"
        f"{chr(10).join(methods)}\n\n"
        f"📝 <b>Комментарий к переводу:</b>\n"
        f"<code>ID{payment_id}</code>\n\n"
        f"После перевода нажмите кнопку ниже ↓"
    )
    if hasattr(msg, 'edit_text'):
        await msg.edit_text(text, parse_mode="HTML", reply_markup=payment_confirm_kb(payment_id))
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=payment_confirm_kb(payment_id))


@router.callback_query(F.data.startswith("paid_"))
async def payment_sent(call: CallbackQuery, bot: Bot):
    payment_id = int(call.data.replace("paid_", ""))
    user_id = call.from_user.id
    user = get_user(user_id)
    payment = get_payment(payment_id)
    if not payment:
        await call.answer("❌ Заявка не найдена", show_alert=True)
        return
    username = f"@{user['username']}" if user and user['username'] else f"ID{user_id}"
    full_name = user['full_name'] if user else "Неизвестно"
    await call.message.edit_text(
        f"✅ <b>Заявка #{payment_id} отправлена!</b>\n\nОжидайте подтверждения (~5 минут).",
        parse_mode="HTML"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>Новая заявка #{payment_id}</b>\n\n"
                f"👤 {full_name} ({username})\n"
                f"🆔 <code>{user_id}</code>\n"
                f"💵 Сумма: <b>{payment['amount']}₽</b>\n\n"
                f"Подтвердите или отклоните:",
                parse_mode="HTML",
                reply_markup=admin_payment_kb(payment_id, user_id)
            )
        except Exception as e:
            logger.error(f"Notify admin {admin_id} error: {e}")
    await call.answer("✅ Заявка отправлена!")
