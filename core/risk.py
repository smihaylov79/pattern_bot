import MetaTrader5 as mt5

from core.logger import setup_logger


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


def can_execute(symbol, settings):
    logger = setup_logger()
    equity_limit = settings['trading']['equity_limit']
    positions_limit = settings['trading']['max_open_trades']
    # === MARGIN USAGE PROTECTION ===
    acc = mt5.account_info()
    equity = acc.equity
    margin = acc.margin

    max_margin_allowed = equity * equity_limit

    if margin > max_margin_allowed:
        logger.warning(
            f"{symbol} | Margin protection active: "
            f"margin={margin:.2f} > allowed={max_margin_allowed:.2f}. "
            f"No new trades will be opened."
        )
        return False

    # === MAX OPEN TRADES CHECK ===
    positions = mt5.positions_get()
    if positions and len(positions) >= positions_limit:
        logger.warning(
            f"{symbol} | Max open trades reached ({len(positions)}). "
            f"No new trades will be opened."
        )
        return False

    return True
