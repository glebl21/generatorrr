import os
import logging
from config import FREE_IMAGES, FREE_VIDEOS

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    def get_connection():
        return psycopg2.connect(DATABASE_URL)
else:
    import sqlite3
    from config import DB_PATH
    def get_connection():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


def _q(sql):
    """Конвертирует ? в %s для PostgreSQL"""
    if USE_POSTGRES:
        return sql.replace("?", "%s")
    return sql


def fetchone(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    if USE_POSTGRES:
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))
    return dict(row)


def fetchall(cursor):
    rows = cursor.fetchall()
    if USE_POSTGRES:
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in rows]
    return [dict(row) for row in rows]


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    if USE_POSTGRES:
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT, full_name TEXT,
                balance INTEGER DEFAULT 0,
                free_images INTEGER DEFAULT {FREE_IMAGES},
                free_videos INTEGER DEFAULT {FREE_VIDEOS},
                total_images INTEGER DEFAULT 0,
                total_videos INTEGER DEFAULT 0,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_banned INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT, amount INTEGER, type TEXT,
                status TEXT DEFAULT 'pending', comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id SERIAL PRIMARY KEY,
                user_id BIGINT, type TEXT, prompt TEXT,
                status TEXT DEFAULT 'success', cost INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT, full_name TEXT,
                balance INTEGER DEFAULT 0,
                free_images INTEGER DEFAULT {FREE_IMAGES},
                free_videos INTEGER DEFAULT {FREE_VIDEOS},
                total_images INTEGER DEFAULT 0,
                total_videos INTEGER DEFAULT 0,
                registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_banned INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, amount INTEGER, type TEXT,
                status TEXT DEFAULT 'pending', comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, type TEXT, prompt TEXT,
                status TEXT DEFAULT 'success', cost INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()
    conn.close()
    logger.info(f"Database initialized ({'PostgreSQL' if USE_POSTGRES else 'SQLite'})")


def get_user(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(_q("SELECT * FROM users WHERE user_id = ?"), (user_id,))
    row = fetchone(cursor)
    conn.close()
    return row


def create_user(user_id: int, username: str, full_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if USE_POSTGRES:
            cursor.execute(
                "INSERT INTO users (user_id, username, full_name) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
                (user_id, username, full_name)
            )
        else:
            cursor.execute(
                "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
                (user_id, username, full_name)
            )
        conn.commit()
    except Exception as e:
        logger.error(f"create_user error: {e}")
    finally:
        conn.close()


def get_all_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY registered_at DESC")
    rows = fetchall(cursor)
    conn.close()
    return rows


def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(total_images),0) FROM users")
    total_images = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(total_videos),0) FROM users")
    total_videos = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE status='confirmed' AND type='topup'")
    total_income = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE status='pending' AND type='topup'")
    pending = cursor.fetchone()[0]
    conn.close()
    return {"total_users": total_users, "total_images": total_images,
            "total_videos": total_videos, "total_income": total_income,
            "pending_payments": pending}


def add_balance(user_id: int, amount: int, comment: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(_q("UPDATE users SET balance = balance + ? WHERE user_id = ?"), (amount, user_id))
        cursor.execute(
            _q("INSERT INTO transactions (user_id, amount, type, status, comment, confirmed_at) VALUES (?, ?, 'topup', 'confirmed', ?, CURRENT_TIMESTAMP)"),
            (user_id, amount, comment)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"add_balance error: {e}")
        return False
    finally:
        conn.close()


def create_payment_request(user_id: int, amount: int):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if USE_POSTGRES:
            cursor.execute(
                "INSERT INTO transactions (user_id, amount, type, status) VALUES (%s, %s, 'topup', 'pending') RETURNING id",
                (user_id, amount)
            )
            payment_id = cursor.fetchone()[0]
        else:
            cursor.execute(
                "INSERT INTO transactions (user_id, amount, type, status) VALUES (?, ?, 'topup', 'pending')",
                (user_id, amount)
            )
            payment_id = cursor.lastrowid
        conn.commit()
        return payment_id
    finally:
        conn.close()


def get_payment(payment_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(_q("SELECT * FROM transactions WHERE id = ?"), (payment_id,))
    row = fetchone(cursor)
    conn.close()
    return row


def confirm_payment(payment_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(_q("SELECT * FROM transactions WHERE id = ?"), (payment_id,))
        payment = fetchone(cursor)
        if not payment or payment["status"] != "pending":
            return None
        cursor.execute(
            _q("UPDATE transactions SET status='confirmed', confirmed_at=CURRENT_TIMESTAMP WHERE id=?"),
            (payment_id,)
        )
        cursor.execute(
            _q("UPDATE users SET balance = balance + ? WHERE user_id = ?"),
            (payment["amount"], payment["user_id"])
        )
        conn.commit()
        return payment
    finally:
        conn.close()


def reject_payment(payment_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(_q("UPDATE transactions SET status='rejected' WHERE id=?"), (payment_id,))
        conn.commit()
    finally:
        conn.close()


def get_pending_payments():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.user_id, t.amount, t.status, t.created_at,
               u.username, u.full_name
        FROM transactions t
        JOIN users u ON t.user_id = u.user_id
        WHERE t.status = 'pending' AND t.type = 'topup'
        ORDER BY t.created_at ASC
    """)
    rows = fetchall(cursor)
    conn.close()
    return rows


def log_generation(user_id: int, gen_type: str, prompt: str, cost: int, status: str = "success"):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            _q("INSERT INTO generations (user_id, type, prompt, status, cost) VALUES (?, ?, ?, ?, ?)"),
            (user_id, gen_type, prompt, status, cost)
        )
        if gen_type in ("image", "img2img"):
            cursor.execute(_q("UPDATE users SET total_images = total_images + 1 WHERE user_id = ?"), (user_id,))
        else:
            cursor.execute(_q("UPDATE users SET total_videos = total_videos + 1 WHERE user_id = ?"), (user_id,))
        conn.commit()
    finally:
        conn.close()


def deduct_balance(user_id: int, amount: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(_q("SELECT balance FROM users WHERE user_id = ?"), (user_id,))
        row = cursor.fetchone()
        bal = row[0] if row else 0
        if bal < amount:
            return False
        cursor.execute(_q("UPDATE users SET balance = balance - ? WHERE user_id = ?"), (amount, user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def use_free_image(user_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(_q("SELECT free_images FROM users WHERE user_id = ?"), (user_id,))
        row = cursor.fetchone()
        if not row or row[0] <= 0:
            return False
        cursor.execute(_q("UPDATE users SET free_images = free_images - 1 WHERE user_id = ?"), (user_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def use_free_video(user_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(_q("SELECT free_videos FROM users WHERE user_id = ?"), (user_id,))
        row = cursor.fetchone()
        if not row or row[0] <= 0:
            return False
        cursor.execute(_q("UPDATE users SET free_videos = free_videos - 1 WHERE user_id = ?"), (user_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def update_user(user_id: int, **kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for key, value in kwargs.items():
            cursor.execute(_q(f"UPDATE users SET {key} = ? WHERE user_id = ?"), (value, user_id))
        conn.commit()
    finally:
        conn.close()
