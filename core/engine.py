import time
from datetime import datetime
from core.data_feed import get_bars
from core.candles import add_candle_metrics
from core.patterns import calculate_atr
from core.signals import generate_signals
from core.execution import send_order
from core.risk import calc_lot_size, can_execute
import MetaTrader5 as mt5
from core.logger import setup_logger
from core.db import get_connection, init_db


class BotEngine:
    def __init__(self, symbols, timeframe, htf, ltf, bars, settings, sleep_time=10):
        self.symbols = symbols
        self.timeframe = timeframe
        self.htf = htf
        self.ltf = ltf
        self.bars = bars
        self.settings = settings
        self.sleep_time = sleep_time
        self.last_timestamp = {s: None for s in symbols}
        self.logger = setup_logger()
        init_db()

    def run(self):
        print("Bot started...")

        while True:
            for symbol in self.symbols:
                try:
                    self.process_symbol(symbol)
                except Exception as e:
                    print(f"Error processing {symbol}: {e}")

            self.monitor_open_positions()
            time.sleep(self.sleep_time)

    def monitor_open_positions(self):
        positions = mt5.positions_get()

        if positions is None or len(positions) == 0:
            return

        for pos in positions:
            try:
                self.manage_position(pos)
            except Exception as e:
                print(f"Error managing position {pos.ticket}: {e}")

    def manage_position(self, pos):
        symbol = pos.symbol
        direction = "buy" if pos.type == 0 else "sell"
        entry = pos.price_open
        volume = pos.volume
        ticket = pos.ticket

        info = mt5.symbol_info(symbol)
        point = info.point
        min_stop = info.trade_stops_level * point

        # current price
        tick = mt5.symbol_info_tick(symbol)
        current = tick.bid if direction == "sell" else tick.ask

        # --- Compute MFE/MAE correctly ---
        if direction == "buy":
            mfe = current - entry
            mae = current - entry  # current loss (not true MAE, but safe fallback)
        else:
            mfe = entry - current
            mae = entry - current

        # thresholds based on symbol volatility
        atr = calculate_atr(symbol, timeframe=self.htf, period=14)
        break_even_trigger = max(1 * min_stop, 0.5 * atr)
        reversal_trigger = max(2 * min_stop, 1.0 * atr)
        hard_loss_trigger = -max(2 * min_stop, 1.0 * atr)

        # 1. Break-even logic
        if mfe > break_even_trigger and pos.sl < entry:
            if self.detect_reversal(symbol, direction):
                new_sl = entry + 1 * point if direction == "buy" else entry - 1 * point
                self.modify_sl_safe(ticket, symbol, new_sl, current, min_stop, direction, pos.tp)

        # 2. Reversal exit
        if mfe > reversal_trigger and self.detect_reversal(symbol, direction):
            self.close_position(ticket, symbol, direction, volume, reason="reversal")
            return

        # 3. Hard loss exit
        if mae < hard_loss_trigger:
            self.close_position(ticket, symbol, direction, volume, reason="hard_loss")
            return

    def detect_reversal(self, symbol, direction):
        """
        Detects a reversal against the current position using the last few candles.
        Uses the same get_bars() function as the signal engine for consistency.
        """

        # Get last 5 M1 candles (or use your LTF timeframe if you prefer)
        try:
            df = get_bars(symbol, self.ltf, 5)
        except Exception as e:
            print(f"[MANAGER] Failed to get bars for reversal detection: {e}")
            return False

        if df is None or len(df) < 3:
            return False

        # Extract last 3 candles
        c1 = df.iloc[-1]  # current candle
        c2 = df.iloc[-2]  # previous candle
        c3 = df.iloc[-3]  # earlier candle

        # -----------------------------
        # 1. Engulfing reversal pattern
        # -----------------------------
        if direction == "buy":
            # Bearish engulfing
            if (
                    c1["open"] > c1["close"] and
                    c1["open"] >= c2["close"] and
                    c1["close"] <= c2["open"]
            ):
                return True
        else:
            # Bullish engulfing
            if (
                    c1["close"] > c1["open"] and
                    c1["close"] >= c2["open"] and
                    c1["open"] <= c2["close"]
            ):
                return True

        # -----------------------------
        # 2. Break of last swing
        # -----------------------------
        swing_low = min(c2["low"], c3["low"])
        swing_high = max(c2["high"], c3["high"])

        if direction == "buy" and c1["close"] < swing_low:
            return True

        if direction == "sell" and c1["close"] > swing_high:
            return True

        # -----------------------------
        # 3. Momentum loss (2 opposite candles growing)
        # -----------------------------
        body1 = abs(c1["close"] - c1["open"])
        body2 = abs(c2["close"] - c2["open"])

        if direction == "buy":
            if (
                    c1["close"] < c1["open"] and
                    c2["close"] < c2["open"] and
                    body1 > body2
            ):
                return True
        else:
            if (
                    c1["close"] > c1["open"] and
                    c2["close"] > c2["open"] and
                    body1 > body2
            ):
                return True

        return False

    def close_position(self, ticket, symbol, direction, volume, reason="manager_exit"):
        opposite = mt5.ORDER_TYPE_SELL if direction == "buy" else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).bid if direction == "buy" else mt5.symbol_info_tick(symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": opposite,
            "position": ticket,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": reason,
        }

        result = mt5.order_send(request)
        print(f"[MANAGER] Close result: {result.retcode} | reason={reason}")

    def modify_sl_safe(self, ticket, symbol, new_sl, current_price, min_stop, direction, current_tp):

        # enforce minimum stop distance
        if direction == "buy":
            allowed_sl = current_price - min_stop
            new_sl = min(new_sl, allowed_sl)
        else:
            allowed_sl = current_price + min_stop
            new_sl = max(new_sl, allowed_sl)

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": current_tp,
        }

        result = mt5.order_send(request)
        print(f"[MANAGER] SL modify result: {result.retcode}")

    def process_symbol(self, symbol):

        df_ltf = get_bars(symbol, self.timeframe, self.bars)
        df_htf = get_bars(symbol, self.htf, self.bars)

        df_ltf = add_candle_metrics(df_ltf)
        df_htf = add_candle_metrics(df_htf)

        last_time = df_ltf.index[-1]
        if self.last_timestamp[symbol] == last_time:
            return
        self.last_timestamp[symbol] = last_time

        df_signals = generate_signals(df_ltf, df_htf)
        last = df_signals.iloc[-1]


        # default execution values
        action = "NONE"
        lots = 0
        sl = 0
        tp = 0
        result = None

        # check for signals
        if last["long_signal"]:
            action = "BUY"
            lots, sl, tp, result = self.execute_trade(symbol, "buy", df_ltf, last)

        elif last["short_signal"]:
            action = "SELL"
            lots, sl, tp, result = self.execute_trade(symbol, "sell", df_ltf, last)

        # unified log entry
        self.logger.info(
            f"{symbol} | {self.timeframe} | candle={last_time} | "
            f"O={df_ltf['open'].iloc[-1]} H={df_ltf['high'].iloc[-1]} "
            f"L={df_ltf['low'].iloc[-1]} C={df_ltf['close'].iloc[-1]} | "
            f"bull_eng={last['bullish_engulfing']} | "
            f"bear_eng={last['bearish_engulfing']} | "
            f"hammer={last['hammer']} | "
            f"shooting_star={last['shooting_star']} | "
            f"inside_bar={last['inside_bar']} | "
            f"near_sr={last['near_sr']} | "
            f"long_sig={last['long_signal']} | "
            f"short_sig={last['short_signal']} | "
            f"action={action} | lots={lots} | sl={sl} | tp={tp}"
        )
        self.log_to_db(symbol, last, df_ltf, action, lots, sl, tp, result)

    def log_to_db(self, symbol, last, df_ltf, action, lots, sl, tp, result):
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            INSERT INTO logs (
                timestamp, symbol, timeframe, candle_time,
                open, high, low, close,
                bull_eng, bear_eng, hammer, shooting_star, inside_bar,
                near_sr, long_sig, short_sig,
                action, lots, sl, tp,
                pin_bar, doji, morning_star, evening_star,
                three_bar_reversal, breakout_bar, outside_bar,
                trigger_pattern, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            symbol,
            self.timeframe,
            df_ltf.index[-1].isoformat(),

            df_ltf["open"].iloc[-1],
            df_ltf["high"].iloc[-1],
            df_ltf["low"].iloc[-1],
            df_ltf["close"].iloc[-1],

            int(last["bullish_engulfing"]),
            int(last["bearish_engulfing"]),
            int(last["hammer"]),
            int(last["shooting_star"]),
            int(last["inside_bar"]),

            int(last["near_sr"]),
            int(last["long_signal"]),
            int(last["short_signal"]),

            action,
            lots,
            sl,
            tp,

            int(last["pin_bar"]),
            int(last["doji"]),
            int(last["morning_star"]),
            int(last["evening_star"]),
            int(last["three_bar_reversal"]),
            int(last["breakout_bar"]),
            int(last["outside_bar"]),

            last["trigger_pattern"],
            result
        ))

        conn.commit()
        conn.close()

    def execute_trade(self, symbol, direction, df, last):
        if not can_execute(symbol, self.settings):
            return 0, 0, 0
        # entry = df["close"].iloc[-1]
        tick = mt5.symbol_info_tick(symbol)
        entry = tick.ask if direction == "buy" else tick.bid
        point = mt5.symbol_info(symbol).point

        demand_zones = last["demand_zones"]
        supply_zones = last["supply_zones"]

        # --- LONG TRADE ---
        if direction == "buy":

            # 1. SL = below demand zone
            if last["in_demand"] and len(demand_zones) > 0:
                # find the nearest demand zone
                nearest = min(demand_zones, key=lambda z: abs(entry - z[1]))
                zone_low = nearest[0]
                sl = zone_low - 2 * point  # small buffer
            else:
                # fallback: recent swing low
                sl = df["low"].tail(10).min()

            # 2. TP = next supply zone
            if len(supply_zones) > 0:
                # find supply zone above price
                above = [z for z in supply_zones if z[0] > entry]
                if len(above) > 0:
                    next_supply = min(above, key=lambda z: z[0])
                    tp = next_supply[0]
                else:
                    # fallback: 2R
                    tp = entry + 2 * (entry - sl)
            else:
                tp = entry + 2 * (entry - sl)

        # --- SHORT TRADE ---
        else:

            # 1. SL = above supply zone
            if last["in_supply"] and len(supply_zones) > 0:
                nearest = min(supply_zones, key=lambda z: abs(entry - z[0]))
                zone_high = nearest[1]
                sl = zone_high + 2 * point
            else:
                sl = df["high"].tail(10).max()

            # 2. TP = next demand zone
            if len(demand_zones) > 0:
                below = [z for z in demand_zones if z[1] < entry]
                if len(below) > 0:
                    next_demand = max(below, key=lambda z: z[1])
                    tp = next_demand[1]
                else:
                    tp = entry - 2 * (sl - entry)
            else:
                tp = entry - 2 * (sl - entry)

        # risk-based lot size
        balance = mt5.account_info().equity
        risk_per_trade = self.settings["trading"]["risk_per_trade"]

        lots = calc_lot_size(symbol, balance, risk_per_trade, entry, sl)

        result = send_order(symbol, direction, lots, sl, tp, last)
        return lots, sl, tp, result.comment


