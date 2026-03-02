def count_patterns(df):
    cols = ['bullish_engulfing', 'bearish_engulfing', 'hammer',
       'shooting_star', 'morning_star', 'evening_star', 'bullish_pin_bar',
       'bearish_pin_bar', 'bullish_three_bar_reversal',
       'bearish_three_bar_reversal', 'bullish_breakout_bar',
       'bearish_breakout_bar', 'bullish_inside_bar', 'bearish_inside_bar',
       'doji', 'outside_bar',]
    return df[cols].sum().sort_values(ascending=False)


def signal_stats(df):
    return df.groupby("symbol")[["long_sig", "short_sig"]].sum()
