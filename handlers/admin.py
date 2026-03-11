import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from database.db import (
    get_all_users, get_stats, confirm_payment, reject_payment,
    get_pending_payments, add_balance, update_user
)
from utils.keyboards import admin_panel_kb, main_menu_kb
from config import ADMIN_IDS

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_user_id = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = get_stats()
    text = (
        f"🔧 <b>Панель администратора</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"🖼 Картинок: <b>{stats['total_images']}</b>\n"
        f"🎬 Видео: <b>{stats['total_videos']}</b>\n"
        f"💰 Доход: <b>{stats['total_income']}₽</b>\n"
        f"⏳ Ожидают оплаты: <b>{stats['pending_payments']}</b>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=admin_panel_kb())


@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    stats = get_stats()
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"🖼 Картинок: <b>{stats['total_images']}</b>\n"
        f"🎬 Видео: <b>{stats['total_videos']}</b>\n"
        f"💰 Доход: <b>{stats['total_income']}₽</b>\n"
        f"⏳ Ожидают: <b>{stats['pending_payments']}</b>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_panel_kb())
    await call.answer()


@router.callback_query(F.data == "admin_pending")
async def admin_pending(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    payments = get_pending_payments()
    if not payments:
        await call.answer("✅ Нет ожидающих платежей", show_alert=True)
        return
    text = f"⏳ <b>Ожидающие платежи ({len(payments)}):</b>\n\n"
    for p in payments[:10]:
        uname = f"@{p['username']}" if p['username'] else p['full_name']
        created = str(p['created_at'])[:16]
        text += f"#{p['id']} | {uname} | <b>{p['amount']}₽</b> | {created}\n"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_panel_kb())
    await call.answer()


@router.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm_payment(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    payment_id = int(call.data.replace("admin_confirm_", ""))
    payment = confirm_payment(payment_id)
    if not payment:
        await call.answer("❌ Платёж не найден или уже обработан", show_alert=True)
        return
    try:
        await bot.send_message(
            payment["user_id"],
            f"✅ <b>Баланс пополнен!</b>\n\n+{payment['amount']}₽ зачислено. Заявка #{payment_id} подтверждена.",
            parse_mode="HTML", reply_markup=main_menu_kb()
        )
    except Exception as e:
        logger.error(f"Notify user error: {e}")
    await call.message.edit_text(
        f"✅ Платёж #{payment_id} подтверждён! Сумма: {payment['amount']}₽",
        parse_mode="HTML"
    )
    await call.answer("✅ Подтверждено!")


@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject_payment(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    parts = call.data.split("_")
    payment_id = int(parts[2])
    user_id = int(parts[3])
    reject_payment(payment_id)
    try:
        await bot.send_message(
            user_id,
            f"❌ <b>Заявка #{payment_id} отклонена.</b>\n\nПо вопросам: @glebknopka",
            parse_mode="HTML"
        )
    except Exception:
        pass
    await call.message.edit_text(f"❌ Платёж #{payment_id} отклонён.", parse_mode="HTML")
    await call.answer("Отклонено")


@router.message(Command("addbalance"))
async def cmd_add_balance(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("❌ /addbalance <user_id> <amount>")
        return
    try:
        user_id = int(args[1])
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Неверный формат")
        return
    if add_balance(user_id, amount, "Ручное пополнение"):
        await message.answer(f"✅ +{amount}₽ → {user_id}")
        try:
            await message.bot.send_message(user_id, f"✅ <b>+{amount}₽ от администратора!</b>", parse_mode="HTML")
        except Exception:
            pass
    else:
        await message.answer("❌ Ошибка")


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    await call.message.edit_text("📢 <b>Рассылка</b>\n\nВведите текст:", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_broadcast)
    await call.answer()


@router.message(AdminStates.waiting_broadcast)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    users = get_all_users()
    sent = 0
    failed = 0
    status_msg = await message.answer(f"📤 Отправляю {len(users)} пользователям...")
    for user in users:
        try:
            await bot.send_message(user["user_id"], message.text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(f"✅ Отправлено: {sent}\n❌ Ошибок: {failed}", parse_mode="HTML")


@router.callback_query(F.data == "admin_find_user")
async def admin_find_user_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    await call.message.edit_text("👤 Введите Telegram ID или @username:")
    await state.set_state(AdminStates.waiting_user_id)
    await call.answer()


@router.message(AdminStates.waiting_user_id)
async def admin_show_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    query = message.text.strip().replace("@", "")
    users = get_all_users()
    found = next((u for u in users if str(u["user_id"]) == query or u["username"] == query), None)
    if not found:
        await message.answer("❌ Пользователь не найден")
        return
    reg = str(found['registered_at'])[:10]
    text = (
        f"👤 <b>Пользователь</b>\n\n"
        f"🆔 <code>{found['user_id']}</code>\n"
        f"👤 {found['full_name']}\n"
        f"📱 @{found['username'] or 'нет'}\n"
        f"💰 Баланс: <b>{found['balance']}₽</b>\n"
        f"🖼 Бесплатных: {found['free_images']} картинок, {found['free_videos']} видео\n"
        f"📊 Создано: {found['total_images']} картинок, {found['total_videos']} видео\n"
        f"📅 Регистрация: {reg}\n\n"
        f"/addbalance {found['user_id']} <сумма>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=admin_panel_kb())
