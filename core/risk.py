import MetaTrader5 as mt5

from core.logger import setup_logger


def calc_lot_size(symbol: str, balance: float, risk_per_trade: float, entry: float, sl: float) -> float:
    logger = setup_logger()

    stop_points = get_stop_distance_points(entry, sl)
    if stop_points <= 0:
        logger.error(f"{symbol} | Invalid stop distance: {stop_points}")
        return 0.0

    point_value = get_point_value(symbol)
    if point_value <= 0:
        logger.error(f"{symbol} | Invalid point_value={point_value}")
        return 0.0

    risk_amount = balance * risk_per_trade
    risk_per_lot = stop_points * point_value

    if risk_per_lot <= 0:
        logger.error(f"{symbol} | Invalid risk_per_lot={risk_per_lot}")
        return 0.0

    raw_lots = risk_amount / risk_per_lot

    # Safety cap: never allow more than 1 lot on indices/energies/metals
    asset = get_asset_class(symbol)
    if asset in ["index", "energy", "metal"] and raw_lots > 1:
        logger.warning(f"{symbol} | Lot size capped from {raw_lots} to 1.0")
        raw_lots = 1.0
    if asset == "forex" and raw_lots > 0.1:
        logger.warning(f"{symbol} | Forex lot size capped from {raw_lots} to 0.5")
        raw_lots = 0.1

    normalized = normalize_lot(symbol, raw_lots)
    return normalized



def get_point_value(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info failed for {symbol}")

    # MT5 gives correct tick_value and tick_size for all assets
    tick_value = info.trade_tick_value
    tick_size = info.trade_tick_size

    # point = 1 full price unit (not pip)
    point_value = tick_value / tick_size
    return point_value



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


def get_asset_class(symbol: str) -> str:
    symbol = symbol.upper()

    if any(x in symbol for x in ["USD", "JPY", "EUR", "GBP", "AUD", "NZD", "CAD", "CHF"]):
        return "forex"

    if any(x in symbol for x in ["GERMANY", "JP225", "SP500", "NAS", "DOW"]):
        return "index"

    if any(x in symbol for x in ["OIL", "CRUDE", "BRENT", "NGAS"]):
        return "energy"

    if any(x in symbol for x in ["GOLD", "XAU", "SILVER", "XAG", "COPPER"]):
        return "metal"

    return "other"


def get_stop_distance_points(entry: float, sl: float) -> float:
    return abs(entry - sl)
