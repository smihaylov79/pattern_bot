import pandas as pd


def find_impulse_zones(
    df: pd.DataFrame,
    lookback: int = 20,
    impulse_factor: float = 1.5,
) -> pd.DataFrame:
    df = df.copy()
    df["range"] = df["high"] - df["low"]
    avg_range = df["range"].rolling(lookback).mean()

    # impulsive candles
    df["impulse_up"] = (df["is_bull"]) & (df["range"] >= impulse_factor * avg_range)
    df["impulse_down"] = (df["is_bear"]) & (df["range"] >= impulse_factor * avg_range)

    zones = []
    for i in range(1, len(df)):
        if df["impulse_up"].iloc[i]:
            # demand zone: last bearish candle before impulse
            j = i - 1
            while j >= 0 and df["is_bear"].iloc[j]:
                j -= 1
            j += 1
            if j < i:
                zones.append({
                    "type": "demand",
                    "start": df.index[j],
                    "end": df.index[i],
                    "low": df["low"].iloc[j:i+1].min(),
                    "high": df["high"].iloc[j:i+1].max(),
                })
        if df["impulse_down"].iloc[i]:
            # supply zone: last bullish candle before impulse
            j = i - 1
            while j >= 0 and df["is_bull"].iloc[j]:
                j -= 1
            j += 1
            if j < i:
                zones.append({
                    "type": "supply",
                    "start": df.index[j],
                    "end": df.index[i],
                    "low": df["low"].iloc[j:i+1].min(),
                    "high": df["high"].iloc[j:i+1].max(),
                })

    return pd.DataFrame(zones)
