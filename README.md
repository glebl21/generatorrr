# 🤖 AI Generator Bot

Telegram бот для продажи AI-генерации изображений и видео. Деплой на **Railway.app**.

## 💰 Монетизация
| Тип | Цена |
|-----|------|
| 🖼 Картинка | 10₽ |
| 🎬 Видео 5 сек | 30₽ |
| 🎬 Видео 10 сек | 60₽ |

🎁 Новичкам: 3 бесплатных картинки + 1 видео

---

## 🚀 Деплой на Railway (пошагово)

### Шаг 1 — Подготовка

1. Создайте бота у @BotFather в Telegram → /newbot
2. Скопируйте токен вида 123456:ABC-DEF...
3. Узнайте ваш Telegram ID у @userinfobot

### Шаг 2 — GitHub

Railway разворачивает бота прямо из GitHub.

1. Зайдите на github.com → New repository
2. Назовите ai-generator-bot, сделайте Private
3. Нажмите "uploading an existing file"
4. Перетащите ВСЕ файлы из папки tg-bot/
5. Commit changes

### Шаг 3 — Railway

1. Зайдите на railway.app → Login with GitHub
2. New Project → Deploy from GitHub repo
3. Выберите репозиторий ai-generator-bot
4. Railway найдёт Procfile и начнёт сборку автоматически

### Шаг 4 — Переменные окружения (Variables)

Откройте проект в Railway → вкладка Variables → добавьте:

| Переменная       | Значение              | Обязательно |
|------------------|-----------------------|-------------|
| BOT_TOKEN        | 123456:ABC-DEF...     | ✅ Да       |
| ADMIN_IDS        | 123456789             | ✅ Да       |
| PAYMENT_CARD     | 2200 1234 5678 9000   | ✅ Да       |
| PAYMENT_PHONE    | +7 999 123 45 67      | Рекоменд.   |
| HF_TOKEN         | hf_xxxxx              | Для картинок|
| REPLICATE_TOKEN  | r8_xxxxx              | Для видео   |
| STABILITY_KEY    | sk-xxxxx              | Резерв видео|

После добавления переменных Railway перезапустит бота автоматически.

### Шаг 5 — Проверка

Railway → вкладка Logs — должно появиться:
  INFO - Bot started!

Напишите боту /start — если ответил, всё работает!

---

## 🎨 Бесплатные API

### Картинки

Pollinations.ai — работает СРАЗУ, без токена и регистрации.

Hugging Face (лучшее качество, FLUX модель):
1. Зарегистрируйтесь на huggingface.co
2. Settings → Access Tokens → New Token (тип: Read)
3. Добавьте в Railway: HF_TOKEN = hf_...

### Видео

Replicate (рекомендуется, при регистрации дают $5 = ~150 видео):
1. Зарегистрируйтесь на replicate.com
2. Аватар → API Tokens → Create token
3. Добавьте в Railway: REPLICATE_TOKEN = r8_...

Stability AI (резерв):
1. Зарегистрируйтесь на platform.stability.ai
2. API Keys → Create Key
3. Добавьте: STABILITY_KEY = sk-...

---

## 👨‍💼 Управление

### Команды администратора
- /admin — панель: статистика, платежи, рассылка
- /addbalance 123456789 100 — зачислить 100₽ пользователю

### Как подтверждать оплаты
1. Пользователь нажал «Я оплатил» → вам в Telegram приходит уведомление
2. Проверяете перевод в банке
3. Нажимаете ✅ Подтвердить — деньги зачисляются автоматически

---

## ⚠️ База данных на Railway

Railway — эфемерная файловая система. При редеплое bot_database.db сбрасывается.

Для надёжности добавьте PostgreSQL:
Railway → New → Database → PostgreSQL (бесплатно до 1GB)

На старте с малым количеством пользователей SQLite вполне подойдёт.

---

## 📁 Структура

    tg-bot/
    ├── bot.py              # Точка входа
    ├── config.py           # Настройки из env
    ├── Procfile            # Команда запуска для Railway
    ├── railway.toml        # Конфиг Railway
    ├── runtime.txt         # Python 3.11
    ├── requirements.txt    # aiogram, aiohttp
    ├── handlers/
    │   ├── start.py        # /start, баланс, помощь
    │   ├── generate.py     # Генерация картинок и видео
    │   ├── payment.py      # Пополнение баланса
    │   └── admin.py        # Панель администратора
    ├── services/
    │   └── generator.py    # Работа с API генерации
    ├── database/
    │   └── db.py           # SQLite
    └── utils/
        └── keyboards.py    # Клавиатуры
