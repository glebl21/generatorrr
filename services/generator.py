import aiohttp
import asyncio
import logging
import urllib.parse
from config import (
    HF_TOKEN, HF_IMAGE_MODEL,
    STABILITY_KEY, REPLICATE_TOKEN, IMAGE_WIDTH, IMAGE_HEIGHT
)

logger = logging.getLogger(__name__)


# ============================================================
#  ПЕРЕВОД ПРОМПТА
# ============================================================

# Простой словарь частых русских слов для перевода без API
RU_EN_DICT = {
    "кот": "cat", "кошка": "cat", "собака": "dog", "пёс": "dog",
    "девушка": "girl", "женщина": "woman", "мужчина": "man", "парень": "guy",
    "лес": "forest", "море": "sea", "океан": "ocean", "горы": "mountains",
    "город": "city", "дом": "house", "замок": "castle", "дворец": "palace",
    "закат": "sunset", "рассвет": "sunrise", "ночь": "night", "день": "day",
    "небо": "sky", "облака": "clouds", "звёзды": "stars", "луна": "moon",
    "солнце": "sun", "огонь": "fire", "вода": "water", "земля": "earth",
    "красивый": "beautiful", "красивая": "beautiful", "огромный": "huge",
    "маленький": "small", "тёмный": "dark", "светлый": "bright",
    "реалистично": "realistic", "реалистичный": "realistic",
    "аниме": "anime", "мультик": "cartoon", "рисунок": "drawing",
    "портрет": "portrait", "пейзаж": "landscape", "природа": "nature",
    "фото": "photo", "фотография": "photograph", "картина": "painting",
    "цветы": "flowers", "цветок": "flower", "дерево": "tree", "трава": "grass",
    "красный": "red", "синий": "blue", "зелёный": "green", "белый": "white",
    "чёрный": "black", "золотой": "golden", "серебряный": "silver",
    "дракон": "dragon", "единорог": "unicorn", "волк": "wolf", "лиса": "fox",
    "робот": "robot", "космос": "space", "планета": "planet", "галактика": "galaxy",
    "магия": "magic", "фэнтези": "fantasy", "будущее": "future",
    "над": "above", "под": "under", "рядом": "near", "вокруг": "around",
    "и": "and", "в": "in", "на": "on", "с": "with", "без": "without",
}

def simple_translate(text: str) -> str:
    """Простой перевод по словарю + добавляем качество"""
    words = text.lower().split()
    translated = []
    for word in words:
        clean = word.strip('.,!?')
        translated.append(RU_EN_DICT.get(clean, clean))
    result = " ".join(translated)
    # Добавляем качество если не указано
    if "4k" not in result.lower() and "quality" not in result.lower():
        result += ", high quality, detailed"
    return result

async def translate_to_english(prompt: str) -> str:
    """Перевод через MyMemory API (бесплатный, без ключа)"""
    try:
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(prompt)}&langpair=ru|en"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    translated = data.get("responseData", {}).get("translatedText", "")
                    if translated and translated != prompt:
                        logger.info(f"MyMemory translated: {prompt[:50]} -> {translated[:50]}")
                        return translated
    except Exception as e:
        logger.warning(f"MyMemory translation failed: {e}")

    # Fallback — простой словарь
    return simple_translate(prompt)

def has_cyrillic(text: str) -> bool:
    return any('\u0400' <= c <= '\u04FF' for c in text)


# ============================================================
#  ГЕНЕРАЦИЯ КАРТИНОК
# ============================================================

async def generate_image_pollinations(prompt: str) -> bytes | None:
    """Pollinations.ai — бесплатный, без ключа"""
    urls_to_try = [
        f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1024&height=1024&nologo=true&model=flux",
        f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=512&height=512&nologo=true",
    ]
    for url in urls_to_try:
        try:
            logger.info(f"Trying Pollinations: {url[:80]}")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=90),
                    headers={"User-Agent": "Mozilla/5.0"}
                ) as resp:
                    logger.info(f"Pollinations status: {resp.status}, content-type: {resp.content_type}")
                    if resp.status == 200 and "image" in resp.content_type:
                        data = await resp.read()
                        if len(data) > 1000:  # минимум 1KB — точно картинка
                            logger.info(f"Pollinations OK: {len(data)} bytes")
                            return data
                        else:
                            logger.warning(f"Pollinations returned too small data: {len(data)} bytes")
                    else:
                        body = await resp.text()
                        logger.warning(f"Pollinations bad response: {resp.status} | {body[:200]}")
        except asyncio.TimeoutError:
            logger.error("Pollinations timeout")
        except Exception as e:
            logger.error(f"Pollinations error: {type(e).__name__}: {e}")
    return None


