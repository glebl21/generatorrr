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
    """Hugging Face — бесплатный токен с huggingface.co"""
    if not HF_TOKEN:
        return None
    models = [
        "black-forest-labs/FLUX.1-schnell",
        "stabilityai/stable-diffusion-xl-base-1.0",
        "runwayml/stable-diffusion-v1-5",
    ]
    for model in models:
        try:
            url = f"https://api-inference.huggingface.co/models/{model}"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            logger.info(f"Trying HF: {model}")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json={"inputs": prompt},
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    logger.info(f"HF {model}: status={resp.status}")
                    if resp.status == 200:
                        data = await resp.read()
                        if len(data) > 1000:
                            logger.info(f"HF OK: {len(data)} bytes")
                            return data
                    elif resp.status == 503:
                        logger.info(f"HF model loading, wait 15s...")
                        await asyncio.sleep(15)
                        async with session.post(url, headers=headers, json={"inputs": prompt},
                                                timeout=aiohttp.ClientTimeout(total=120)) as r2:
                            if r2.status == 200:
                                data = await r2.read()
                                if len(data) > 1000:
                                    return data
                    else:
                        text = await resp.text()
                        logger.warning(f"HF {model}: {resp.status} | {text[:150]}")
        except Exception as e:
            logger.error(f"HF {model} error: {e}")
    return None


async def generate_image_prodia(prompt: str) -> bytes | None:
    """
    Prodia.com — бесплатный Stable Diffusion API, без ключа.
    """
    try:
        # Шаг 1: создаём задачу
        params = {
            "model": "sd_xl_base_1.0.safetensors [be9edd61]",
            "prompt": prompt,
            "negative_prompt": "ugly, blurry, low quality, watermark",
            "steps": 20,
            "cfg_scale": 7,
            "width": 1024,
            "height": 1024,
            "sampler": "DPM++ 2M Karras",
        }
        headers = {"accept": "application/json"}
        logger.info(f"Prodia: starting job for prompt: {prompt[:60]}")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.prodia.com/v1/sd/generate",
                params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                logger.info(f"Prodia generate: {resp.status}")
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Prodia generate failed: {text[:200]}")
                    return None
                job = await resp.json()
                job_id = job.get("job")
                if not job_id:
                    logger.error(f"Prodia: no job id in response: {job}")
                    return None
                logger.info(f"Prodia job_id: {job_id}")

            # Шаг 2: ждём результата
            for i in range(30):
                await asyncio.sleep(4)
                async with session.get(
                    f"https://api.prodia.com/v1/job/{job_id}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    data = await resp.json()
                    status = data.get("status")
                    logger.info(f"Prodia poll {i+1}: {status}")
                    if status == "succeeded":
                        img_url = data.get("imageUrl")
                        logger.info(f"Prodia succeeded, downloading: {img_url}")
                        async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=30)) as img_resp:
                            if img_resp.status == 200:
                                img_data = await img_resp.read()
                                logger.info(f"Prodia image: {len(img_data)} bytes")
                                return img_data
                    elif status == "failed":
                        logger.error("Prodia job failed")
                        return None
    except Exception as e:
        logger.error(f"Prodia error: {type(e).__name__}: {e}")
    return None


async def generate_image_pollinations(prompt: str) -> bytes | None:
    """Pollinations fallback"""
    try:
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=512&height=512&nologo=true&seed={hash(prompt) % 99999}"
        logger.info(f"Pollinations: {url[:80]}")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=90),
                headers={"User-Agent": "Mozilla/5.0"}
            ) as resp:
                logger.info(f"Pollinations: status={resp.status} content-type={resp.content_type}")
                if resp.status == 200 and "image" in resp.content_type:
                    data = await resp.read()
                    if len(data) > 1000:
                        return data
    except Exception as e:
        logger.error(f"Pollinations error: {e}")
    return None


async def generate_image(prompt: str) -> bytes | None:
    logger.info(f"generate_image: '{prompt[:80]}'")

    # 1. HuggingFace (лучшее качество, нужен токен)
    if HF_TOKEN:
        logger.info("Trying HuggingFace...")
        result = await generate_image_hf(prompt)
        if result:
            return result

    # 2. Prodia (бесплатно, без ключа)
    logger.info("Trying Prodia...")
    result = await generate_image_prodia(prompt)
    if result:
        return result

    # 3. Pollinations (последний fallback)
    logger.info("Trying Pollinations...")
    result = await generate_image_pollinations(prompt)
    if result:
        return result

    logger.error("ALL methods failed")
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
        logger.info("Replicate: starting video generation")
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
                    logger.error(f"Replicate start failed: {text[:300]}")
                    return None
                prediction = await resp.json()
                prediction_id = prediction["id"]
                logger.info(f"Replicate prediction: {prediction_id}")

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


async def generate_video_stability(prompt: str, duration: int = 5) -> bytes | None:
    if not STABILITY_KEY:
        return None
    try:
        img_data = await generate_image_prodia(prompt)
        if not img_data:
            img_data = await generate_image_pollinations(prompt)
        if not img_data:
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
                    return None
                gen_id = (await resp.json()).get("id")
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
        logger.error(f"Stability error: {e}")
    return None


async def generate_video(prompt: str, duration: int = 5) -> bytes | None:
    logger.info(f"generate_video: '{prompt[:60]}', duration={duration}")

    if REPLICATE_TOKEN:
        result = await generate_video_replicate(prompt, duration)
        if result:
            return result

    if STABILITY_KEY:
        result = await generate_video_stability(prompt, duration)
        if result:
            return result

    logger.error("ALL video methods failed")
    return None
