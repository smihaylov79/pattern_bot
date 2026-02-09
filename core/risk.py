import MetaTrader5 as mt5


def calc_lot_size(symbol: str, balance: float, risk_per_trade: float, stop_pips: float) -> float:
    if stop_pips <= 0:
        return 0.0

    pip_value = get_pip_value(symbol)
    risk_amount = balance * risk_per_trade

    raw_lots = risk_amount / (stop_pips * pip_value)
    normalized_lots = normalize_lot(symbol, raw_lots)

    return normalized_lots



def get_pip_value(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info failed for {symbol}")

    tick_value = info.trade_tick_value
    tick_size = info.trade_tick_size

    # pip = 10 * tick for most FX pairs
    pip_size = tick_size * 10

    pip_value = tick_value * (pip_size / tick_size)
    return pip_value


def normalize_lot(symbol: str, lots: float) -> float:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info failed for {symbol}")

    min_lot = info.volume_min
    max_lot = info.volume_max
    step = info.volume_step

    # clamp
    lots = max(min_lot, min(lots, max_lot))

    # round to nearest step
    steps = round(lots / step)
    normalized = steps * step

    return round(normalized, 3)
