def count_patterns(df):
    cols = ["bull_eng", "bear_eng", "hammer", "shooting_star", "inside_bar"]
    return df[cols].sum().sort_values(ascending=False)


def signal_stats(df):
    return df.groupby("symbol")[["long_sig", "short_sig"]].sum()
