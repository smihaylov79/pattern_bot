import pandas as pd
from .patterns import PATTERNS
from .support_resistance import find_levels
from .smart_money_zones import find_impulse_zones


HTF_MAP = {
    "M5": "M15",
    "M15": "H1",
    "M30": "H1",
    "H1": "H4",
    "H4": "D1",
}


def generate_signals(
    df_ltf: pd.DataFrame,
    df_htf: pd.DataFrame,
    sr_tolerance: float = 0.0015,
) -> pd.DataFrame:
    df = df_ltf.copy()

    # patterns
    for name, func in PATTERNS.items():
        df[name] = func(df)

    # S/R on HTF
    sr = find_levels(df_htf)
    levels = sr["levels"]

    # smart money zones on HTF
    smz = find_impulse_zones(df_htf)

    def near_level(price):
        for lvl in levels:
            if abs(price - lvl) <= sr_tolerance * price:
                return True
        return False

    df["near_sr"] = df["close"].apply(near_level)

    # simple directional bias from HTF: close vs 20-period MA
    df_htf_ma = df_htf["close"].rolling(20).mean()
    htf_bias = (df_htf["close"] > df_htf_ma).iloc[-1]  # True = bullish bias

    # example entry conditions
    df["long_signal"] = (
        df["bullish_engulfing"]
        & df["near_sr"]
        & htf_bias
    )

    df["short_signal"] = (
        df["bearish_engulfing"]
        & df["near_sr"]
        & (~htf_bias)
    )

    return df
