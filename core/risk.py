import MetaTrader5 as mt5

from core.logger import setup_logger


# def calc_lot_size(symbol: str, balance: float, risk_per_trade: float, entry: float, sl: float) -> float:
#     logger = setup_logger()
#
#     stop_points = get_stop_distance_points(entry, sl)
#     if stop_points <= 0:
#         logger.error(f"{symbol} | Invalid stop distance: {stop_points}")
#         return 0.0
#
#     point_value = get_point_value(symbol)
#     if point_value <= 0:
#         logger.error(f"{symbol} | Invalid point_value={point_value}")
#         return 0.0
#
#     risk_amount = balance * risk_per_trade
#     risk_per_lot = stop_points * point_value
#
#     if risk_per_lot <= 0:
#         logger.error(f"{symbol} | Invalid risk_per_lot={risk_per_lot}")
#         return 0.0
#
#     raw_lots = risk_amount / risk_per_lot
#
#     # Safety cap: never allow more than 1 lot on indices/energies/metals
#     asset = get_asset_class(symbol)
#     if asset in ["index", "energy", "metal"] and raw_lots > 1:
#         logger.warning(f"{symbol} | Lot size capped from {raw_lots} to 1.0")
#         raw_lots = 1.0
#     if asset == "forex" and raw_lots > 0.1:
#         logger.warning(f"{symbol} | Forex lot size capped from {raw_lots} to 0.5")
#         raw_lots = 0.1
#
#     normalized = normalize_lot(symbol, raw_lots)
#     return normalized

import MetaTrader5 as mt5


def calc_lot_size(symbol: str,
                  balance: float,
                  risk_perc: float,
                  entry_price: float,
                  sl_price: float) -> float:
    """
    Symbol-aware lot size:
    - risk_perc is in PERCENT (e.g. 0.05 = 0.05%)
    - Uses tick_value and tick_size from MT5
    - Respects volume_min, volume_max, volume_step
    """

    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol info not found for {symbol}")

    # --- Basic symbol parameters ---
    tick_size = info.point          # price step
    tick_value = info.trade_tick_value  # money per tick per 1.0 lot
    vol_min = info.volume_min
    vol_max = info.volume_max
    vol_step = info.volume_step

    # --- Risk in account currency ---
    risk_amount = balance * (risk_perc / 100.0)

    # --- SL distance in price and ticks ---
    sl_dist_price = abs(entry_price - sl_price)
    if sl_dist_price <= 0:
        # safety fallback: 5 ticks
        sl_dist_price = 5 * tick_size

    sl_ticks = sl_dist_price / tick_size

    # --- Money risk per 1.0 lot for this SL distance ---
    # (ticks * tick_value_per_tick_per_lot)
    risk_per_lot = sl_ticks * tick_value

    if risk_per_lot <= 0:
        # avoid division by zero / nonsense
        return vol_min

    # --- Raw lot size ---
    lots = risk_amount / risk_per_lot

    # --- Clamp to broker limits ---
    # round to nearest volume_step
    steps = round(lots / vol_step)
    lots = steps * vol_step

    if lots < vol_min:
        lots = vol_min
    if lots > vol_max:
        lots = vol_max

    return lots



def get_point_value(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    if info is None:
        return 0.0

    if info.trade_tick_size == 0:
        return 0.0

    return info.trade_tick_value / info.trade_tick_size

#
# def normalize_lot(symbol: str, lots: float) -> float:
#     info = mt5.symbol_info(symbol)
#     if info is None:
#         raise RuntimeError(f"symbol_info failed for {symbol}")
#
#     min_lot = info.volume_min
#     max_lot = info.volume_max
#     step = info.volume_step
#
#     # clamp to broker limits
#     lots = max(min_lot, min(lots, max_lot))
#
#     # determine number of decimals required by step
#     # e.g. 0.01 -> 2 decimals, 0.001 -> 3 decimals
#     step_str = f"{step:.10f}".rstrip("0")
#     if "." in step_str:
#         decimals = len(step_str.split(".")[1])
#     else:
#         decimals = 0
#
#     # round to nearest step
#     steps = round(lots / step)
#     normalized = steps * step
#
#     # final rounding to correct decimals
#     normalized = round(normalized, decimals)
#
#     return normalized


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
#
#
# def get_asset_class(symbol: str) -> str:
#     info = mt5.symbol_info(symbol)
#     if info is None:
#         return "other"
#
#     path = info.path.lower()
#
#     if "forex" in path:
#         return "forex"
#     if "indices" in path or "index" in path:
#         return "index"
#     if "metal" in path:
#         return "metal"
#     if "energies" in path or "oil" in path or "gas" in path:
#         return "energy"
#     if "crypto" in path:
#         return "crypto"
#     if "stock" in path:
#         return "stock"
#     if "agricultures" in path:
#         return "agricultures"
#
#     return "other"
#
#
# def get_stop_distance_points(symbol: str, entry: float, sl: float) -> float:
#     info = mt5.symbol_info(symbol)
#     if info is None:
#         return 0.0
#
#     point = info.point
#     return abs(entry - sl) / point
#
