import sqlite3
import pandas as pd
import numpy as np
import streamlit as st
import seaborn as sns
import matplotlib.pyplot as plt


# -----------------------------
# Load & preprocess
# -----------------------------
DB_PATH = r"C:\Users\stoya\OneDrive\Invest\pattern_bot\logs\bot.db"


def load_trade_history(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM trade_history", conn)
    conn.close()

    # Remove deposits/withdrawals
    df = df[df["type"] != 2].copy()

    # Parse timestamps
    df["time"] = pd.to_datetime(df["time"])
    df["time_msc"] = pd.to_datetime(df["time_msc"])

    return df


def exclude_manual_closes(df):
    exits = df[df["entry"] == 1].copy()

    manual_pos_ids = exits.loc[
        (exits["comment"] == "") & (exits["profit"] != 0),
        "position_id"
    ].unique()

    df = df[~df["position_id"].isin(manual_pos_ids)].copy()
    return df


# -----------------------------
# Trade reconstruction
# -----------------------------

# -----------------------------
# Metrics
# -----------------------------
def compute_metrics(trades):
    profits = trades["profit"]

    total_profit = profits[profits > 0].sum()
    total_loss = profits[profits < 0].sum()

    metrics = {
        "Trades": len(trades),
        "Wins": int((profits > 0).sum()),
        "Losses": int((profits < 0).sum()),
        "Win rate": f"{(profits > 0).mean() * 100:.2f}%",
        "Avg profit": profits.mean(),
        "Median profit": profits.median(),
        "Total profit": total_profit,
        "Total loss": total_loss,
        "Net profit": total_profit + total_loss,
        "Profit factor": total_profit / abs(total_loss) if total_loss != 0 else np.nan,
        "Avg holding (min)": trades["holding_minutes"].mean(),
        "Max drawdown": (trades["equity"] - trades["equity"].cummax()).min(),
    }

    return metrics
