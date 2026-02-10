import plotly.express as px


def pattern_frequency_chart(pattern_counts):
    fig = px.bar(
        x=pattern_counts.index,
        y=pattern_counts.values,
        title="Pattern Frequency",
        labels={"x": "Pattern", "y": "Count"}
    )
    return fig


def signal_distribution_chart(df):
    grouped = df.groupby("symbol")[["long_sig", "short_sig"]].sum().reset_index()
    fig = px.bar(
        grouped,
        x="symbol",
        y=["long_sig", "short_sig"],
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
