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


def generate_signals(df_ltf, df_htf, sr_tolerance=0.0015):

    df = df_ltf.copy()

    # 1. Detect patterns
    for name, func in PATTERNS.items():
        df[name] = func(df)

    # 2. HTF Support/Resistance
    sr = find_levels(df_htf)
    levels = sr["levels"]

    def near_level(price):
        return any(abs(price - lvl) <= sr_tolerance * price for lvl in levels)

    df["near_sr"] = df["close"].apply(near_level)

    # 3. HTF Smart Money Zones (THIS WAS MISSING)
    smz = find_impulse_zones(df_htf)

    # Extract supply/demand zones
    demand_zones = smz[smz["type"] == "demand"][["low", "high"]].values
    supply_zones = smz[smz["type"] == "supply"][["low", "high"]].values

    # Helper functions (ADD THEM HERE)
    def in_demand(price):
        for low, high in demand_zones:
            if low <= price <= high:
                return True
        return False

    def in_supply(price):
        for low, high in supply_zones:
            if low <= price <= high:
                return True
        return False

    # Add SMZ columns to LTF df
    df["in_demand"] = df["close"].apply(in_demand)
    df["in_supply"] = df["close"].apply(in_supply)

    # 4. HTF directional bias
    df_htf_ma = df_htf["close"].rolling(20).mean()
    htf_bias = (df_htf["close"] > df_htf_ma).iloc[-1]

    # 5. Initialize signals
    df["long_signal"] = False
    df["short_signal"] = False

    # 6. Add pattern-based signals (engulfing, hammer, shooting star, inside bar)

    # === ENGULFINGS ===
    df["long_signal"] |= (
            df["bullish_engulfing"]
            & df["near_sr"]
            & df["in_demand"]
            & htf_bias
    )

    df["short_signal"] |= (
            df["bearish_engulfing"]
            & df["near_sr"]
            & df["in_supply"]
            & (~htf_bias)
    )

    # === HAMMER ===
    df["long_signal"] |= (
            df["hammer"]
            & df["in_demand"]
            & htf_bias
    )

    # === SHOOTING STAR ===
    df["short_signal"] |= (
            df["shooting_star"]
            & df["in_supply"]
            & (~htf_bias)
    )

    # === INSIDE BAR BREAKOUT ===
    mother_high = df["high"].shift(1)
    mother_low = df["low"].shift(1)

    df["long_signal"] |= (
        df["inside_bar"]
        & (df["close"] > mother_high)
        & htf_bias
    )

    df["short_signal"] |= (
        df["inside_bar"]
        & (df["close"] < mother_low)
        & (~htf_bias)
    )

    # === PRIORITY RESOLUTION ===

    # 1. Engulfing overrides everything
    engulf_long = df["bullish_engulfing"] & df["long_signal"]
    engulf_short = df["bearish_engulfing"] & df["short_signal"]

    # 2. Hammer / Shooting Star (second priority)
    wick_long = df["hammer"] & df["long_signal"]
    wick_short = df["shooting_star"] & df["short_signal"]

    # 3. Inside bar (lowest priority)
    inside_long = df["inside_bar"] & df["long_signal"]
    inside_short = df["inside_bar"] & df["short_signal"]

    # Reset signals
    df["long_signal"] = False
    df["short_signal"] = False

    # Apply priority
    df.loc[engulf_long, "long_signal"] = True
    df.loc[engulf_short, "short_signal"] = True

    df.loc[~(engulf_long | engulf_short) & wick_long, "long_signal"] = True
    df.loc[~(engulf_long | engulf_short) & wick_short, "short_signal"] = True

    df.loc[
        ~(engulf_long | engulf_short | wick_long | wick_short) & inside_long,
        "long_signal"
    ] = True

    df.loc[
        ~(engulf_long | engulf_short | wick_long | wick_short) & inside_short,
        "short_signal"
    ] = True

    df["trigger_pattern"] = None

    df.loc[df["long_signal"] & df["bullish_engulfing"], "trigger_pattern"] = "bullish_engulfing"
    df.loc[df["short_signal"] & df["bearish_engulfing"], "trigger_pattern"] = "bearish_engulfing"

    df.loc[df["long_signal"] & df["hammer"], "trigger_pattern"] = "hammer"
    df.loc[df["short_signal"] & df["shooting_star"], "trigger_pattern"] = "shooting_star"

    df.loc[df["long_signal"] & df["inside_bar"], "trigger_pattern"] = "inside_bar"
    df.loc[df["short_signal"] & df["inside_bar"], "trigger_pattern"] = "inside_bar"

    return df
