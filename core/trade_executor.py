import MetaTrader5 as mt5
from core.execution import send_order
from core.patterns import calculate_atr
from core.risk import calc_lot_size, can_execute


def execute_trade(symbol, direction, df, last, settings, magic=123456):
    """
    Shared trade execution logic used by:
    - BotEngine (normal strategy)
    - NYOpenBot (NY-open strategy)
    """

    if not can_execute(symbol, settings):
        return 0, 0, 0

    tick = mt5.symbol_info_tick(symbol)
    entry = tick.ask if direction == "buy" else tick.bid
    info = mt5.symbol_info(symbol)
    point = info.point

    # --- HTF ATR for structural volatility ---
    atr_htf = calculate_atr(symbol, timeframe=settings["trading"]["ltf"], period=14)
    if atr_htf is None:
        return 0, 0, 0

    # minimum SL distance in price terms (hybrid: broker + ATR)
    min_stop_points = info.trade_stops_level * point
    min_sl_dist = max(min_stop_points, 0.5 * atr_htf)

    demand_zones = last["demand_zones"]
    supply_zones = last["supply_zones"]

    # ---------- LONG ----------
    if direction == "buy":
        if last["in_demand"] and len(demand_zones) > 0:
            nearest = min(demand_zones, key=lambda z: abs(entry - z[1]))
            zone_low = nearest[0]
            sl_zone = zone_low - 2 * point
        else:
            sl_zone = df["low"].tail(10).min()

        sl_raw = min(entry - min_sl_dist, sl_zone)
        sl = min(sl_raw, entry - min_sl_dist)

        if len(supply_zones) > 0:
            above = [z for z in supply_zones if z[0] > entry]
            if len(above) > 0:
                next_supply = min(above, key=lambda z: z[0])
                tp_zone = next_supply[0]
            else:
                tp_zone = entry + 2 * (entry - sl)
        else:
            tp_zone = entry + 2 * (entry - sl)

        tp_min = entry + 1.5 * atr_htf
        tp = max(tp_zone, tp_min)

    # ---------- SHORT ----------
    else:
        if last["in_supply"] and len(supply_zones) > 0:
            nearest = min(supply_zones, key=lambda z: abs(entry - z[0]))
            zone_high = nearest[1]
            sl_zone = zone_high + 2 * point
        else:
            sl_zone = df["high"].tail(10).max()

        sl_raw = max(entry + min_sl_dist, sl_zone)
        sl = max(sl_raw, entry + min_sl_dist)

        if len(demand_zones) > 0:
            below = [z for z in demand_zones if z[1] < entry]
            if len(below) > 0:
                next_demand = max(below, key=lambda z: z[1])
                tp_zone = next_demand[1]
            else:
                tp_zone = entry - 2 * (sl - entry)
        else:
            tp_zone = entry - 2 * (sl - entry)

        tp_min = entry - 1.5 * atr_htf
        tp = min(tp_zone, tp_min)

    balance = mt5.account_info().equity
    risk_per_trade = settings["trading"]["risk_per_trade"]

    lots = calc_lot_size(symbol, balance, risk_per_trade, entry, sl)
    result = send_order(symbol, direction, lots, sl, tp, last, magic)

    return lots, sl, tp, result
