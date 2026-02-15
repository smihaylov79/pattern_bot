import pandas as pd
import streamlit as st
import seaborn as sns
import numpy as np

from trade_performance import exclude_manual_closes, compute_metrics
from loader import load_trade_history
from queries import count_patterns, signal_stats
from charts import pattern_frequency_chart, signal_distribution_chart
from analytics import pattern_signal_attribution, calculate_mfe_mae, reconstruct_trades, classify_recovery
from charts import pattern_signal_chart
from analytics import explain_signal_row
import matplotlib.pyplot as plt

from charts import plot_trade_path
from analytics import calculate_mfe_mae


def render_dashboard(df):
    st.title("Trading Session Dashboard")

    st.subheader("Pattern Frequency")
    pattern_counts = count_patterns(df)
    st.plotly_chart(pattern_frequency_chart(pattern_counts))

    st.subheader("Signal Distribution")
    st.plotly_chart(signal_distribution_chart(df))

    st.subheader("Pattern → Signal Attribution")
    attr = pattern_signal_attribution(df)
    st.dataframe(attr)

    st.plotly_chart(pattern_signal_chart(attr))


def render_signal_explorer(df):
    st.header("🔍 Signal Explorer")

    st.write("Click a row to see why the signal was generated.")

    # Show table with clickable rows
    selected = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun"
    )

    if selected and "selection" in selected and selected["selection"]["rows"]:
        idx = selected["selection"]["rows"][0]
        row = df.iloc[idx]

        signal, reasons = explain_signal_row(row)

        st.subheader(f"Explanation for {row['timestamp']} — {row['symbol']}")
        st.write(f"**Signal:** {signal}")

        if len(reasons) == 0:
            st.info("No patterns were active on this candle.")
        else:
            st.write("**Patterns that triggered:**")
            for r in reasons:
                st.write(f"- {r}")
    else:
        st.info("Select a row from the table to see details.")


def render_trade_performance():
    st.header("📈 Trade Performance Analytics")

    df = load_trade_history()
    df = exclude_manual_closes(df)
    trades = reconstruct_trades(df)

    # Filters
    symbols = ["All"] + sorted(trades["symbol"].unique())
    signals = ["All"] + sorted(trades["signal"].unique())

    col1, col2 = st.columns(2)
    with col1:
        symbol_filter = st.selectbox("Symbol", symbols)
    with col2:
        signal_filter = st.selectbox("Signal", signals)

    date_range = st.date_input(
        "Date range",
        value=(trades["exit_time"].min().date(), trades["exit_time"].max().date())
    )

    # Apply filters
    filtered = trades.copy()

    if symbol_filter != "All":
        filtered = filtered[filtered["symbol"] == symbol_filter]

    if signal_filter != "All":
        filtered = filtered[filtered["signal"] == signal_filter]

    start_date, end_date = date_range
    filtered = filtered[
        (filtered["exit_time"].dt.date >= start_date) &
        (filtered["exit_time"].dt.date <= end_date)
        ]

    st.subheader("Summary Metrics")
    metrics = compute_metrics(filtered)

    colA, colB, colC = st.columns(3)
    colA.metric("Trades", metrics["Trades"])
    colA.metric("Win rate", metrics["Win rate"])
    colA.metric("Profit factor", f"{metrics['Profit factor']:.2f}")

    colB.metric("Net profit", f"{metrics['Net profit']:.2f}")
    colB.metric("Avg profit", f"{metrics['Avg profit']:.2f}")
    colB.metric("Median profit", f"{metrics['Median profit']:.2f}")

    colC.metric("Avg holding (min)", f"{metrics['Avg holding (min)']:.2f}")
    colC.metric("Max drawdown", f"{metrics['Max drawdown']:.2f}")

    st.subheader("Equity Curve")
    st.line_chart(filtered.set_index("exit_time")["equity"])

    st.subheader("Performance by Signal")
    st.dataframe(
        filtered.groupby("signal")["profit"]
        .agg(["count", "mean", "sum"])
        .sort_values("sum", ascending=False)
    )

    st.subheader("Performance by Symbol")
    st.dataframe(
        filtered.groupby("symbol")["profit"]
        .agg(["count", "mean", "sum"])
        .sort_values("sum", ascending=False)
    )

    matrix = (
        filtered
        .pivot_table(
            index="signal",
            columns="symbol",
            values="profit",
            aggfunc="sum",
            fill_value=0
        )
    )

    # Add total column
    matrix["ALL"] = matrix.sum(axis=1)

    # Sort by total performance
    matrix = matrix.sort_values("ALL", ascending=False)
    st.subheader("🔥 Signal × Symbol Heatmap (All Trades)")

    # Prepare matrix
    heatmap_data = matrix.copy()

    max_abs = np.abs(heatmap_data.values).max()

    # Create figure
    fig, ax = plt.subplots(figsize=(16, 8))

    sns.heatmap(
        heatmap_data,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        linewidths=0.7,
        linecolor="black",
        cbar_kws={"shrink": 0.7},
        annot_kws={"size": 14, "weight": "bold"},
        vmin=-max_abs,
        vmax=max_abs,
        center=0,
        ax=ax
    )

    ax.set_title("Signal × Symbol Performance Heatmap", fontsize=20, pad=20)
    ax.set_xlabel("Symbol", fontsize=14)
    ax.set_ylabel("Signal", fontsize=14)

    # Rotate labels for readability
    plt.xticks(rotation=45, ha="right", fontsize=15)
    plt.yticks(rotation=0, fontsize=15)

    st.pyplot(fig)

    st.subheader("⏰ Performance by Hour of Day")

    # Extract hour of exit
    filtered["exit_hour"] = filtered["exit_time"].dt.hour

    hourly = (
        filtered.groupby("exit_hour")["profit"]
        .agg(["count", "mean", "sum"])
        .rename(columns={"count": "Trades", "mean": "Avg Profit", "sum": "Total Profit"})
    )

    st.dataframe(hourly.style.format("{:.2f}"))

    st.bar_chart(hourly["Total Profit"])

    st.subheader("🏆 Win Rate by Hour")

    winrate = (
            filtered.assign(win=filtered["profit"] > 0)
            .groupby("exit_hour")["win"]
            .mean() * 100
    )

    st.line_chart(winrate)

    st.subheader("📉 Hourly Equity Curve (Normalized)")

    hourly_equity = (
        filtered.groupby("exit_hour")["profit"]
        .sum()
        .cumsum()
    )

    st.line_chart(hourly_equity)
    st.subheader("Holding Time Distribution (minutes)")
    st.bar_chart(filtered["holding_minutes"])


