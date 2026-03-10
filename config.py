import os

# ========================
#  НАСТРОЙКИ БОТА
# ========================
# Все переменные читаются из окружения Railway (Variables)

BOT_TOKEN = os.environ["BOT_TOKEN"]  # ОБЯЗАТЕЛЬНО: задать в Railway Variables

# ID администратора (ваш Telegram ID, узнать у @userinfobot)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",")]

# ========================
#  ЦЕНЫ (в рублях)
# ========================
PRICE_IMAGE = int(os.getenv("PRICE_IMAGE", "10"))
PRICE_VIDEO_SHORT = int(os.getenv("PRICE_VIDEO_SHORT", "30"))
PRICE_VIDEO_LONG = int(os.getenv("PRICE_VIDEO_LONG", "60"))

# ========================
#  БЕСПЛАТНЫЕ ЛИМИТЫ
# ========================
FREE_IMAGES = int(os.getenv("FREE_IMAGES", "3"))
FREE_VIDEOS = int(os.getenv("FREE_VIDEOS", "1"))

# ========================
#  ПЛАТЁЖНЫЕ РЕКВИЗИТЫ
# ========================
PAYMENT_CARD = os.getenv("PAYMENT_CARD", "")   # Номер карты
PAYMENT_PHONE = os.getenv("PAYMENT_PHONE", "")  # Телефон СБП
PAYMENT_QIWI = os.getenv("PAYMENT_QIWI", "")    # QIWI (необязательно)

# ========================
#  API ДЛЯ ГЕНЕРАЦИИ
# ========================

# Pollinations.ai — БЕСПЛАТНЫЙ, без ключа (работает всегда)
POLLINATIONS_IMAGE_URL = "https://image.pollinations.ai/prompt/{prompt}?width={width}&height={height}&nologo=true&enhance=true"

# Hugging Face — БЕСПЛАТНЫЙ (нужен токен с huggingface.co)
HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"

# Stability AI — бесплатные кредиты при регистрации
STABILITY_KEY = os.getenv("STABILITY_KEY", "")

# Replicate — бесплатный tier (нужен токен с replicate.com)
REPLICATE_TOKEN = os.getenv("REPLICATE_TOKEN", "")

# ========================
#  БАЗА ДАННЫХ
# ========================
# Railway даёт /app как рабочую папку, база хранится там
DB_PATH = os.getenv("DB_PATH", "bot_database.db")

# ========================
#  НАСТРОЙКИ ГЕНЕРАЦИИ
# ========================
IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 1024
VIDEO_DURATION_SHORT = 5
VIDEO_DURATION_LONG = 10
