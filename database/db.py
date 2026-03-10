import sqlite3
import logging
from datetime import datetime
from config import DB_PATH, FREE_IMAGES, FREE_VIDEOS

logger = logging.getLogger(__name__)

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация базы данных"""
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance INTEGER DEFAULT 0,
            free_images INTEGER DEFAULT ?,
            free_videos INTEGER DEFAULT ?,
            total_images INTEGER DEFAULT 0,
            total_videos INTEGER DEFAULT 0,
            registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_banned INTEGER DEFAULT 0
        )
    """, (FREE_IMAGES, FREE_VIDEOS))

    # Таблица транзакций
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            type TEXT,
            status TEXT DEFAULT 'pending',
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # Таблица генераций
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            prompt TEXT,
            status TEXT DEFAULT 'pending',
            cost INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized")

# ============================
#  ФУНКЦИИ ПОЛЬЗОВАТЕЛЕЙ
# ============================

def get_user(user_id: int):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return user

def create_user(user_id: int, username: str, full_name: str):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
        """, (user_id, username, full_name))
        conn.commit()
    except Exception as e:
        logger.error(f"Error creating user: {e}")
    finally:
        conn.close()

def update_user(user_id: int, **kwargs):
    conn = get_connection()
    try:
        for key, value in kwargs.items():
            conn.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
        conn.commit()
    finally:
        conn.close()

def get_all_users():
    conn = get_connection()
    users = conn.execute("SELECT * FROM users ORDER BY registered_at DESC").fetchall()
    conn.close()
    return users

def get_stats():
    conn = get_connection()
    stats = {
        "total_users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "total_images": conn.execute("SELECT SUM(total_images) FROM users").fetchone()[0] or 0,
        "total_videos": conn.execute("SELECT SUM(total_videos) FROM users").fetchone()[0] or 0,
        "total_income": conn.execute(
            "SELECT SUM(amount) FROM transactions WHERE status = 'confirmed' AND type = 'topup'"
        ).fetchone()[0] or 0,
        "pending_payments": conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE status = 'pending' AND type = 'topup'"
        ).fetchone()[0],
    }
    conn.close()
    return stats

# ============================
#  ФУНКЦИИ БАЛАНСА
# ============================

def add_balance(user_id: int, amount: int, comment: str = ""):
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.execute("""
            INSERT INTO transactions (user_id, amount, type, status, comment, confirmed_at)
            VALUES (?, ?, 'topup', 'confirmed', ?, CURRENT_TIMESTAMP)
        """, (user_id, amount, comment))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding balance: {e}")
        return False
    finally:
        conn.close()

def create_payment_request(user_id: int, amount: int):
    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO transactions (user_id, amount, type, status)
            VALUES (?, ?, 'topup', 'pending')
        """, (user_id, amount))
        payment_id = cursor.lastrowid
        conn.commit()
        return payment_id
    finally:
        conn.close()

def confirm_payment(payment_id: int):
    conn = get_connection()
    try:
        payment = conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (payment_id,)
        ).fetchone()
        if not payment or payment["status"] != "pending":
            return None
        conn.execute("""
            UPDATE transactions SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (payment_id,))
        conn.execute("""
            UPDATE users SET balance = balance + ? WHERE user_id = ?
        """, (payment["amount"], payment["user_id"]))
        conn.commit()
        return payment
    finally:
        conn.close()

def get_pending_payments():
    conn = get_connection()
    payments = conn.execute("""
        SELECT t.*, u.username, u.full_name 
        FROM transactions t
        JOIN users u ON t.user_id = u.user_id
        WHERE t.status = 'pending' AND t.type = 'topup'
        ORDER BY t.created_at ASC
    """).fetchall()
    conn.close()
    return payments

# ============================
#  ФУНКЦИИ ГЕНЕРАЦИИ
# ============================

def log_generation(user_id: int, gen_type: str, prompt: str, cost: int, status: str = "success"):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO generations (user_id, type, prompt, status, cost)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, gen_type, prompt, status, cost))
        if gen_type == "image":
            conn.execute("UPDATE users SET total_images = total_images + 1 WHERE user_id = ?", (user_id,))
        else:
            conn.execute("UPDATE users SET total_videos = total_videos + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()

def deduct_balance(user_id: int, amount: int) -> bool:
    conn = get_connection()
    try:
        user = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user or user["balance"] < amount:
            return False
        conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        return True
    finally:
        conn.close()

def use_free_image(user_id: int) -> bool:
    conn = get_connection()
    try:
        user = conn.execute("SELECT free_images FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user or user["free_images"] <= 0:
            return False
        conn.execute("UPDATE users SET free_images = free_images - 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    finally:
        conn.close()

def use_free_video(user_id: int) -> bool:
    conn = get_connection()
    try:
        user = conn.execute("SELECT free_videos FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user or user["free_videos"] <= 0:
            return False
        conn.execute("UPDATE users SET free_videos = free_videos - 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    finally:
        conn.close()
