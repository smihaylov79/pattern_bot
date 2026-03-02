import plotly.express as px
import matplotlib.pyplot as plt
import pandas as pd


def pattern_frequency_chart(pattern_counts):
    fig = px.bar(
        x=pattern_counts.index,
        y=pattern_counts.values,
        title="Pattern Frequency",
        labels={"x": "Pattern", "y": "Count"}
    )
    return fig


def signal_distribution_chart(df):
    grouped = df.groupby("symbol")[["long_signal", "short_signal"]].sum().reset_index()
    fig = px.bar(
        grouped,
        x="symbol",
        y=["long_signal", "short_signal"],
        barmode="group",
        title="Signal Distribution by Symbol"
    )
    return fig


def pattern_signal_chart(attr_df):
    fig = px.bar(
        attr_df,
        x="pattern",
        y=["long_prob", "short_prob"],
        barmode="group",
        title="Probability of Signal Given Pattern"
    )
    return fig


def plot_trade_path(trade, price_df):
    entry_time = trade["entry_time"]
    exit_time = trade["exit_time"]

    # Extend 30 minutes after exit
    extended_exit = exit_time + pd.Timedelta(minutes=30)

    segment = price_df.loc[
        (price_df.index >= entry_time) &
        (price_df.index <= extended_exit)
    ]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(segment.index, segment["close"], label="Price")

    # Mark entry
    ax.scatter(entry_time, trade["entry_price"], color="green", s=80, label="Entry")

    # Mark exit
    ax.scatter(exit_time, trade["exit_price"], color="red", s=80, label="Exit (SL/TP)")

    # Mark extended window end
    ax.axvline(extended_exit, color="gray", linestyle="--", label="Extended +30m")

    ax.set_title(f"{trade['symbol']} — {trade['signal']} — {trade['direction']}")
    ax.legend()
    ax.grid(True)

    return fig