def render_trade_path_analysis(trades, price_data):
    st.header("📈 Trade Path Analysis (MFE / MAE)")

    results = []

    for _, trade in trades.iterrows():
        symbol = trade["symbol"]

        if symbol in price_data:
            mfe, mae, optimal_exit, left, avoidable, actual_points = calculate_mfe_mae(
                trade, price_data[symbol]
            )
        else:
            mfe = mae = optimal_exit = left = avoidable = actual_points = None

        results.append({
            "trade_id": trade["position_id"],
            "symbol": symbol,
            "signal": trade["signal"],
            "direction": trade["direction"],
            "entry_time": trade["entry_time"],
            "exit_time": trade["exit_time"],
            "entry_price": trade["entry_price"],
            "exit_price": trade["exit_price"],
            "profit": trade["profit"],
            "actual_points": actual_points,
            "MFE": mfe,
            "MAE": mae,
            "optimal_exit": optimal_exit,     # ← added back
            "left_on_table": left,
            "avoidable_loss": avoidable,
            "exit_reason": trade["exit_reason"],
        })

    df_results = pd.DataFrame(results)

    ## adding what could be

    df_results["recovery_group"] = df_results["MFE"].apply(classify_recovery)

    df_results = df_results.convert_dtypes()

    recovery_order = [
        "No recovery",
        "0 to +5 points",
        "+5 to +10 points",
        "+10 to +20 points",
        "20+ points"
    ]

    df_results["recovery_group"] = pd.Categorical(
        df_results["recovery_group"],
        categories=recovery_order,
        ordered=True
    )

    # Only losing trades
    losers = df_results[df_results["actual_points"] < 0]

    recovery_stats = (
        losers.groupby("recovery_group")["trade_id"]
        .count()
        .reset_index()
        .sort_values("recovery_group")
        .rename(columns={"trade_id": "count"})
    )
    st.subheader("🔥 Recovery Potential of Losing Trades")

    st.dataframe(recovery_stats, width="stretch")

    st.bar_chart(recovery_stats.set_index("recovery_group"))

    losers = df_results[df_results["actual_points"] < 0]
    could_be_profitable = losers[losers["MFE"] > 5]

    st.metric(
        "Losing trades that could have been winners",
        f"{len(could_be_profitable)} / {len(losers)}",
    )
    st.subheader("🔥 Recovery Potential by Signal (losing trades)")

    signal_recovery = (
            losers.assign(recover=(losers["MFE"] > 5))
            .groupby("signal")["recover"]
            .mean() * 100
    )

    st.bar_chart(signal_recovery)

    st.subheader("🔥 Recovery Potential by Symbol (losing trades)")

    symbol_recovery = (
            losers.assign(recover=(losers["MFE"] > 5))
            .groupby("symbol")["recover"]
            .mean() * 100
    )

    st.bar_chart(symbol_recovery)

    # end of what could be

    numeric_cols = df_results.select_dtypes(include=["float", "int"]).columns

    selected = st.dataframe(
        df_results.style.format({col: "{:.2f}" for col in numeric_cols}),
        width="stretch",
        hide_index=True,
        on_select="rerun"
    )

    if selected and "selection" in selected and selected["selection"]["rows"]:
        idx = selected["selection"]["rows"][0]
        row = df_results.iloc[idx]

        st.subheader(f"Trade {row['trade_id']} — {row['symbol']} — {row['signal']}")
        st.write(row)

        trade = trades[trades["position_id"] == row["trade_id"]].iloc[0]
        symbol = trade["symbol"]

        if symbol in price_data:
            fig = plot_trade_path(trade, price_data[symbol])
            st.pyplot(fig)
        else:
            st.warning("No price data for this symbol")