async def generate_image_hf(prompt: str) -> bytes | None:
    """Hugging Face — нужен бесплатный токен"""
    if not HF_TOKEN:
        return None
    # Пробуем несколько быстрых моделей
    models = [
        "black-forest-labs/FLUX.1-schnell",
        "stabilityai/stable-diffusion-xl-base-1.0",
        "runwayml/stable-diffusion-v1-5",
    ]
    for model in models:
        try:
            url = f"https://api-inference.huggingface.co/models/{model}"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            payload = {"inputs": prompt}
            logger.info(f"Trying HF model: {model}")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    logger.info(f"HF {model} status: {resp.status}")
                    if resp.status == 200:
                        data = await resp.read()
                        if len(data) > 1000:
                            logger.info(f"HF OK: {len(data)} bytes from {model}")
                            return data
                    elif resp.status == 503:
                        # Модель загружается, ждём
                        logger.info(f"HF model {model} loading, waiting 20s...")
                        await asyncio.sleep(20)
                        # Повторная попытка
                        async with session.post(url, headers=headers, json=payload,
                                                timeout=aiohttp.ClientTimeout(total=120)) as resp2:
                            if resp2.status == 200:
                                data = await resp2.read()
                                if len(data) > 1000:
                                    return data
                    else:
                        text = await resp.text()
                        logger.warning(f"HF {model}: {resp.status} | {text[:200]}")
        except Exception as e:
            logger.error(f"HF {model} error: {type(e).__name__}: {e}")
    return None


async def generate_image(prompt: str) -> bytes | None:
    """Главная функция генерации картинки"""
    logger.info(f"generate_image called with prompt: {prompt[:80]}")

    # 1. Hugging Face (если есть токен — приоритет)
    if HF_TOKEN:
        logger.info("Trying HuggingFace...")
        result = await generate_image_hf(prompt)
        if result:
            return result
        logger.warning("HuggingFace failed, falling back to Pollinations")

    # 2. Pollinations (всегда как fallback)
    logger.info("Trying Pollinations...")
    result = await generate_image_pollinations(prompt)
    if result:
        return result

    logger.error("ALL image generation methods failed!")
    return None


# ============================================================
#  ГЕНЕРАЦИЯ ВИДЕО
# ============================================================

async def generate_video_replicate(prompt: str, duration: int = 5) -> bytes | None:
    """Replicate — нужен токен (дают $5 бонус при регистрации)"""
    if not REPLICATE_TOKEN:
        logger.warning("No REPLICATE_TOKEN set")
        return None
    try:
        headers = {
            "Authorization": f"Token {REPLICATE_TOKEN}",
            "Content-Type": "application/json",
            "Prefer": "wait"
        }
        # minimax/video-01-live — хорошее качество
        payload = {
            "version": "minimax/video-01-live",
            "input": {
                "prompt": prompt,
                "duration": duration,
            }
        }
        logger.info(f"Starting Replicate video generation...")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.replicate.com/v1/models/minimax/video-01-live/predictions",
                headers=headers, json={"input": {"prompt": prompt}},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                logger.info(f"Replicate start status: {resp.status}")
                if resp.status not in (200, 201):
                    text = await resp.text()
                    logger.error(f"Replicate start failed: {resp.status} | {text[:300]}")
                    return None
                prediction = await resp.json()
                prediction_id = prediction["id"]
                logger.info(f"Replicate prediction ID: {prediction_id}")

            # Поллинг результата (до 4 минут)
            for i in range(48):
                await asyncio.sleep(5)
                async with session.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers=headers
                ) as resp:
                    data = await resp.json()
                    status = data.get("status")
                    logger.info(f"Replicate poll {i+1}: {status}")
                    if status == "succeeded":
                        output = data.get("output")
                        video_url = output[0] if isinstance(output, list) else output
                        logger.info(f"Replicate succeeded, downloading: {video_url}")
                        async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=60)) as vresp:
                            if vresp.status == 200:
                                return await vresp.read()
                    elif status == "failed":
                        logger.error(f"Replicate failed: {data.get('error')}")
                        return None
    except Exception as e:
        logger.error(f"Replicate error: {type(e).__name__}: {e}")
    return None


async def generate_video_stability(prompt: str, duration: int = 5) -> bytes | None:
    """Stability AI video — нужен токен"""
    if not STABILITY_KEY:
        return None
    try:
        img_data = await generate_image_pollinations(prompt)
        if not img_data:
            logger.error("Stability video: can't get start frame")
            return None

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
                    logger.warning(f"Stability video init: {resp.status}")
                    return None
                result = await resp.json()
                gen_id = result.get("id")
                if not gen_id:
                    return None

            for _ in range(30):
                await asyncio.sleep(10)
                async with session.get(
                    f"https://api.stability.ai/v2beta/image-to-video/result/{gen_id}",
                    headers={"Authorization": f"Bearer {STABILITY_KEY}", "Accept": "video/*"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    elif resp.status != 202:
                        return None
    except Exception as e:
        logger.error(f"Stability video error: {e}")
    return None


async def generate_video(prompt: str, duration: int = 5) -> bytes | None:
    """Главная функция генерации видео"""
    logger.info(f"generate_video called: prompt={prompt[:60]}, duration={duration}")

    if REPLICATE_TOKEN:
        result = await generate_video_replicate(prompt, duration)
        if result:
            return result
        logger.warning("Replicate failed, trying Stability...")

    if STABILITY_KEY:
        result = await generate_video_stability(prompt, duration)
        if result:
            return result

    logger.error("ALL video generation methods failed!")
    return None
