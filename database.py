import sqlite3
import os
import secrets
import string
import bcrypt
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "novel_reader.db")


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS reading_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            site TEXT NOT NULL,
            novel_id TEXT NOT NULL,
            novel_title TEXT NOT NULL,
            chapter_url TEXT NOT NULL,
            chapter_title TEXT DEFAULT '',
            page INTEGER DEFAULT 1,
            total_pages INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, site, novel_id)
        );
    """)
    conn.commit()

    cur = conn.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        password = generate_password()
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                     ("admin", pw_hash))
        conn.commit()
        print("=" * 50)
        print(f"  首次启动，已创建管理员账号")
        print(f"  用户名: admin")
        print(f"  密码: {password}")
        print("=" * 50)
        with open(os.path.join(os.path.dirname(__file__), "data", "admin_credentials.txt"), "w") as f:
            f.write(f"username: admin\npassword: {password}\n")
    conn.close()


def generate_password(length=20):
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(chars) for _ in range(length))


def verify_login(username, password):
    conn = get_db()
    cur = conn.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return row["id"]
    return None


def get_history(user_id, limit=30):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM reading_history WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_history(user_id, site, novel_id, novel_title, chapter_url, chapter_title, page, total_pages):
    conn = get_db()
    conn.execute("""
        INSERT INTO reading_history (user_id, site, novel_id, novel_title, chapter_url, chapter_title, page, total_pages, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, site, novel_id)
        DO UPDATE SET
            chapter_url = excluded.chapter_url,
            chapter_title = excluded.chapter_title,
            page = excluded.page,
            total_pages = excluded.total_pages,
            updated_at = excluded.updated_at
    """, (user_id, site, novel_id, novel_title, chapter_url, chapter_title, page, total_pages, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def delete_history(history_id, user_id):
    conn = get_db()
    conn.execute("DELETE FROM reading_history WHERE id = ? AND user_id = ?", (history_id, user_id))
    conn.commit()
    conn.close()


def get_secret_key():
    key_file = os.path.join(os.path.dirname(__file__), "data", "secret_key.txt")
    os.makedirs(os.path.dirname(key_file), exist_ok=True)
    if os.path.exists(key_file):
        with open(key_file) as f:
            return f.read().strip()
    key = secrets.token_hex(64)
    with open(key_file, "w") as f:
        f.write(key)
    return key
