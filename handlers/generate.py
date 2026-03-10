import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import get_user, create_user, use_free_image, use_free_video, deduct_balance, log_generation
from services.generator import generate_image, generate_image_img2img, generate_video, translate_to_english, has_cyrillic
from utils.keyboards import main_menu_kb, video_duration_kb, image_type_kb
from config import PRICE_IMAGE, PRICE_VIDEO_SHORT, PRICE_VIDEO_LONG

logger = logging.getLogger(__name__)
router = Router()


class GenerateStates(StatesGroup):
    # Картинка
    waiting_image_prompt = State()       # только промпт
    waiting_img2img_photo = State()      # ждём фото
    waiting_img2img_prompt = State()     # ждём промпт после фото
    # Видео
    choosing_video_duration = State()
    waiting_video_prompt = State()


def check_balance(user, price):
    """Проверяет бесплатные слоты и баланс"""
    has_free = user["free_images"] > 0
    has_balance = user["balance"] >= price
    return has_free, has_balance


# ===========================
#  КАРТИНКА — выбор режима
# ===========================

@router.message(F.text == "🖼 Картинка")
async def cmd_image(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        create_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
        user = get_user(message.from_user.id)

    has_free, has_balance = check_balance(user, PRICE_IMAGE)
    if not has_free and not has_balance:
        await message.answer(
            f"❌ <b>Недостаточно средств</b>\n\n"
            f"💰 Баланс: {user['balance']}₽ (нужно {PRICE_IMAGE}₽)\n\n"
            f"Пополните кнопкой <b>➕ Пополнить</b>",
            parse_mode="HTML"
        )
        return

    cost_info = "🎁 Бесплатный слот" if has_free else f"💵 Спишется {PRICE_IMAGE}₽"
    await message.answer(
        f"🖼 <b>Генерация картинки</b>\n\n"
        f"{cost_info}\n\n"
        f"Выберите режим:",
        parse_mode="HTML",
        reply_markup=image_type_kb()
    )


# ===========================
#  РЕЖИМ 1: только промпт
# ===========================

@router.callback_query(F.data == "img_prompt")
async def img_prompt_mode(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "✏️ <b>Генерация по описанию</b>\n\n"
        "Напишите что хотите получить:\n"
        "<i>Например: «закат над горами, реалистично, 4K»</i>",
        parse_mode="HTML"
    )
    await state.set_state(GenerateStates.waiting_image_prompt)
    await call.answer()


@router.message(GenerateStates.waiting_image_prompt)
async def process_image_prompt(message: Message, state: FSMContext):
    await state.clear()
    prompt = message.text.strip()
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        return

    use_free = user["free_images"] > 0
    if not use_free and user["balance"] < PRICE_IMAGE:
        await message.answer("❌ Недостаточно средств.")
        return

    wait_msg = await message.answer(
        f"⏳ <b>Генерирую картинку...</b>\n\n"
        f"📝 <i>{prompt[:100]}</i>\n\n"
        f"⏱ ~20-40 секунд",
        parse_mode="HTML"
    )
    try:
        eng_prompt = prompt
        if has_cyrillic(prompt):
            eng_prompt = await translate_to_english(prompt)
            logger.info(f"Translated: {prompt} -> {eng_prompt}")

        image_data = await generate_image(eng_prompt)

        if not image_data:
            await wait_msg.edit_text(
                "❌ <b>Ошибка генерации</b>\n\nПопробуйте другой запрос.\nСредства не списаны.",
                parse_mode="HTML"
            )
            return

        if use_free:
            use_free_image(user_id)
            payment_note = "🎁 Использован бесплатный слот"
        else:
            deduct_balance(user_id, PRICE_IMAGE)
            payment_note = f"💵 Списано {PRICE_IMAGE}₽"

        log_generation(user_id, "image", prompt, PRICE_IMAGE if not use_free else 0)
        await wait_msg.delete()
        await message.answer_photo(
            BufferedInputFile(image_data, filename="image.png"),
            caption=f"✅ <b>Готово!</b>\n\n📝 <i>{prompt[:100]}</i>\n{payment_note}",
            parse_mode="HTML",
            reply_markup=main_menu_kb()
        )
    except Exception as e:
        logger.error(f"Image prompt error: {e}")
        await wait_msg.edit_text("❌ Произошла ошибка. Попробуйте позже.")


# ===========================
#  РЕЖИМ 2: фото + промпт
# ===========================

@router.callback_query(F.data == "img_photo")
async def img_photo_mode(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "🖼 <b>Генерация по фото + описанию</b>\n\n"
        "Отправьте фото которое хотите изменить:",
        parse_mode="HTML"
    )
    await state.set_state(GenerateStates.waiting_img2img_photo)
    await call.answer()


@router.message(GenerateStates.waiting_img2img_photo, F.photo)
async def process_img2img_photo(message: Message, state: FSMContext, bot: Bot):
    # Скачиваем фото
    photo = message.photo[-1]  # берём наибольшее разрешение
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    photo_data = file_bytes.read()

    await state.update_data(photo_data=photo_data)
    await message.answer(
        "✏️ Теперь напишите <b>что сделать с фото</b>:\n\n"
        "<i>Например: «сделай аниме стиль», «добавь снег», «измени фон на космос»</i>",
        parse_mode="HTML"
    )
    await state.set_state(GenerateStates.waiting_img2img_prompt)


@router.message(GenerateStates.waiting_img2img_photo)
async def process_img2img_no_photo(message: Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте фото (не файл, а именно фото).")


@router.message(GenerateStates.waiting_img2img_prompt)
async def process_img2img_prompt(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    prompt = message.text.strip()
    photo_data = data.get("photo_data")
    user_id = message.from_user.id
    user = get_user(user_id)

    if not user or not photo_data:
        await message.answer("❌ Ошибка. Попробуйте снова.")
        return

    use_free = user["free_images"] > 0
    if not use_free and user["balance"] < PRICE_IMAGE:
        await message.answer("❌ Недостаточно средств.")
        return

    wait_msg = await message.answer(
        f"⏳ <b>Обрабатываю фото...</b>\n\n"
        f"📝 <i>{prompt[:100]}</i>\n\n"
        f"⏱ ~30-60 секунд",
        parse_mode="HTML"
    )
    try:
        eng_prompt = prompt
        if has_cyrillic(prompt):
            eng_prompt = await translate_to_english(prompt)
            logger.info(f"Translated: {prompt} -> {eng_prompt}")

        image_data = await generate_image_img2img(photo_data, eng_prompt)

        if not image_data:
            await wait_msg.edit_text(
                "❌ <b>Ошибка генерации</b>\n\nПопробуйте другое фото или описание.\nСредства не списаны.",
                parse_mode="HTML"
            )
            return

        if use_free:
            use_free_image(user_id)
            payment_note = "🎁 Использован бесплатный слот"
        else:
            deduct_balance(user_id, PRICE_IMAGE)
            payment_note = f"💵 Списано {PRICE_IMAGE}₽"

        log_generation(user_id, "img2img", prompt, PRICE_IMAGE if not use_free else 0)
        await wait_msg.delete()
        await message.answer_photo(
            BufferedInputFile(image_data, filename="result.png"),
            caption=f"✅ <b>Готово!</b>\n\n📝 <i>{prompt[:100]}</i>\n{payment_note}",
            parse_mode="HTML",
            reply_markup=main_menu_kb()
        )
    except Exception as e:
        logger.error(f"img2img error: {e}")
        await wait_msg.edit_text("❌ Произошла ошибка. Попробуйте позже.")


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
    has_balance = user["balance"] >= PRICE_VIDEO_SHORT

    if not has_free and not has_balance:
        await message.answer(
            f"❌ <b>Недостаточно средств</b>\n\n"
            f"💰 Баланс: {user['balance']}₽ (минимум {PRICE_VIDEO_SHORT}₽)\n\n"
            f"Пополните кнопкой <b>➕ Пополнить</b>",
            parse_mode="HTML"
        )
        return

    await message.answer(
        "🎬 <b>Генерация видео</b>\n\nВыберите длительность:",
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
        f"✏️ Опишите сцену:\n"
        f"<i>Например: «закат на море, волны, чайки летят»</i>",
        parse_mode="HTML"
    )
    await state.set_state(GenerateStates.waiting_video_prompt)
    await call.answer()


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
        f"📝 <i>{prompt[:100]}</i>\n\n"
        f"⏱ 1-3 минуты, пожалуйста подождите",
        parse_mode="HTML"
    )
    try:
        eng_prompt = prompt
        if has_cyrillic(prompt):
            eng_prompt = await translate_to_english(prompt)

        from services.generator import generate_video
        video_data = await generate_video(eng_prompt, duration)

        if not video_data:
            await wait_msg.edit_text(
                "❌ <b>Ошибка генерации видео</b>\n\nСредства не списаны.",
                parse_mode="HTML"
            )
            return

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
            caption=f"✅ <b>Готово!</b>\n\n📝 <i>{prompt[:100]}</i>\n{payment_note}",
            parse_mode="HTML",
            reply_markup=main_menu_kb()
        )
    except Exception as e:
        logger.error(f"Video error: {e}")
        await wait_msg.edit_text("❌ Произошла ошибка. Попробуйте позже.")


# ===========================
#  ОТМЕНА
# ===========================

@router.callback_query(F.data == "cancel")
async def cancel_action(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("❌ Отменено", reply_markup=main_menu_kb())
    await call.answer()
