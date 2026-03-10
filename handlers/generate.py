import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import get_user, create_user, use_free_image, use_free_video, deduct_balance, log_generation
from services.generator import generate_image, generate_video, translate_to_english, has_cyrillic
from utils.keyboards import main_menu_kb, video_duration_kb
from config import PRICE_IMAGE, PRICE_VIDEO_SHORT, PRICE_VIDEO_LONG

logger = logging.getLogger(__name__)
router = Router()


class GenerateStates(StatesGroup):
    waiting_image_prompt = State()
    waiting_video_prompt = State()
    choosing_video_duration = State()
    video_prompt_ready = State()


# ===========================
#  КАРТИНКА
# ===========================

@router.message(F.text == "🖼 Картинка")
async def cmd_image(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        create_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
        user = get_user(message.from_user.id)

    has_free = user["free_images"] > 0
    has_balance = user["balance"] >= PRICE_IMAGE

    if not has_free and not has_balance:
        await message.answer(
            f"❌ <b>Недостаточно средств</b>\n\n"
            f"💰 Ваш баланс: {user['balance']}₽\n"
            f"💵 Нужно: {PRICE_IMAGE}₽\n\n"
            f"Пополните баланс кнопкой <b>➕ Пополнить</b>",
            parse_mode="HTML"
        )
        return

    cost_info = "🎁 Будет использован бесплатный слот" if has_free else f"💵 Спишется {PRICE_IMAGE}₽"
    await message.answer(
        f"🖼 <b>Генерация картинки</b>\n\n"
        f"{cost_info}\n\n"
        f"✏️ Опишите, что хотите получить:\n"
        f"<i>Можно на русском или английском</i>",
        parse_mode="HTML"
    )
    await state.set_state(GenerateStates.waiting_image_prompt)


@router.message(GenerateStates.waiting_image_prompt)
async def process_image_prompt(message: Message, state: FSMContext):
    await state.clear()
    prompt = message.text.strip()
    user_id = message.from_user.id
    user = get_user(user_id)

    if not user:
        return

    # Определяем способ оплаты
    use_free = user["free_images"] > 0
    use_paid = user["balance"] >= PRICE_IMAGE

    if not use_free and not use_paid:
        await message.answer("❌ Недостаточно средств. Пополните баланс.")
        return

    # Отправляем уведомление
    wait_msg = await message.answer(
        f"⏳ <b>Генерирую картинку...</b>\n\n"
        f"📝 Запрос: <i>{prompt[:100]}</i>\n\n"
        f"⏱ Обычно занимает 20-40 секунд",
        parse_mode="HTML"
    )

    try:
        # Переводим если нужно
        eng_prompt = prompt
        if has_cyrillic(prompt):
            eng_prompt = await translate_to_english(prompt)
            logger.info(f"Translated: {prompt} -> {eng_prompt}")

        # Генерируем
        image_data = await generate_image(eng_prompt)

        if not image_data:
            await wait_msg.edit_text(
                "❌ <b>Ошибка генерации</b>\n\n"
                "Попробуйте другой запрос или повторите позже.\n"
                "Средства не списаны.",
                parse_mode="HTML"
            )
            return

        # Списываем средства
        if use_free:
            use_free_image(user_id)
            payment_note = "🎁 Использован бесплатный слот"
        else:
            deduct_balance(user_id, PRICE_IMAGE)
            payment_note = f"💵 Списано {PRICE_IMAGE}₽"

        log_generation(user_id, "image", prompt, PRICE_IMAGE if not use_free else 0)

        # Отправляем картинку
        await wait_msg.delete()
        await message.answer_photo(
            BufferedInputFile(image_data, filename="image.png"),
            caption=f"✅ <b>Готово!</b>\n\n"
                    f"📝 Запрос: <i>{prompt[:100]}</i>\n"
                    f"{payment_note}",
            parse_mode="HTML",
            reply_markup=main_menu_kb()
        )

    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await wait_msg.edit_text(
            "❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


# ===========================
#  ВИДЕО
# ===========================

@router.message(F.text == "🎬 Видео")
async def cmd_video(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        create_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
        user = get_user(message.from_user.id)

    has_free = user["free_videos"] > 0
    has_balance_short = user["balance"] >= PRICE_VIDEO_SHORT

    if not has_free and not has_balance_short:
        await message.answer(
            f"❌ <b>Недостаточно средств</b>\n\n"
            f"💰 Баланс: {user['balance']}₽\n"
            f"💵 Минимум: {PRICE_VIDEO_SHORT}₽ (видео 5 сек)\n\n"
            f"Пополните баланс кнопкой <b>➕ Пополнить</b>",
            parse_mode="HTML"
        )
        return

    await message.answer(
        "🎬 <b>Генерация видео</b>\n\n"
        "Выберите длительность:",
        parse_mode="HTML",
        reply_markup=video_duration_kb()
    )
    await state.set_state(GenerateStates.choosing_video_duration)


@router.callback_query(F.data.in_({"video_5", "video_10"}), GenerateStates.choosing_video_duration)
async def choose_video_duration(call: CallbackQuery, state: FSMContext):
    duration = 5 if call.data == "video_5" else 10
    price = PRICE_VIDEO_SHORT if duration == 5 else PRICE_VIDEO_LONG

    user = get_user(call.from_user.id)
    has_free = user["free_videos"] > 0
    has_balance = user["balance"] >= price

    if not has_free and not has_balance:
        await call.answer(f"❌ Нужно {price}₽, у вас {user['balance']}₽", show_alert=True)
        return

    await state.update_data(duration=duration, price=price)

    cost_info = "🎁 Бесплатный слот" if has_free else f"💵 Спишется {price}₽"
    await call.message.edit_text(
        f"🎬 <b>Видео {duration} секунд</b>\n\n"
        f"{cost_info}\n\n"
        f"✏️ Опишите сцену для видео:\n"
        f"<i>Например: «закат на море, волны, чайки летят»</i>",
        parse_mode="HTML"
    )
    await state.set_state(GenerateStates.waiting_video_prompt)


@router.message(GenerateStates.waiting_video_prompt)
async def process_video_prompt(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    duration = data.get("duration", 5)
    price = data.get("price", PRICE_VIDEO_SHORT)
    prompt = message.text.strip()
    user_id = message.from_user.id
    user = get_user(user_id)

    if not user:
        return

    use_free = user["free_videos"] > 0
    if not use_free and user["balance"] < price:
        await message.answer("❌ Недостаточно средств.")
        return

    wait_msg = await message.answer(
        f"⏳ <b>Генерирую видео {duration} сек...</b>\n\n"
        f"📝 Запрос: <i>{prompt[:100]}</i>\n\n"
        f"⏱ Это занимает 1-3 минуты, пожалуйста подождите",
        parse_mode="HTML"
    )

    try:
        eng_prompt = prompt
        if has_cyrillic(prompt):
            eng_prompt = await translate_to_english(prompt)

        video_data = await generate_video(eng_prompt, duration)

        if not video_data:
            await wait_msg.edit_text(
                "❌ <b>Ошибка генерации видео</b>\n\n"
                "К сожалению, видео не удалось создать.\n"
                "Попробуйте позже или измените запрос.\n"
                "<b>Средства не списаны.</b>",
                parse_mode="HTML"
            )
            return

        # Списываем
        if use_free:
            use_free_video(user_id)
            payment_note = "🎁 Использован бесплатный слот"
        else:
            deduct_balance(user_id, price)
            payment_note = f"💵 Списано {price}₽"

        log_generation(user_id, "video", prompt, price if not use_free else 0)

        await wait_msg.delete()
        await message.answer_video(
            BufferedInputFile(video_data, filename="video.mp4"),
            caption=f"✅ <b>Готово!</b>\n\n"
                    f"📝 Запрос: <i>{prompt[:100]}</i>\n"
                    f"{payment_note}",
            parse_mode="HTML",
            reply_markup=main_menu_kb()
        )

    except Exception as e:
        logger.error(f"Video generation error: {e}")
        await wait_msg.edit_text("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "cancel")
async def cancel_action(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("❌ Отменено", reply_markup=main_menu_kb())
    await call.answer()
