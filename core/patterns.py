import pandas as pd


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


PATTERNS = {
    "bullish_engulfing": bullish_engulfing,
    "bearish_engulfing": bearish_engulfing,
    "hammer": hammer,
    "shooting_star": shooting_star,
    "inside_bar": inside_bar,
}
