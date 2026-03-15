import logging
import uuid
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import get_user, create_user, create_payment_request, get_payment, add_balance
from utils.keyboards import (
    main_menu_kb, topup_amounts_kb, topup_method_kb,
    payment_confirm_kb, admin_payment_kb, stars_amounts_kb, yukassa_amounts_kb
)
from config import ADMIN_IDS, PAYMENT_CARD, PAYMENT_PHONE, PAYMENT_QIWI, PRICE_IMAGE, PRICE_VIDEO_SHORT, PRICE_VIDEO_LONG

logger = logging.getLogger(__name__)
router = Router()

YUKASSA_SHOP_ID = os.getenv("YUKASSA_SHOP_ID", "")
YUKASSA_SECRET_KEY = os.getenv("YUKASSA_SECRET_KEY", "")

# Stars курс
STARS_TO_RUB = {
    50: 60,
    100: 125,
    200: 260,
    500: 650,
}


class PaymentStates(StatesGroup):
    waiting_custom_amount = State()
    waiting_yukassa_amount = State()


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
#  СПОСОБ 1: ЮКасса
# ===========================

@router.callback_query(F.data == "pay_yukassa")
async def pay_yukassa_menu(call: CallbackQuery):
    await call.message.edit_text(
        "💳 <b>Оплата картой (ЮКасса)</b>\n\nВыберите сумму:",
        parse_mode="HTML",
        reply_markup=yukassa_amounts_kb()
    )
    await call.answer()


@router.callback_query(F.data.startswith("yukassa_"))
async def process_yukassa_payment(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = call.data.replace("yukassa_", "")

    if data == "custom":
        await call.message.edit_text("💬 Введите сумму пополнения (минимум 60₽):")
        await state.set_state(PaymentStates.waiting_yukassa_amount)
        await call.answer()
        return

    amount = int(data)
    await create_yukassa_payment(call.message, call.from_user.id, amount, bot)
    await call.answer()


@router.message(PaymentStates.waiting_yukassa_amount)
async def process_yukassa_custom_amount(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    try:
        amount = int(message.text.strip())
        if amount < 60:
            await message.answer("❌ Минимум 60₽")
            return
        if amount > 100000:
            await message.answer("❌ Максимум 100 000₽")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    await create_yukassa_payment(message, message.from_user.id, amount, bot)


async def create_yukassa_payment(msg, user_id: int, amount: int, bot: Bot):
    if not YUKASSA_SHOP_ID or not YUKASSA_SECRET_KEY:
        await msg.edit_text("❌ ЮКасса не настроена. Используйте другой способ оплаты.")
        return

    try:
        from yookassa import Configuration, Payment
        Configuration.account_id = YUKASSA_SHOP_ID
        Configuration.secret_key = YUKASSA_SECRET_KEY

        idempotence_key = str(uuid.uuid4())
        payment = Payment.create({
            "amount": {
                "value": f"{amount}.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{(await bot.get_me()).username}"
            },
            "capture": True,
            "description": f"Пополнение баланса на {amount}₽ | user_id={user_id}",
            "metadata": {
                "user_id": str(user_id),
                "amount_rub": str(amount)
            }
        }, idempotence_key)

        # Сохраняем payment_id в БД
        db_payment_id = create_payment_request(user_id, amount)

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment.confirmation.confirmation_url)],
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_yukassa_{payment.id}_{amount}_{user_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
        ])

        text = (
            f"💳 <b>Оплата {amount}₽ через ЮКассу</b>\n\n"
            f"1. Нажмите кнопку <b>Оплатить</b>\n"
            f"2. Введите данные карты\n"
            f"3. Вернитесь и нажмите <b>Я оплатил</b>\n\n"
            f"⏱ Ссылка действует 1 час"
        )

        if hasattr(msg, 'edit_text'):
            await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await msg.answer(text, parse_mode="HTML", reply_markup=kb)

    except Exception as e:
        logger.error(f"YooKassa error: {e}")
        await msg.edit_text(f"❌ Ошибка создания платежа. Попробуйте позже.\n<code>{str(e)[:100]}</code>", parse_mode="HTML")


@router.callback_query(F.data.startswith("check_yukassa_"))
async def check_yukassa_payment(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    # check_yukassa_<payment_id>_<amount>_<user_id>
    payment_id = parts[2]
    amount = int(parts[3])
    user_id = int(parts[4])

    try:
        from yookassa import Configuration, Payment
        Configuration.account_id = YUKASSA_SHOP_ID
        Configuration.secret_key = YUKASSA_SECRET_KEY

        payment = Payment.find_one(payment_id)

        if payment.status == "succeeded":
            # Зачисляем баланс
            add_balance(user_id, amount, f"ЮКасса {payment_id}")
            await call.message.edit_text(
                f"✅ <b>Оплата прошла!</b>\n\n"
                f"💰 Зачислено: <b>{amount}₽</b>\n\n"
                f"Можете генерировать!",
                parse_mode="HTML",
                reply_markup=main_menu_kb()
            )
            logger.info(f"YooKassa payment success: user={user_id} amount={amount}")
        elif payment.status == "pending":
            await call.answer("⏳ Оплата ещё не прошла. Попробуйте через минуту.", show_alert=True)
        elif payment.status == "canceled":
            await call.answer("❌ Платёж отменён.", show_alert=True)
        else:
            await call.answer(f"Статус: {payment.status}", show_alert=True)

    except Exception as e:
        logger.error(f"YooKassa check error: {e}")
        await call.answer("❌ Ошибка проверки платежа. Попробуйте позже.", show_alert=True)

    await call.answer()


# ===========================
#  СПОСОБ 2: Telegram Stars
# ===========================

@router.callback_query(F.data == "pay_stars")
async def pay_stars_menu(call: CallbackQuery):
    await call.message.edit_text(
        "⭐ <b>Оплата Telegram Stars</b>\n\nВыберите количество:",
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
        title=f"Пополнение на {rubles}₽",
        description=f"{stars} ⭐ → {rubles}₽ на баланс",
        payload=f"stars_{stars}_{rubles}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{rubles}₽", amount=stars)],
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")
    rubles = int(parts[2])
    stars = int(parts[1])
    user_id = message.from_user.id
    add_balance(user_id, rubles, f"Telegram Stars ({stars}⭐)")
    await message.answer(
        f"✅ <b>Оплата Stars прошла!</b>\n\n⭐ {stars} звёзд\n💰 Зачислено: <b>{rubles}₽</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )


# ===========================
#  СПОСОБ 3: Ручная (карта/СБП)
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
    if not methods:
        methods = ["⚠️ Реквизиты не настроены"]
    text = (
        f"💳 <b>Оплата {amount}₽</b>\n\n"
        f"Переведите <b>ровно {amount}₽</b>:\n\n"
        f"{chr(10).join(methods)}\n\n"
        f"📝 <b>Комментарий:</b> <code>ID{payment_id}</code>\n\n"
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
        f"✅ <b>Заявка #{payment_id} отправлена!</b>\n\nОжидайте подтверждения.",
        parse_mode="HTML"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>Новая заявка #{payment_id}</b>\n\n"
                f"👤 {full_name} ({username})\n"
                f"🆔 <code>{user_id}</code>\n"
                f"💵 <b>{payment['amount']}₽</b>\n\n"
                f"Подтвердите или отклоните:",
                parse_mode="HTML",
                reply_markup=admin_payment_kb(payment_id, user_id)
            )
        except Exception as e:
            logger.error(f"Notify admin error: {e}")
    await call.answer("✅ Отправлено!")
