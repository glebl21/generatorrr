import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from database.db import (
    get_user, get_all_users, get_stats, confirm_payment,
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
    waiting_add_balance_amount = State()


# ===========================
#  АДМИН ПАНЕЛЬ
# ===========================

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return

    stats = get_stats()
    text = (
        f"🔧 <b>Панель администратора</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"🖼 Картинок создано: <b>{stats['total_images']}</b>\n"
        f"🎬 Видео создано: <b>{stats['total_videos']}</b>\n"
        f"💰 Общий доход: <b>{stats['total_income']}₽</b>\n"
        f"⏳ Ожидают оплаты: <b>{stats['pending_payments']}</b>\n"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=admin_panel_kb())


@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    stats = get_stats()
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"🖼 Картинок создано: <b>{stats['total_images']}</b>\n"
        f"🎬 Видео создано: <b>{stats['total_videos']}</b>\n"
        f"💰 Подтверждённый доход: <b>{stats['total_income']}₽</b>\n"
        f"⏳ Ожидают подтверждения: <b>{stats['pending_payments']}</b>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_panel_kb())
    await call.answer()


@router.callback_query(F.data == "admin_pending")
async def admin_pending(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    payments = get_pending_payments()
    if not payments:
        await call.answer("✅ Нет ожидающих платежей", show_alert=True)
        return

    text = f"⏳ <b>Ожидающие платежи ({len(payments)}):</b>\n\n"
    for p in payments[:10]:
        uname = f"@{p['username']}" if p['username'] else p['full_name']
        text += f"#{p['id']} | {uname} | <b>{p['amount']}₽</b> | {p['created_at'][:16]}\n"

    await call.message.edit_text(
        text + "\n\nИспользуйте команду /confirm <payment_id> для подтверждения",
        parse_mode="HTML",
        reply_markup=admin_panel_kb()
    )
    await call.answer()


# ===========================
#  ПОДТВЕРЖДЕНИЕ ПЛАТЕЖЕЙ
# ===========================

@router.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm_payment(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return

    payment_id = int(call.data.replace("admin_confirm_", ""))
    payment = confirm_payment(payment_id)

    if not payment:
        await call.answer("❌ Платёж не найден или уже обработан", show_alert=True)
        return

    # Уведомляем пользователя
    try:
        await bot.send_message(
            payment["user_id"],
            f"✅ <b>Баланс пополнен!</b>\n\n"
            f"💰 +{payment['amount']}₽ зачислено на ваш счёт.\n"
            f"Заявка #{payment_id} подтверждена.",
            parse_mode="HTML",
            reply_markup=main_menu_kb()
        )
    except Exception as e:
        logger.error(f"Error notifying user: {e}")

    await call.message.edit_text(
        f"✅ <b>Платёж #{payment_id} подтверждён!</b>\n"
        f"Сумма: {payment['amount']}₽\n"
        f"Пользователь уведомлён.",
        parse_mode="HTML"
    )
    await call.answer("✅ Подтверждено!")


@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject_payment(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return

    parts = call.data.split("_")
    payment_id = int(parts[2])
    user_id = int(parts[3])

    from database.db import get_connection
    conn = get_connection()
    conn.execute("UPDATE transactions SET status = 'rejected' WHERE id = ?", (payment_id,))
    conn.commit()
    conn.close()

    try:
        await bot.send_message(
            user_id,
            f"❌ <b>Заявка #{payment_id} отклонена</b>\n\n"
            f"Если вы уже перевели деньги — свяжитесь с поддержкой.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await call.message.edit_text(f"❌ Платёж #{payment_id} отклонён.", parse_mode="HTML")
    await call.answer("Отклонено")


# ===========================
#  РУЧНОЕ ПОПОЛНЕНИЕ
# ===========================

@router.message(Command("addbalance"))
async def cmd_add_balance(message: Message):
    """Команда: /addbalance <user_id> <amount>"""
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("❌ Использование: /addbalance <user_id> <amount>")
        return

    try:
        user_id = int(args[1])
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Неверный формат")
        return

    success = add_balance(user_id, amount, "Ручное пополнение администратором")
    if success:
        await message.answer(f"✅ Баланс пользователя {user_id} пополнен на {amount}₽")
        try:
            await message.bot.send_message(
                user_id,
                f"✅ <b>Баланс пополнен администратором!</b>\n\n+{amount}₽",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await message.answer("❌ Ошибка пополнения")


# ===========================
#  РАССЫЛКА
# ===========================

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        "📢 <b>Рассылка</b>\n\nВведите текст сообщения для всех пользователей:",
        parse_mode="HTML"
    )
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

    status_msg = await message.answer(f"📤 Отправляю рассылку {len(users)} пользователям...")

    for user in users:
        try:
            await bot.send_message(user["user_id"], message.text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"✉️ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        parse_mode="HTML"
    )


# ===========================
#  ПОИСК ПОЛЬЗОВАТЕЛЯ
# ===========================

@router.callback_query(F.data == "admin_find_user")
async def admin_find_user(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("👤 Введите Telegram ID или @username пользователя:")
    await state.set_state(AdminStates.waiting_user_id)
    await call.answer()


@router.message(AdminStates.waiting_user_id)
async def admin_show_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    query = message.text.strip().replace("@", "")
    users = get_all_users()

    found = None
    for u in users:
        if str(u["user_id"]) == query or u["username"] == query:
            found = u
            break

    if not found:
        await message.answer("❌ Пользователь не найден")
        return

    text = (
        f"👤 <b>Пользователь</b>\n\n"
        f"🆔 ID: <code>{found['user_id']}</code>\n"
        f"👤 Имя: {found['full_name']}\n"
        f"📱 Username: @{found['username'] or 'нет'}\n"
        f"💰 Баланс: <b>{found['balance']}₽</b>\n"
        f"🖼 Бесплатных картинок: {found['free_images']}\n"
        f"🎬 Бесплатных видео: {found['free_videos']}\n"
        f"📊 Всего картинок: {found['total_images']}\n"
        f"📊 Всего видео: {found['total_videos']}\n"
        f"📅 Регистрация: {found['registered_at'][:10]}\n"
        f"🚫 Забанен: {'Да' if found['is_banned'] else 'Нет'}\n\n"
        f"Пополнить: /addbalance {found['user_id']} <сумма>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=admin_panel_kb())
