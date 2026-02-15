import streamlit as st
from loader import load_logs, load_trade_history, load_price_history
from analytics import reconstruct_trades
from layout import (
    render_dashboard,
    render_signal_explorer,
    render_trade_performance,
    render_trade_path_analysis
)

if __name__ == "__main__":
    df_logs = load_logs()
    df_history = load_trade_history()

    df_trades = reconstruct_trades(df_history)

    symbols = df_trades["symbol"].unique()
    price_data = load_price_history(symbols)

    st.title("Pattern Bot Dashboard")

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Session Dashboard",
        "🔍 Signal Explorer",
        "📈 Trade Performance",
        "📈 Trade Path Analysis"
    ])

    with tab1:
        render_dashboard(df_logs)

    with tab2:
        render_signal_explorer(df_logs)

    with tab3:
        render_trade_performance()

    with tab4:
        render_trade_path_analysis(df_trades, price_data)
