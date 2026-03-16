import sqlite3
from datetime import datetime
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


def log_to_db(symbol, last, df_ltf, action, lots, sl, tp, result, timeframe):
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
            INSERT INTO logs (
                timestamp, symbol, timeframe, candle_time,
                open, high, low, close,

                bullish_engulfing, bearish_engulfing,
                hammer, shooting_star,
                morning_star, evening_star,

                bullish_pin_bar, bearish_pin_bar,
                bullish_three_bar_reversal, bearish_three_bar_reversal,
                bullish_breakout_bar, bearish_breakout_bar,
                bullish_inside_bar, bearish_inside_bar,

                doji, outside_bar,

                near_sr, in_demand, in_supply, vol_ok,

                bullish_count, bearish_count,
                recent_bullish, recent_bearish,

                bias_long, bias_short,
                htf_ma_fast, htf_ma_slow, htf_ma_fast_slope,

                long_signal, short_signal,
                trigger_pattern,

                action, lots, sl, tp, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            symbol,
            timeframe,
            df_ltf.index[-1].isoformat(),

            df_ltf["open"].iloc[-1],
            df_ltf["high"].iloc[-1],
            df_ltf["low"].iloc[-1],
            df_ltf["close"].iloc[-1],

            int(last["bullish_engulfing"]),
            int(last["bearish_engulfing"]),
            int(last["hammer"]),
            int(last["shooting_star"]),
            int(last["morning_star"]),
            int(last["evening_star"]),

            int(last["bullish_pin_bar"]),
            int(last["bearish_pin_bar"]),
            int(last["bullish_three_bar_reversal"]),
            int(last["bearish_three_bar_reversal"]),
            int(last["bullish_breakout_bar"]),
            int(last["bearish_breakout_bar"]),
            int(last["bullish_inside_bar"]),
            int(last["bearish_inside_bar"]),

            int(last["doji"]),
            int(last["outside_bar"]),

            int(last["near_sr"]),
            int(last["in_demand"]),
            int(last["in_supply"]),
            int(last["vol_ok"]),

            int(last["bullish_count"]),
            int(last["bearish_count"]),
            int(last["recent_bullish"]),
            int(last["recent_bearish"]),

            int(last["bias_long"]),
            int(last["bias_short"]),
            float(last["htf_ma_fast"]),
            float(last["htf_ma_slow"]),
            float(last["htf_ma_fast_slope"]),

            int(last["long_signal"]),
            int(last["short_signal"]),
            last["trigger_pattern"],

            action,
            lots,
            sl,
            tp,
            result
        ))

    conn.commit()
    conn.close()