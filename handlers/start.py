from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from database.db import get_user, create_user
from utils.keyboards import main_menu_kb
from config import FREE_IMAGES, FREE_VIDEOS

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""

    user = get_user(user_id)
    if not user:
        create_user(user_id, username, full_name)
        text = (
            f"👋 Добро пожаловать, {full_name}!\n\n"
            f"🎨 <b>AI Генератор изображений и видео</b>\n\n"
            f"🎁 <b>Подарок новичку:</b>\n"
            f"  • {FREE_IMAGES} бесплатных картинок\n"
            f"  • {FREE_VIDEOS} бесплатное видео\n\n"
            f"📋 <b>Тарифы:</b>\n"
            f"  • 🖼 Картинка — <b>10₽</b>\n"
            f"  • 🎬 Видео 5 сек — <b>30₽</b>\n"
            f"  • 🎬 Видео 10 сек — <b>60₽</b>\n\n"
            f"Выберите действие в меню ниже 👇"
        )
    else:
        text = (
            f"👋 С возвращением, {full_name}!\n\n"
            f"💰 Баланс: <b>{user['balance']}₽</b>\n"
            f"🖼 Бесплатных картинок: <b>{user['free_images']}</b>\n"
            f"🎬 Бесплатных видео: <b>{user['free_videos']}</b>\n\n"
            f"Выберите действие 👇"
        )

    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_kb())


@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    text = (
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Нажмите <b>🖼 Картинка</b> или <b>🎬 Видео</b>\n"
        "2️⃣ Напишите <b>описание</b> на русском или английском\n"
        "3️⃣ Дождитесь результата (20-60 сек)\n\n"
        "💡 <b>Советы для лучшего результата:</b>\n"
        "• Описывайте детально: стиль, цвета, настроение\n"
        "• Например: «закат над горами, реалистично, 4K»\n"
        "• Или: «портрет девушки, аниме стиль, яркие цвета»\n\n"
        "💰 <b>Тарифы:</b>\n"
        "  • 🖼 Картинка — 10₽\n"
        "  • 🎬 Видео 5 сек — 30₽\n"
        "  • 🎬 Видео 10 сек — 60₽\n\n"
        "❓ Проблемы? Напишите @glebknopka"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_kb())


@router.message(F.text == "💰 Баланс")
async def cmd_balance(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Используйте /start для регистрации")
        return

    text = (
        f"💰 <b>Ваш баланс</b>\n\n"
        f"💵 Рублей: <b>{user['balance']}₽</b>\n"
        f"🖼 Бесплатных картинок: <b>{user['free_images']}</b>\n"
        f"🎬 Бесплатных видео: <b>{user['free_videos']}</b>\n\n"
        f"📊 <b>Всего создано:</b>\n"
        f"  • Картинок: {user['total_images']}\n"
        f"  • Видео: {user['total_videos']}\n"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_kb())
