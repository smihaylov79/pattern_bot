import pandas as pd



def pattern_probabilities(df):
    patterns = ["bull_eng", "bear_eng", "hammer", "shooting_star", "inside_bar"]
    results = {}
    for p in patterns:
        long_prob = df[df[p] == 1]["long_sig"].mean()
        short_prob = df[df[p] == 1]["short_sig"].mean()
        results[p] = {"long_prob": long_prob, "short_prob": short_prob}
    return results


def pattern_signal_attribution(df):
    patterns = ['bullish_engulfing', 'bearish_engulfing', 'hammer',
       'shooting_star', 'morning_star', 'evening_star', 'bullish_pin_bar',
       'bearish_pin_bar', 'bullish_three_bar_reversal',
       'bearish_three_bar_reversal', 'bullish_breakout_bar',
       'bearish_breakout_bar', 'bullish_inside_bar', 'bearish_inside_bar',
       'doji', 'outside_bar',]
    rows = []

    for p in patterns:
        subset = df[df[p] == 1]
        total = len(subset)

        if total == 0:
            rows.append([p, 0, 0, 0, 0])
            continue

        long_hits = subset["long_signal"].sum()
        short_hits = subset["short_signal"].sum()

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

    if row["bullish_engulfing"] == 1:
        reasons.append("Bullish Engulfing")
    if row["bearish_engulfing"] == 1:
        reasons.append("Bearish Engulfing")
    if row["hammer"] == 1:
        reasons.append("Hammer")
    if row["shooting_star"] == 1:
        reasons.append("Shooting Star")
    if row["morning_star"] == 1:
        reasons.append("Morning Star")
    if row["evening_star"] == 1:
        reasons.append("Evening Star")
    if row["bullish_pin_bar"] == 1:
        reasons.append("Bullish Pin Bar")
    if row["bearish_pin_bar"] == 1:
        reasons.append("Bearish Pin Bar")
    if row["bullish_three_bar_reversal"] == 1:
        reasons.append("Bullish Three Bar Reversal")
    if row["bearish_three_bar_reversal"] == 1:
        reasons.append("Bearish Three Bar Reversal")
    if row["bullish_breakout_bar"] == 1:
        reasons.append("Bullish Breakout Bar")
    if row["bearish_breakout_bar"] == 1:
        reasons.append("Bearish Breakout Bar")
    if row["bullish_inside_bar"] == 1:
        reasons.append("Bullish Inside Bar")
    if row["bearish_inside_bar"] == 1:
        reasons.append("Bearish Inside Bar")
    if row["doji"] == 1:
        reasons.append("Doji")
    if row["outside_bar"] == 1:
        reasons.append("Outside Bar")

    if row["long_signal"] == 1:
        signal = "LONG"
    elif row["short_signal"] == 1:
        signal = "SHORT"
    else:
        signal = "NO SIGNAL"

    return signal, reasons


def calculate_mfe_mae(trade, price_df):
    entry_time = trade["entry_time"]
    exit_time = trade["exit_time"]
    direction = trade["direction"]  # "buy" or "sell"
    entry_price = trade["entry_price"]

    # Extend window 30 minutes after exit
    extended_exit = exit_time + pd.Timedelta(minutes=30)

    # Slice price data
    segment = price_df.loc[
        (price_df.index >= entry_time) & (price_df.index <= extended_exit),
        "close"
    ]

    if segment.empty:
        return None, None, None, None, None, None

    # MFE / MAE in points
    if direction == "buy":
        mfe = segment.max() - entry_price
        mae = segment.min() - entry_price
        optimal_exit = segment.max()
        actual_points = trade["exit_price"] - entry_price
    else:  # sell
        mfe = entry_price - segment.min()
        mae = entry_price - segment.max()
        optimal_exit = segment.min()
        actual_points = entry_price - trade["exit_price"]

    # left on table (only for winners)
    left_on_table = mfe - actual_points if actual_points > 0 else 0

    # avoidable loss (only for losers)
    avoidable_loss = actual_points - mae if actual_points < 0 else 0

    return mfe, mae, optimal_exit, left_on_table, avoidable_loss, actual_points

