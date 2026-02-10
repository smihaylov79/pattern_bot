import sqlite3
import pandas as pd


DB_PATH = r"C:\Users\stoya\OneDrive\Invest\pattern_bot\logs\bot.db"


def load_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    df = pd.read_sql_query("SELECT * FROM logs", conn)
    conn.close()
    return df

