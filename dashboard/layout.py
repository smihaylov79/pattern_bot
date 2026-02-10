import streamlit as st
from loader import load_db
from queries import count_patterns, signal_stats
from charts import pattern_frequency_chart, signal_distribution_chart
from analytics import pattern_signal_attribution
from charts import pattern_signal_chart
from analytics import explain_signal_row


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

    if selected and "selection" in selected:
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

