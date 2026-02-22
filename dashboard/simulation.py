import pandas as pd

from core.patterns import PATTERNS


# def simulate_confluence_effect(logs, symbol_settings, recent_window=3, default_min=2):
#     """
#     Replays historical logs with new confluence rules and compares:
#     - original triggered trades
#     - trades that would trigger under new rules
#     """
#
#     # ---------------------------------------------------------
#     # 1. Filter only rows where a signal was evaluated
#     # ---------------------------------------------------------
#     logs = logs.copy()
#     logs = logs[logs["reason"].notna()]
#
#     # Ensure pattern columns are boolean/int
#     pattern_cols = [c for c in logs.columns if c in PATTERNS.keys()]
#
#     # ---------------------------------------------------------
#     # 2. Compute confluence per row (only allowed patterns)
#     # ---------------------------------------------------------
#     def compute_allowed_confluence(row, allowed_patterns):
#         return sum(int(row[p]) for p in pattern_cols if allowed_patterns == "all" or p in allowed_patterns)
#
#     logs["pattern_count"] = 0
#     logs["recent_pattern_count"] = 0
#
#     # ---------------------------------------------------------
#     # 3. Apply symbol-specific settings
#     # ---------------------------------------------------------
#     results = []
#
#     for symbol, group in logs.groupby("symbol"):
#         cfg = symbol_settings.get(symbol, {})
#         allowed = cfg.get("allowed_patterns", "all")
#         min_conf = cfg.get("min_confluence", default_min)
#
#         g = group.copy()
#
#         # Count allowed patterns
#         g["pattern_count"] = g.apply(lambda r: compute_allowed_confluence(r, allowed), axis=1)
#
#         # Rolling confluence
#         g["recent_pattern_count"] = (
#             g["pattern_count"]
#             .rolling(recent_window)
#             .sum()
#             .fillna(0)
#         )
#
#         # Apply confluence threshold
#         g["passes_confluence"] = g["recent_pattern_count"] >= min_conf
#
#         # Determine which trades would trigger
#         # original: triggered_trade == True
#         # new: raw_signal & passes_confluence
#         g["would_trigger"] = g["raw_signal"] & g["passes_confluence"]
#
#         results.append(g)
#
#     logs2 = pd.concat(results, ignore_index=True)
#
#     # ---------------------------------------------------------
#     # 4. Build comparison table
#     # ---------------------------------------------------------
#     def filtered_profit(sub):
#         return sub.loc[sub["would_trigger"], "profit"].sum()
#
#     comparison = (
#         logs2.groupby(["symbol", "signal"])
#         .agg(
#             original_trades=("triggered_trade", "sum"),
#             original_profit=("profit", "sum"),
#             filtered_trades=("would_trigger", "sum"),
#             filtered_profit=("profit", filtered_profit),
#         )
#         .reset_index()
#     )
#
#     # Compute deltas
#     comparison["trade_diff"] = comparison["filtered_trades"] - comparison["original_trades"]
#     comparison["profit_diff"] = comparison["filtered_profit"] - comparison["original_profit"]
#
#     return comparison, logs2
