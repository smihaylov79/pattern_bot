import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd


DB_PATH = r"C:\Users\stoya\OneDrive\Invest\pattern_bot\logs\bot.db"


def load_trade_history(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM trade_history", conn)
    conn.close()
    return df


def preprocess_history(df: pd.DataFrame) -> pd.DataFrame:
    # Drop deposits/withdrawals (type = 2 in MT5 deals)
    df = df[df["type"] != 2].copy()

    # Parse times
    df["time"] = pd.to_datetime(df["time"])
    df["time_msc"] = pd.to_datetime(df["time_msc"])

    return df


def exclude_manual_closes(df: pd.DataFrame) -> pd.DataFrame:
    """
    We define manual closes as:
    - entry == 1 (exit deal)
    - comment == "" (no sl/tp info)
    - profit != 0 (real close, not some zero-fee adjustment)
    We exclude the entire position_id from the analysis.
    """
    exits = df[df["entry"] == 1].copy()
    manual_pos_ids = exits.loc[
        (exits["comment"] == "") & (exits["profit"] != 0), "position_id"
    ].unique()

    if len(manual_pos_ids) > 0:
        df = df[~df["position_id"].isin(manual_pos_ids)].copy()

    return df


def reconstruct_trades(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reconstruct trades from MT5 deals:
    - entry: entry == 0
    - exit:  entry == 1
    We merge on position_id.
    """
    entries = df[df["entry"] == 0].copy()
    exits = df[df["entry"] == 1].copy()

    trades = pd.merge(
        entries,
        exits,
        on="position_id",
        suffixes=("_entry", "_exit"),
        how="inner",
    )

    # Basic derived fields
    trades["entry_time"] = trades["time_entry"]
    trades["exit_time"] = trades["time_exit"]
    trades["symbol"] = trades["symbol_entry"]
    trades["signal"] = trades["signal_entry"]
    trades["direction"] = np.where(trades["type_entry"] == 0, "BUY", "SELL")

    trades["entry_price"] = trades["price_entry"]
    trades["exit_price"] = trades["price_exit"]
    trades["volume"] = trades["volume_entry"]
    trades["profit"] = trades["profit_exit"]
    trades["exit_comment"] = trades["comment_exit"]

    trades["holding_minutes"] = (
        trades["exit_time"] - trades["entry_time"]
    ).dt.total_seconds() / 60.0

    # Exit reason classification
    def classify_exit(comment: str) -> str:
        if isinstance(comment, str):
            c = comment.lower()
            if "tp" in c:
                return "tp"
            if "sl" in c:
                return "sl"
        return "other"

    trades["exit_reason"] = trades["exit_comment"].apply(classify_exit)

    # Sort by exit time for equity curve
    trades = trades.sort_values("exit_time").reset_index(drop=True)

    return trades


def compute_metrics(trades: pd.DataFrame) -> dict:
    metrics = {}

    profits = trades["profit"]
    metrics["n_trades"] = len(trades)
    metrics["n_wins"] = int((profits > 0).sum())
    metrics["n_losses"] = int((profits < 0).sum())
    metrics["win_rate"] = metrics["n_wins"] / metrics["n_trades"] if metrics["n_trades"] > 0 else np.nan

    metrics["avg_profit"] = profits.mean()
    metrics["median_profit"] = profits.median()

    total_profit = profits[profits > 0].sum()
    total_loss = profits[profits < 0].sum()
    metrics["total_profit"] = total_profit
    metrics["total_loss"] = total_loss
    metrics["net_profit"] = total_profit + total_loss

    if total_loss != 0:
        metrics["profit_factor"] = total_profit / abs(total_loss)
    else:
        metrics["profit_factor"] = np.nan

    metrics["avg_holding_min"] = trades["holding_minutes"].mean()

    # Equity curve
    trades["equity"] = profits.cumsum()
    metrics["max_equity"] = trades["equity"].max()
    metrics["min_equity"] = trades["equity"].min()

    # Simple max drawdown
    running_max = trades["equity"].cummax()
    drawdown = trades["equity"] - running_max
    metrics["max_drawdown"] = drawdown.min()

    return metrics


def group_stats(trades: pd.DataFrame):
    by_signal = (
        trades.groupby("signal")["profit"]
        .agg(["count", "mean", "sum"])
        .sort_values("sum", ascending=False)
    )

    by_symbol = (
        trades.groupby("symbol")["profit"]
        .agg(["count", "mean", "sum"])
        .sort_values("sum", ascending=False)
    )

    by_exit_reason = (
        trades.groupby("exit_reason")["profit"]
        .agg(["count", "mean", "sum"])
        .sort_values("sum", ascending=False)
    )

    return by_signal, by_symbol, by_exit_reason


def print_report(metrics: dict, by_signal, by_symbol, by_exit_reason):
    print("\n========== TRADE PERFORMANCE REPORT ==========\n")

    print("Overall:")
    print(f"  Trades:        {metrics['n_trades']}")
    print(f"  Wins:          {metrics['n_wins']}")
    print(f"  Losses:        {metrics['n_losses']}")
    print(f"  Win rate:      {metrics['win_rate']*100:.2f}%")
    print(f"  Avg profit:    {metrics['avg_profit']:.2f}")
    print(f"  Median profit: {metrics['median_profit']:.2f}")
    print(f"  Total profit:  {metrics['total_profit']:.2f}")
    print(f"  Total loss:    {metrics['total_loss']:.2f}")
    print(f"  Net profit:    {metrics['net_profit']:.2f}")
    print(f"  Profit factor: {metrics['profit_factor']:.2f}")
    print(f"  Avg holding:   {metrics['avg_holding_min']:.2f} min")
    print(f"  Max equity:    {metrics['max_equity']:.2f}")
    print(f"  Min equity:    {metrics['min_equity']:.2f}")
    print(f"  Max drawdown:  {metrics['max_drawdown']:.2f}")

    print("\nBy signal:")
    print(by_signal.to_string())

    print("\nBy symbol:")
    print(by_symbol.to_string())

    print("\nBy exit reason:")
    print(by_exit_reason.to_string())

    print("\n==============================================\n")


def save_trades(trades: pd.DataFrame, path: str = "trades_report.csv"):
    cols = [
        "position_id",
        "symbol",
        "direction",
        "signal",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "volume",
        "profit",
        "holding_minutes",
        "exit_reason",
        "exit_comment",
        "equity",
    ]
    trades[cols].to_csv(path, index=False)
    print(f"Detailed trades report saved to: {path}")


def main():
    print("Loading trade history from DB...")
    df = load_trade_history(DB_PATH)
    df = preprocess_history(df)
    df = exclude_manual_closes(df)

    print(f"Deals after filtering: {len(df)}")

    trades = reconstruct_trades(df)
    print(f"Reconstructed trades: {len(trades)}")

    metrics = compute_metrics(trades)
    by_signal, by_symbol, by_exit_reason = group_stats(trades)

    print_report(metrics, by_signal, by_symbol, by_exit_reason)
    # save_trades(trades)


if __name__ == "__main__":
    main()
