import aiohttp
import asyncio
import logging
import urllib.parse
from config import HF_TOKEN, STABILITY_KEY, REPLICATE_TOKEN

logger = logging.getLogger(__name__)


# ============================================================
#  ПЕРЕВОД
# ============================================================

async def translate_to_english(prompt: str) -> str:
    try:
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(prompt)}&langpair=ru|en"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    translated = data.get("responseData", {}).get("translatedText", "")
                    if translated and translated.upper() != prompt.upper():
                        logger.info(f"MyMemory translated: {prompt} -> {translated}")
                        return translated
    except Exception as e:
        logger.warning(f"Translation failed: {e}")
    return prompt

def has_cyrillic(text: str) -> bool:
    return any('\u0400' <= c <= '\u04FF' for c in text)


# ============================================================
#  ГЕНЕРАЦИЯ КАРТИНОК
# ============================================================

async def generate_image_hf(prompt: str) -> bytes | None:
    """HuggingFace Router API (новый endpoint с 2025)"""
    if not HF_TOKEN:
        return None
    models = [
        "black-forest-labs/FLUX.1-schnell",
        "stabilityai/stable-diffusion-xl-base-1.0",
    ]
    for model in models:
        try:
            # Новый URL: router.huggingface.co
            url = f"https://router.huggingface.co/hf-inference/models/{model}"
            headers = {
                "Authorization": f"Bearer {HF_TOKEN}",
                "Content-Type": "application/json",
            }
            logger.info(f"HF Router: {model}")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers,
                    json={"inputs": prompt},
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    logger.info(f"HF {model}: status={resp.status}")
                    if resp.status == 200:
                        data = await resp.read()
                        if len(data) > 1000:
                            logger.info(f"HF OK: {len(data)} bytes")
                            return data
                    elif resp.status == 503:
                        logger.info("HF model loading, waiting 20s...")
                        await asyncio.sleep(20)
                        async with session.post(url, headers=headers,
                                                json={"inputs": prompt},
                                                timeout=aiohttp.ClientTimeout(total=120)) as r2:
                            if r2.status == 200:
                                data = await r2.read()
                                if len(data) > 1000:
                                    return data
                    else:
                        text = await resp.text()
                        logger.warning(f"HF {model}: {resp.status} | {text[:200]}")
        except Exception as e:
            logger.error(f"HF {model} error: {e}")
    return None


async def generate_image_together(prompt: str) -> bytes | None:
    """
    Together.ai — бесплатный tier $25 при регистрации.
    Переменная: TOGETHER_TOKEN
    """
    import os
    token = os.getenv("TOGETHER_TOKEN", "")
    if not token:
        return None
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "black-forest-labs/FLUX.1-schnell-Free",
            "prompt": prompt,
            "width": 1024,
            "height": 1024,
            "steps": 4,
            "n": 1,
            "response_format": "b64_json",
        }
        logger.info("Together.ai: generating image")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.together.xyz/v1/images/generations",
                headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                logger.info(f"Together: status={resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    b64 = data["data"][0].get("b64_json", "")
                    if b64:
                        import base64
                        img_bytes = base64.b64decode(b64)
                        logger.info(f"Together OK: {len(img_bytes)} bytes")
                        return img_bytes
                else:
                    text = await resp.text()
                    logger.warning(f"Together: {resp.status} | {text[:200]}")
    except Exception as e:
        logger.error(f"Together error: {e}")
    return None


async def generate_image_getimg(prompt: str) -> bytes | None:
    """
    GetImg.ai — 100 бесплатных генераций в месяц.
    Переменная: GETIMG_TOKEN
    """
    import os
    token = os.getenv("GETIMG_TOKEN", "")
    if not token:
        return None
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "flux-schnell",
            "prompt": prompt,
            "width": 1024,
            "height": 1024,
            "steps": 4,
            "output_format": "jpeg",
            "response_format": "b64",
        }
        logger.info("GetImg.ai: generating")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.getimg.ai/v1/flux-schnell/text-to-image",
                headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                logger.info(f"GetImg: status={resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    b64 = data.get("image", "")
                    if b64:
                        import base64
                        img_bytes = base64.b64decode(b64)
                        logger.info(f"GetImg OK: {len(img_bytes)} bytes")
                        return img_bytes
                else:
                    text = await resp.text()
                    logger.warning(f"GetImg: {resp.status} | {text[:200]}")
    except Exception as e:
        logger.error(f"GetImg error: {e}")
    return None


async def generate_image(prompt: str) -> bytes | None:
    logger.info(f"generate_image: '{prompt[:80]}'")

    # 1. HuggingFace Router (нужен токен)
    if HF_TOKEN:
        logger.info("Trying HuggingFace Router...")
        result = await generate_image_hf(prompt)
        if result:
            return result

    # 2. Together.ai (нужен токен, $25 бонус)
    import os
    if os.getenv("TOGETHER_TOKEN"):
        logger.info("Trying Together.ai...")
        result = await generate_image_together(prompt)
        if result:
            return result

    # 3. GetImg.ai (нужен токен, 100 бесплатных/месяц)
    if os.getenv("GETIMG_TOKEN"):
        logger.info("Trying GetImg.ai...")
        result = await generate_image_getimg(prompt)
        if result:
            return result

    logger.error("ALL image methods failed. Add HF_TOKEN, TOGETHER_TOKEN or GETIMG_TOKEN in Railway Variables.")
    return None


# ============================================================
#  ГЕНЕРАЦИЯ ВИДЕО
# ============================================================

async def generate_video_replicate(prompt: str, duration: int = 5) -> bytes | None:
    if not REPLICATE_TOKEN:
        logger.warning("No REPLICATE_TOKEN")
        return None
    try:
        headers = {
            "Authorization": f"Token {REPLICATE_TOKEN}",
            "Content-Type": "application/json",
        }
        logger.info("Replicate: starting video")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.replicate.com/v1/models/minimax/video-01-live/predictions",
                headers=headers,
                json={"input": {"prompt": prompt}},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                logger.info(f"Replicate start: {resp.status}")
                if resp.status not in (200, 201):
                    text = await resp.text()
                    logger.error(f"Replicate failed: {text[:300]}")
                    return None
                prediction = await resp.json()
                prediction_id = prediction["id"]

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
                        async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=120)) as vr:
                            if vr.status == 200:
                                return await vr.read()
                    elif status == "failed":
                        logger.error(f"Replicate failed: {data.get('error')}")
                        return None
    except Exception as e:
        logger.error(f"Replicate error: {e}")
    return None


