import pandas as pd
import numpy as np


def _is_swing_high(df: pd.DataFrame, i: int, left: int, right: int) -> bool:
    h = df["high"].iloc[i]
    return h == df["high"].iloc[i-left:i+right+1].max()


def _is_swing_low(df: pd.DataFrame, i: int, left: int, right: int) -> bool:
    l = df["low"].iloc[i]
    return l == df["low"].iloc[i-left:i+right+1].min()


def find_levels(
    df: pd.DataFrame,
    left: int = 3,
    right: int = 3,
    min_touches: int = 2,
    tolerance: float = 0.001,
) -> dict:
    highs = []
    lows = []

    for i in range(left, len(df) - right):
        if _is_swing_high(df, i, left, right):
            highs.append(df["high"].iloc[i])
        if _is_swing_low(df, i, left, right):
            lows.append(df["low"].iloc[i])

    levels = highs + lows
    levels.sort()

    clustered = []
    for lvl in levels:
        if not clustered:
            clustered.append([lvl])
        else:
            if abs(lvl - np.mean(clustered[-1])) <= tolerance * lvl:
                clustered[-1].append(lvl)
            else:
                clustered.append([lvl])

    sr_levels = [
        np.mean(cluster)
        for cluster in clustered
        if len(cluster) >= min_touches
    ]

    return {"levels": sr_levels}
