def pattern_probabilities(df):
    patterns = ["bull_eng", "bear_eng", "hammer", "shooting_star", "inside_bar"]
    results = {}
    for p in patterns:
        long_prob = df[df[p] == 1]["long_sig"].mean()
        short_prob = df[df[p] == 1]["short_sig"].mean()
        results[p] = {"long_prob": long_prob, "short_prob": short_prob}
    return results


import pandas as pd

def pattern_signal_attribution(df):
    patterns = ["bull_eng", "bear_eng", "hammer", "shooting_star", "inside_bar", "near_sr"]
    rows = []

    for p in patterns:
        subset = df[df[p] == 1]
        total = len(subset)

        if total == 0:
            rows.append([p, 0, 0, 0, 0])
            continue

        long_hits = subset["long_sig"].sum()
        short_hits = subset["short_sig"].sum()

        rows.append([
            p,
            total,
            long_hits,
            short_hits,
            long_hits / total,
            short_hits / total
        ])

    return pd.DataFrame(rows, columns=[
        "pattern", "count", "long_hits", "short_hits",
        "long_prob", "short_prob"
    ])


def explain_signal(row):
    reasons = []

    if row["bull_eng"] == 1:
        reasons.append("Bullish Engulfing")
    if row["bear_eng"] == 1:
        reasons.append("Bearish Engulfing")
    if row["hammer"] == 1:
        reasons.append("Hammer")
    if row["shooting_star"] == 1:
        reasons.append("Shooting Star")
    if row["inside_bar"] == 1:
        reasons.append("Inside Bar")
    if row["near_sr"] == 1:
        reasons.append("Near Support/Resistance")

    if row["long_sig"] == 1:
        sig = "LONG"
    elif row["short_sig"] == 1:
        sig = "SHORT"
    else:
        sig = "NO SIGNAL"

    return sig, reasons


def explain_signal_row(row):
    reasons = []

    if row["bull_eng"] == 1:
        reasons.append("Bullish Engulfing")
    if row["bear_eng"] == 1:
        reasons.append("Bearish Engulfing")
    if row["hammer"] == 1:
        reasons.append("Hammer")
    if row["shooting_star"] == 1:
        reasons.append("Shooting Star")
    if row["inside_bar"] == 1:
        reasons.append("Inside Bar")
    if row["near_sr"] == 1:
        reasons.append("Near Support/Resistance")

    if row["long_sig"] == 1:
        signal = "LONG"
    elif row["short_sig"] == 1:
        signal = "SHORT"
    else:
        signal = "NO SIGNAL"

    return signal, reasons
