import pandas as pd
import numpy as np

from core.data_feed import get_bars


def calculate_atr(symbol: str, timeframe: str = "M5", period: int = 14):
    """
    Calculates ATR using the same get_bars() function as the rest of the bot.
    Returns ATR in price units (not points).
    """

    # We need period + 1 candles to compute TR for all periods
    try:
        df = get_bars(symbol, timeframe, period + 2)
    except:
        # fallback to M15
        df = get_bars(symbol, "M15", period + 2)

    # df = get_bars(symbol, timeframe, period + 1)

    if df is None or df.empty or len(df) < period + 1:
        return None

    # True Range components
    high_low = df["high"] - df["low"]
    high_prev_close = (df["high"] - df["close"].shift(1)).abs()
    low_prev_close = (df["low"] - df["close"].shift(1)).abs()

    # True Range
    tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    # ATR = SMA of TR
    atr = tr.rolling(period).mean().iloc[-1]

    return float(atr)


def bullish_engulfing(df: pd.DataFrame) -> pd.Series:
    o, c = df["open"], df["close"]
    prev_o, prev_c = o.shift(1), c.shift(1)

    prev_bear = prev_c < prev_o
    curr_bull = c > o
    engulf = (c >= prev_o) & (o <= prev_c)

    return (prev_bear & curr_bull & engulf).fillna(False)


def bearish_engulfing(df: pd.DataFrame) -> pd.Series:
    o, c = df["open"], df["close"]
    prev_o, prev_c = o.shift(1), c.shift(1)

    prev_bull = prev_c > prev_o
    curr_bear = c < o
    engulf = (c <= prev_o) & (o >= prev_c)

    return (prev_bull & curr_bear & engulf).fillna(False)


def hammer(df: pd.DataFrame, body_ratio: float = 0.3) -> pd.Series:
    body = df["body"]
    lower = df["lower_wick"]
    upper = df["upper_wick"]

    small_body = body <= body.rolling(20).mean() * body_ratio
    long_lower = lower >= 2 * body
    tiny_upper = upper <= body

    return (small_body & long_lower & tiny_upper & df["is_bull"]).fillna(False)


def shooting_star(df: pd.DataFrame, body_ratio: float = 0.3) -> pd.Series:
    body = df["body"]
    lower = df["lower_wick"]
    upper = df["upper_wick"]

    small_body = body <= body.rolling(20).mean() * body_ratio
    long_upper = upper >= 2 * body
    tiny_lower = lower <= body

    return (small_body & long_upper & tiny_lower & df["is_bear"]).fillna(False)


def inside_bar(df: pd.DataFrame) -> pd.Series:
    prev_high = df["high"].shift(1)
    prev_low = df["low"].shift(1)
    return ((df["high"] <= prev_high) & (df["low"] >= prev_low)).fillna(False)


def pin_bar(df: pd.DataFrame, wick_ratio: float = 2.0, body_ratio: float = 0.3) -> pd.Series:
    body = df["body"]
    upper = df["upper_wick"]
    lower = df["lower_wick"]

    small_body = body <= body.rolling(20).mean() * body_ratio

    long_lower = lower >= wick_ratio * body
    long_upper = upper >= wick_ratio * body

    tiny_upper = upper <= body
    tiny_lower = lower <= body

    bullish_pin = small_body & long_lower & tiny_upper
    bearish_pin = small_body & long_upper & tiny_lower

    return (bullish_pin | bearish_pin).fillna(False)


def doji(df: pd.DataFrame, threshold: float = 0.1) -> pd.Series:
    body = df["body"]
    range_ = df["high"] - df["low"]
    return (body <= range_ * threshold).fillna(False)


def morning_star(df: pd.DataFrame) -> pd.Series:
    o, c = df["open"], df["close"]

    c1_bear = c.shift(2) < o.shift(2)
    c2_small = (df["body"].shift(1) < df["body"].rolling(20).mean().shift(1) * 0.5)
    c3_bull = c > o

    c3_closes_into_c1 = c >= (o.shift(2) + df["body"].shift(2) * 0.5)

    return (c1_bear & c2_small & c3_bull & c3_closes_into_c1).fillna(False)


def evening_star(df: pd.DataFrame) -> pd.Series:
    o, c = df["open"], df["close"]

    c1_bull = c.shift(2) > o.shift(2)
    c2_small = (df["body"].shift(1) < df["body"].rolling(20).mean().shift(1) * 0.5)
    c3_bear = c < o

    c3_closes_into_c1 = c <= (o.shift(2) - df["body"].shift(2) * 0.5)

    return (c1_bull & c2_small & c3_bear & c3_closes_into_c1).fillna(False)


def three_bar_reversal(df: pd.DataFrame) -> pd.Series:
    low1 = df["low"].shift(2)
    low2 = df["low"].shift(1)
    low3 = df["low"]

    high1 = df["high"].shift(2)
    high2 = df["high"].shift(1)
    high3 = df["high"]

    bull = (low2 < low1) & (low3 > low2) & (df["close"] > df["open"])
    bear = (high2 > high1) & (high3 < high2) & (df["close"] < df["open"])

    return (bull | bear).fillna(False)


def breakout_bar(df: pd.DataFrame, factor: float = 1.5) -> pd.Series:
    range_ = df["high"] - df["low"]
    avg_range = range_.rolling(20).mean()

    big_range = range_ > avg_range * factor

    bull = big_range & (df["close"] > df["open"])
    bear = big_range & (df["close"] < df["open"])

    return (bull | bear).fillna(False)


def outside_bar(df: pd.DataFrame) -> pd.Series:
    prev_high = df["high"].shift(1)
    prev_low = df["low"].shift(1)

    return ((df["high"] > prev_high) & (df["low"] < prev_low)).fillna(False)


PATTERNS = {
    "bullish_engulfing": bullish_engulfing,
    "bearish_engulfing": bearish_engulfing,
    "hammer": hammer,
    "shooting_star": shooting_star,
    "inside_bar": inside_bar,
    "pin_bar": pin_bar,
    "doji": doji,
    "morning_star": morning_star,
    "evening_star": evening_star,
    "three_bar_reversal": three_bar_reversal,
    "breakout_bar": breakout_bar,
    "outside_bar": outside_bar,
}

