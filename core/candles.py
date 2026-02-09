import pandas as pd


def add_candle_metrics(df: pd.DataFrame) -> pd.DataFrame:
    body = (df["close"] - df["open"]).abs()
    range_ = df["high"] - df["low"]
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]

    df = df.copy()
    df["body"] = body
    df["range"] = range_
    df["upper_wick"] = upper_wick
    df["lower_wick"] = lower_wick
    df["is_bull"] = df["close"] > df["open"]
    df["is_bear"] = df["close"] < df["open"]
    return df
