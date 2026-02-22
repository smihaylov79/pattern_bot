import time
from datetime import datetime, timedelta
from core.data_feed import get_bars, timeframe_to_seconds
from core.candles import add_candle_metrics
from core.patterns import calculate_atr
from core.signals import generate_signals
from core.execution import send_order
from core.risk import calc_lot_size, can_execute
import MetaTrader5 as mt5
from core.logger import setup_logger
from core.db import get_connection, init_db



class BotEngine:
    def __init__(self, symbols, symbol_settings, timeframe, htf, ltf, bars, settings, sleep_time=10):
        self.symbols = symbols
        self.symbol_settings = symbol_settings
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
            if self.settings['trading']['live_monitoring']:
                self.monitor_open_positions()
            self.wait_until_next_candle()
            # time.sleep(self.sleep_time)

    def wait_until_next_candle(self):
        now = datetime.utcnow()
        tf_seconds = timeframe_to_seconds(self.timeframe)

        # Align to the next candle boundary
        current_epoch = int(now.timestamp())
        next_close_epoch = ((current_epoch // tf_seconds) + 1) * tf_seconds
        next_close = datetime.utcfromtimestamp(next_close_epoch)

        sleep_time = (next_close - now).total_seconds()
        time.sleep(max(1.0, sleep_time))

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

        df_signals = generate_signals(df_ltf, df_htf, symbol, self.symbol_settings, self.settings)
        last = df_signals.iloc[-1]


        # default execution values
        # action = "NONE"
        # lots = 0
        # sl = 0
        # tp = 0
        # result = None

        # check for signals
        if last["long_signal"]:
            action = "BUY"
            lots, sl, tp, result = self.execute_trade(symbol, "buy", df_ltf, last)

        elif last["short_signal"]:
            action = "SELL"
            lots, sl, tp, result = self.execute_trade(symbol, "sell", df_ltf, last)
        else:
            action = "NONE"
            lots = sl = tp = 0
            result = None

        if result is None:
            result_text = "NO_TRADE"
        else:
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                result_text = f"EXECUTED: order={result.order}"
            else:
                result_text = f"FAILED: retcode={result.retcode}, comment={result.comment}"

        self.log_to_db(symbol, last, df_ltf, action, lots, sl, tp, result_text)

    def log_to_db(self, symbol, last, df_ltf, action, lots, sl, tp, result):
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            INSERT INTO logs (
                timestamp, symbol, timeframe, candle_time,
                open, high, low, close,

                bullish_engulfing, bearish_engulfing,
                hammer, shooting_star,
                morning_star, evening_star,

                bullish_pin_bar, bearish_pin_bar,
                bullish_three_bar_reversal, bearish_three_bar_reversal,
                bullish_breakout_bar, bearish_breakout_bar,
                bullish_inside_bar, bearish_inside_bar,

                doji, outside_bar,

                near_sr, in_demand, in_supply, vol_ok,

                bullish_count, bearish_count,
                recent_bullish, recent_bearish,

                bias_long, bias_short,
                htf_ma_fast, htf_ma_slow, htf_ma_fast_slope,

                long_signal, short_signal,
                trigger_pattern,

                action, lots, sl, tp, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            int(last["morning_star"]),
            int(last["evening_star"]),

            int(last["bullish_pin_bar"]),
            int(last["bearish_pin_bar"]),
            int(last["bullish_three_bar_reversal"]),
            int(last["bearish_three_bar_reversal"]),
            int(last["bullish_breakout_bar"]),
            int(last["bearish_breakout_bar"]),
            int(last["bullish_inside_bar"]),
            int(last["bearish_inside_bar"]),

            int(last["doji"]),
            int(last["outside_bar"]),

            int(last["near_sr"]),
            int(last["in_demand"]),
            int(last["in_supply"]),
            int(last["vol_ok"]),

            int(last["bullish_count"]),
            int(last["bearish_count"]),
            int(last["recent_bullish"]),
            int(last["recent_bearish"]),

            int(last["bias_long"]),
            int(last["bias_short"]),
            float(last["htf_ma_fast"]),
            float(last["htf_ma_slow"]),
            float(last["htf_ma_fast_slope"]),

            int(last["long_signal"]),
            int(last["short_signal"]),
            last["trigger_pattern"],

            action,
            lots,
            sl,
            tp,
            result
        ))

        conn.commit()
        conn.close()

    def execute_trade(self, symbol, direction, df, last):
        if not can_execute(symbol, self.settings):
            return 0, 0, 0

        tick = mt5.symbol_info_tick(symbol)
        entry = tick.ask if direction == "buy" else tick.bid
        info = mt5.symbol_info(symbol)
        point = info.point

        # --- HTF ATR for structural volatility ---

        atr_htf = calculate_atr(symbol, timeframe=self.ltf, period=14)
        if atr_htf is None:
            return 0, 0, 0

        # minimum SL distance in price terms (hybrid: broker + ATR)
        min_stop_points = info.trade_stops_level * point
        min_sl_dist = max(min_stop_points, 0.5 * atr_htf)  # 0.5 ATR floor

        demand_zones = last["demand_zones"]
        supply_zones = last["supply_zones"]

        # ---------- LONG ----------
        if direction == "buy":
            # 1) Zone-based SL candidate
            if last["in_demand"] and len(demand_zones) > 0:
                nearest = min(demand_zones, key=lambda z: abs(entry - z[1]))
                zone_low = nearest[0]
                sl_zone = zone_low - 2 * point
            else:
                sl_zone = df["low"].tail(10).min()

            # 2) Enforce ATR/broker minimum distance
            sl_raw = min(entry - min_sl_dist, sl_zone)
            sl = min(sl_raw, entry - min_sl_dist)  # ensure at least min_sl_dist away

            # 3) TP: next supply zone or ATR-based
            if len(supply_zones) > 0:
                above = [z for z in supply_zones if z[0] > entry]
                if len(above) > 0:
                    next_supply = min(above, key=lambda z: z[0])
                    tp_zone = next_supply[0]
                else:
                    tp_zone = entry + 2 * (entry - sl)
            else:
                tp_zone = entry + 2 * (entry - sl)

            # enforce minimum TP distance: at least 1.5 ATR
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
        risk_per_trade = self.settings["trading"]["risk_per_trade"]

        lots = calc_lot_size(symbol, balance, risk_per_trade, entry, sl)
        result = send_order(symbol, direction, lots, sl, tp, last)

        return lots, sl, tp, result

    # def execute_trade(self, symbol, direction, df, last):
    #     if not can_execute(symbol, self.settings):
    #         return 0, 0, 0
    #     # entry = df["close"].iloc[-1]
    #     tick = mt5.symbol_info_tick(symbol)
    #     entry = tick.ask if direction == "buy" else tick.bid
    #     point = mt5.symbol_info(symbol).point
    #
    #     demand_zones = last["demand_zones"]
    #     supply_zones = last["supply_zones"]
    #
    #     # --- LONG TRADE ---
    #     if direction == "buy":
    #
    #         # 1. SL = below demand zone
    #         if last["in_demand"] and len(demand_zones) > 0:
    #             # find the nearest demand zone
    #             nearest = min(demand_zones, key=lambda z: abs(entry - z[1]))
    #             zone_low = nearest[0]
    #             sl = zone_low - 2 * point  # small buffer
    #         else:
    #             # fallback: recent swing low
    #             sl = df["low"].tail(10).min()
    #
    #         # 2. TP = next supply zone
    #         if len(supply_zones) > 0:
    #             # find supply zone above price
    #             above = [z for z in supply_zones if z[0] > entry]
    #             if len(above) > 0:
    #                 next_supply = min(above, key=lambda z: z[0])
    #                 tp = next_supply[0]
    #             else:
    #                 # fallback: 2R
    #                 tp = entry + 2 * (entry - sl)
    #         else:
    #             tp = entry + 2 * (entry - sl)
    #
    #     # --- SHORT TRADE ---
    #     else:
    #
    #         # 1. SL = above supply zone
    #         if last["in_supply"] and len(supply_zones) > 0:
    #             nearest = min(supply_zones, key=lambda z: abs(entry - z[0]))
    #             zone_high = nearest[1]
    #             sl = zone_high + 2 * point
    #         else:
    #             sl = df["high"].tail(10).max()
    #
    #         # 2. TP = next demand zone
    #         if len(demand_zones) > 0:
    #             below = [z for z in demand_zones if z[1] < entry]
    #             if len(below) > 0:
    #                 next_demand = max(below, key=lambda z: z[1])
    #                 tp = next_demand[1]
    #             else:
    #                 tp = entry - 2 * (sl - entry)
    #         else:
    #             tp = entry - 2 * (sl - entry)
    #
    #     # risk-based lot size
    #     balance = mt5.account_info().equity
    #     risk_per_trade = self.settings["trading"]["risk_per_trade"]
    #
    #     lots = calc_lot_size(symbol, balance, risk_per_trade, entry, sl)
    #
    #     send_order(symbol, direction, lots, sl, tp, last)
    #
    #     return lots, sl, tp


