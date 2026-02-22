import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"


def load_settings():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def init_mt5():
    settings = load_settings()["mt5"]
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    if settings["login"]:
        authorized = mt5.login(
            settings["login"],
            password=settings["password"],
            server=settings["server"]
        )
        if not authorized:
            raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")
    print("MT5 initialized")


def shutdown_mt5():
    mt5.shutdown()


def get_bars(symbol: str, timeframe: str, n_bars: int) -> pd.DataFrame:
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    tf = tf_map[timeframe]

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, n_bars + 1)
    if rates is None:
        raise RuntimeError(f"Failed to get rates for {symbol}: {mt5.last_error()}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.rename(columns={
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "tick_volume": "volume"
    })
    df = df[["time", "open", "high", "low", "close", "volume"]]
    df.set_index("time", inplace=True)
    df = df.iloc[:-1]

    # NEW: guard against empty or tiny DataFrame
    if df.empty or len(df) < 5:
        raise RuntimeError(f"Not enough bars for {symbol} {timeframe}. Got {len(df)} rows.")

    return df


def timeframe_to_seconds(tf: str) -> int:
    mapping = {
        "M1": 60,
        "M5": 300,
        "M15": 900,
        "M30": 1800,
        "H1": 3600,
        "H4": 14400,
        "D1": 86400,
    }
    return mapping[tf]