async def generate_video(prompt: str, duration: int = 5) -> bytes | None:
    logger.info(f"generate_video: '{prompt[:60]}'")

    if REPLICATE_TOKEN:
        result = await generate_video_replicate(prompt, duration)
        if result:
            return result

    logger.error("No video API available. Add REPLICATE_TOKEN in Railway Variables.")
    return None


# ============================================================
#  IMG2IMG — фото + промпт
# ============================================================

async def generate_image_img2img(image_bytes: bytes, prompt: str) -> bytes | None:
    """
    Изменение фото по описанию через Together.ai или Replicate.
    """
    import os, base64
    token = os.getenv("TOGETHER_TOKEN", "")

    # 1. Together.ai img2img
    if token:
        try:
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "black-forest-labs/FLUX.1-depth",
                "prompt": prompt,
                "image": f"data:image/jpeg;base64,{b64_image}",
                "width": 1024,
                "height": 1024,
                "steps": 8,
                "n": 1,
                "response_format": "b64_json",
            }
            logger.info("Together img2img: generating")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.together.xyz/v1/images/generations",
                    headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=90)
                ) as resp:
                    logger.info(f"Together img2img: {resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        b64 = data["data"][0].get("b64_json", "")
                        if b64:
                            return base64.b64decode(b64)
                    else:
                        text = await resp.text()
                        logger.warning(f"Together img2img: {resp.status} | {text[:200]}")
        except Exception as e:
            logger.error(f"Together img2img error: {e}")

    # 2. Replicate img2img fallback
    if REPLICATE_TOKEN:
        try:
            import base64
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            headers = {
                "Authorization": f"Token {REPLICATE_TOKEN}",
                "Content-Type": "application/json",
            }
            payload = {
                "input": {
                    "prompt": prompt,
                    "image": f"data:image/jpeg;base64,{b64_image}",
                    "prompt_strength": 0.8,
                }
            }
            logger.info("Replicate img2img: generating")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.replicate.com/v1/models/black-forest-labs/flux-dev/predictions",
                    headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status not in (200, 201):
                        return None
                    prediction = await resp.json()
                    prediction_id = prediction["id"]

                for i in range(30):
                    await asyncio.sleep(4)
                    async with session.get(
                        f"https://api.replicate.com/v1/predictions/{prediction_id}",
                        headers=headers
                    ) as resp:
                        data = await resp.json()
                        if data["status"] == "succeeded":
                            output = data.get("output")
                            url = output[0] if isinstance(output, list) else output
                            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as ir:
                                if ir.status == 200:
                                    return await ir.read()
                        elif data["status"] == "failed":
                            return None
        except Exception as e:
            logger.error(f"Replicate img2img error: {e}")

    logger.error("img2img: all methods failed. Need TOGETHER_TOKEN or REPLICATE_TOKEN")
    return None
