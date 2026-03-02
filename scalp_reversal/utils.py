import pandas as pd
import numpy as np

import MetaTrader5 as mt5
from datetime import datetime

def atr(df: pd.DataFrame, period: int = 14):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean()


def open_scalper_order(symbol, order_type, lots, magic, comment):
    """
    order_type: 'buy' or 'sell'
    """

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"[SCALPER] Symbol not found: {symbol}")
        return None

    if not symbol_info.visible:
        mt5.symbol_select(symbol, True)

    price = mt5.symbol_info_tick(symbol).ask if order_type == "buy" else mt5.symbol_info_tick(symbol).bid
    deviation = 200  # slippage

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": mt5.ORDER_TYPE_BUY if order_type == "buy" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": deviation,
        "magic": magic,
        "comment": comment,
        "type_filling": mt5.ORDER_FILLING_FOK,
        "type_time": mt5.ORDER_TIME_GTC,
    }

    result = mt5.order_send(request)

    if result is None:
        print(f"[SCALPER] order_send() returned None")
        return None

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[SCALPER] Order failed: retcode={result.retcode}")
        return None

    print(f"[SCALPER] Opened {order_type.upper()} {symbol} ticket={result.order}")
    return result.order


def close_scalper_order(ticket):
    position = mt5.positions_get(ticket=ticket)
    if not position:
        print(f"[SCALPER] No open position with ticket {ticket}")
        return False

    pos = position[0]
    symbol = pos.symbol
    volume = pos.volume

    price = mt5.symbol_info_tick(symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask
    deviation = 20

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
        "position": ticket,
        "price": price,
        "deviation": deviation,
        "magic": pos.magic,
        "comment": pos.comment,
        "type_filling": mt5.ORDER_FILLING_FOK,
        "type_time": mt5.ORDER_TIME_GTC,
    }

    result = mt5.order_send(request)

    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[SCALPER] Failed to close ticket {ticket}, retcode={result.retcode}")
        return False

    print(f"[SCALPER] Closed position ticket={ticket}")
    return True