def reconstruct_trades(df):
    df = df.copy()
    df["time"] = pd.to_datetime(df["time"])

    trades = []

    for pid, g in df.groupby("position_id"):
        g = g.sort_values("time")

        # ENTRY = first row where entry == 0
        entry_rows = g[g["entry"] == 0]
        if entry_rows.empty:
            continue
        entry = entry_rows.iloc[0]

        # EXIT = last row where entry == 1
        exit_rows = g[g["entry"] == 1]
        if exit_rows.empty:
            continue
        exit_ = exit_rows.iloc[-1]

        direction = "buy" if entry["type"] == 0 else "sell"

        # classify exit reason
        comment = str(exit_["comment"]).lower()
        if "tp" in comment:
            exit_reason = "tp"
        elif "sl" in comment:
            exit_reason = "sl"
        else:
            exit_reason = "other"

        trades.append({
            "position_id": pid,
            "symbol": entry["symbol"],
            "signal": entry["signal"],
            "direction": direction,
            "entry_time": entry["time"],
            "exit_time": exit_["time"],
            "entry_price": entry["price"],
            "exit_price": exit_["price"],
            "profit": exit_["profit"],
            "volume": entry["volume"],
            "exit_reason": exit_reason,
        })

    trades = pd.DataFrame(trades)

    # holding time
    trades["holding_minutes"] = (
        trades["exit_time"] - trades["entry_time"]
    ).dt.total_seconds() / 60

    # equity curve
    trades = trades.sort_values("exit_time").reset_index(drop=True)
    trades["equity"] = trades["profit"].cumsum()

    return trades


def classify_recovery(mfe):
    if mfe is None:
        return "No data"
    if mfe < 0:
        return "No recovery"
    elif mfe < 5:
        return "0 to +5 points"
    elif mfe < 10:
        return "+5 to +10 points"
    elif mfe < 20:
        return "+10 to +20 points"
    else:
        return "20+ points"


def simulate_confluence_effect(logs, trade_history, symbol_settings, recent_window=3, default_min=2):
    import re
    logs = logs.copy()
    logs = logs[logs["result"].notna()]

    # ---------------------------------------------------------
    # 1. Extract order number from logs.reason
    # ---------------------------------------------------------
    def extract_order(reason):
        if isinstance(reason, str):
            m = re.search(r"order=(\d+)", reason)
            if m:
                return int(m.group(1))
        return None

    logs["order"] = logs["result"].apply(extract_order)

    # ---------------------------------------------------------
    # 2. Build lookup tables from trade_history
    # ---------------------------------------------------------
    order_to_pos = trade_history.set_index("order")["position_id"].to_dict()

    pos_to_profit = (
        trade_history
        .sort_values("time_msc")
        .groupby("position_id")["profit"]
        .last()
        .to_dict()
    )

    pos_to_signal = (
        trade_history
        .groupby("position_id")["signal"]
        .first()
        .to_dict()
    )

    # ---------------------------------------------------------
    # 3. Attach trade info to logs
    # ---------------------------------------------------------
    logs["position_id"] = logs["order"].map(order_to_pos)
    logs["profit"] = logs["position_id"].map(pos_to_profit)
    logs["signal"] = logs["position_id"].map(pos_to_signal)
    logs["triggered_trade"] = logs["profit"].notna()

    # ---------------------------------------------------------
    # 4. Confluence based on long_sig + short_sig
    # ---------------------------------------------------------
    # raw signal = long_sig OR short_sig
    logs["raw_signal"] = (logs["long_signal"] == 1) | (logs["short_signal"] == 1)

    # pattern_count = number of signals on this bar (0, 1, or 2)
    logs["pattern_count"] = logs["long_signal"] + logs["short_signal"]

    results = []

    for symbol, group in logs.groupby("symbol"):
        cfg = symbol_settings.get(symbol, {})
        min_conf = cfg.get("min_confluence", default_min)

        g = group.copy()

        # rolling confluence
        g["recent_pattern_count"] = (
            g["pattern_count"]
            .rolling(recent_window)
            .sum()
            .fillna(0)
        )

        g["passes_confluence"] = g["recent_pattern_count"] >= min_conf

        # would trigger under new rules
        g["would_trigger"] = g["raw_signal"] & g["passes_confluence"]

        results.append(g)

    logs2 = pd.concat(results, ignore_index=True)

    # ---------------------------------------------------------
    # 5. Build before/after comparison table
    # ---------------------------------------------------------
    comparison = (
        logs2.groupby(["symbol", "signal"])
        .apply(lambda g: pd.Series({
            "original_trades": g["triggered_trade"].sum(),
            "original_profit": g["profit"].sum(),
            # "filtered_trades": g["would_trigger"].sum(),
            "filtered_trades": g.loc[g["would_trigger"] & g["triggered_trade"], "position_id"].nunique(),

            "filtered_profit": g.loc[g["would_trigger"], "profit"].sum()
        }))
        .reset_index()
    )

    comparison["trade_diff"] = comparison["filtered_trades"] - comparison["original_trades"]
    comparison["profit_diff"] = comparison["filtered_profit"] - comparison["original_profit"]

    return comparison, logs2

