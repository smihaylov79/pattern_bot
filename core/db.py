import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "logs" / "bot.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            candle_time TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            bull_eng INTEGER,
            bear_eng INTEGER,
            hammer INTEGER,
            shooting_star INTEGER,
            inside_bar INTEGER,
            near_sr INTEGER,
            long_sig INTEGER,
            short_sig INTEGER,
            action TEXT,
            lots REAL,
            sl REAL,
            tp REAL
        )
    """)
    conn.commit()
    conn.close()
