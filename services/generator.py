import aiohttp
import asyncio
import logging
import urllib.parse
import base64
import json
from config import (
    POLLINATIONS_IMAGE_URL, HF_TOKEN, HF_IMAGE_MODEL,
    STABILITY_KEY, REPLICATE_TOKEN, IMAGE_WIDTH, IMAGE_HEIGHT
)

logger = logging.getLogger(__name__)


# ============================================================
#  ГЕНЕРАЦИЯ КАРТИНОК
# ============================================================

async def generate_image_pollinations(prompt: str) -> bytes | None:
    """
    Pollinations.ai — полностью БЕСПЛАТНЫЙ, без регистрации.
    Возвращает байты PNG.
    """
    try:
        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={IMAGE_WIDTH}&height={IMAGE_HEIGHT}&nologo=true&enhance=true&model=flux"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    logger.info(f"Pollinations image generated, size: {len(data)} bytes")
                    return data
                else:
                    logger.warning(f"Pollinations returned {resp.status}")
                    return None
    except Exception as e:
        logger.error(f"Pollinations error: {e}")
        return None


async def generate_image_hf(prompt: str) -> bytes | None:
    """
    Hugging Face Inference API — БЕСПЛАТНЫЙ tier.
    Нужен бесплатный токен с huggingface.co
    """
    if not HF_TOKEN:
        return None
    try:
        url = f"https://api-inference.huggingface.co/models/{HF_IMAGE_MODEL}"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {"inputs": prompt, "parameters": {"num_inference_steps": 4}}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    logger.info(f"HF image generated, size: {len(data)} bytes")
                    return data
                else:
                    text = await resp.text()
                    logger.warning(f"HF returned {resp.status}: {text[:200]}")
                    return None
    except Exception as e:
        logger.error(f"HF error: {e}")
        return None


async def generate_image(prompt: str) -> bytes | None:
    """
    Основная функция генерации изображений.
    Пробует источники по порядку: HF → Pollinations
    """
    # 1. Hugging Face (если есть токен)
    if HF_TOKEN:
        result = await generate_image_hf(prompt)
        if result:
            return result

    # 2. Pollinations (всегда бесплатный, fallback)
    result = await generate_image_pollinations(prompt)
    if result:
        return result

    return None


# ============================================================
#  ГЕНЕРАЦИЯ ВИДЕО
# ============================================================

async def generate_video_replicate(prompt: str, duration: int = 5) -> str | None:
    """
    Replicate.com — есть бесплатный tier ($5 кредитов при регистрации).
    Модель: minimax/video-01 или wan-video
    Возвращает URL видео.
    """
    if not REPLICATE_TOKEN:
        return None
    try:
        headers = {
            "Authorization": f"Token {REPLICATE_TOKEN}",
            "Content-Type": "application/json"
        }
        # Используем wan-2.1-i2v-480p — одна из самых доступных
        payload = {
            "version": "fdb5526f1b87f47d9a29a93d94f42bfb419a3c49b0e8c7b44a0e45ef56e23db6",
            "input": {
                "prompt": prompt,
                "num_frames": duration * 8,
                "fps": 8
            }
        }
        async with aiohttp.ClientSession() as session:
            # Запускаем задачу
            async with session.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 201:
                    return None
                prediction = await resp.json()
                prediction_id = prediction["id"]

            # Ждём результата (до 3 минут)
            for _ in range(36):
                await asyncio.sleep(5)
                async with session.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers=headers
                ) as resp:
                    data = await resp.json()
                    if data["status"] == "succeeded":
                        output = data.get("output")
                        if isinstance(output, list):
                            return output[0]
                        return output
                    elif data["status"] == "failed":
                        logger.error(f"Replicate failed: {data.get('error')}")
                        return None
    except Exception as e:
        logger.error(f"Replicate error: {e}")
    return None


async def generate_video_stability(prompt: str, duration: int = 5) -> bytes | None:
    """
    Stability AI Video — бесплатные кредиты при регистрации.
    """
    if not STABILITY_KEY:
        return None
    try:
        headers = {
            "Authorization": f"Bearer {STABILITY_KEY}",
            "Content-Type": "application/json"
        }
        # Сначала генерируем стартовый кадр
        img_data = await generate_image_pollinations(prompt)
        if not img_data:
            return None

        # Отправляем на img2vid
        form = aiohttp.FormData()
        form.add_field("image", img_data, content_type="image/png", filename="frame.png")
        form.add_field("cfg_scale", "1.8")
        form.add_field("motion_bucket_id", "127")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.stability.ai/v2beta/image-to-video",
                headers={"Authorization": f"Bearer {STABILITY_KEY}"},
                data=form, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Stability video init failed: {resp.status}")
                    return None
                result = await resp.json()
                gen_id = result.get("id")
                if not gen_id:
                    return None

            # Ждём результата
            for _ in range(24):
                await asyncio.sleep(10)
                async with session.get(
                    f"https://api.stability.ai/v2beta/image-to-video/result/{gen_id}",
                    headers={
                        "Authorization": f"Bearer {STABILITY_KEY}",
                        "Accept": "video/*"
                    }
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    elif resp.status == 202:
                        continue
                    else:
                        return None
    except Exception as e:
        logger.error(f"Stability video error: {e}")
    return None


async def generate_video(prompt: str, duration: int = 5) -> bytes | str | None:
    """
    Основная функция генерации видео.
    Пробует: Replicate → Stability
    Возвращает bytes (видео) или str (URL видео)
    """
    # 1. Replicate
    if REPLICATE_TOKEN:
        result = await generate_video_replicate(prompt, duration)
        if result:
            # Скачиваем видео по URL
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(result, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        if resp.status == 200:
                            return await resp.read()
            except Exception as e:
                logger.error(f"Error downloading replicate video: {e}")

    # 2. Stability AI
    if STABILITY_KEY:
        result = await generate_video_stability(prompt, duration)
        if result:
            return result

    return None


async def translate_to_english(prompt: str) -> str:
    """
    Простой перевод через Pollinations text API (бесплатно).
    Нужен только если пользователь пишет по-русски.
    """
    try:
        text = f"Translate this to English for AI image generation, respond with translation only: {prompt}"
        encoded = urllib.parse.quote(text)
        url = f"https://text.pollinations.ai/{encoded}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    result = await resp.text()
                    return result.strip()
    except Exception as e:
        logger.error(f"Translation error: {e}")
    return prompt  # возвращаем оригинал если не получилось


def has_cyrillic(text: str) -> bool:
    return any('\u0400' <= c <= '\u04FF' for c in text)
