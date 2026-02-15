import sqlite3
import pandas as pd
import MetaTrader5 as mt5

DB_PATH = r"C:\Users\stoya\OneDrive\Invest\pattern_bot\logs\bot.db"


def load_logs(path=DB_PATH):
    conn = sqlite3.connect(path)
    df = pd.read_sql("SELECT * FROM logs", conn)
    conn.close()
    return df


def load_trade_history(path=DB_PATH):
    conn = sqlite3.connect(path)
    df = pd.read_sql("SELECT * FROM trade_history", conn)
    conn.close()
    return df


def load_price_history(symbols, timeframe=mt5.TIMEFRAME_M1, bars=2000):
    mt5.initialize()
    price_data = {}

    for symbol in symbols:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        df = pd.DataFrame(rates)

        if df.empty:
            print(f"[WARN] No price data for {symbol}")
            continue

        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
        price_data[symbol] = df

    return price_data
