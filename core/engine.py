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
from scalp_reversal.scalp_reversal_bot import ScalperBot


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
        self.max_profit = {}
        self.max_price = {}  # for BUY positions
        self.min_price = {}  # for SELL positions

        init_db()

        if settings["trading"].get("scalper_bot_active", False):
            self.scalper = ScalperBot(symbol="[SP500]", timeframe="M5", atr_period=14, body_threshold=0.5, magic=999001,
                                      comment="scalper_bot")
        else:
            self.scalper = None

    def run(self):
        print("Bot started...")

        while True:
            for symbol in self.symbols:
                try:
                    self.process_symbol(symbol)
                except Exception as e:
                    print(f"Error processing {symbol}: {e}")

            if self.scalper:
                self.scalper.process()

            if self.settings['trading']['live_monitoring']:
                self.monitor_open_positions()
            self.wait_until_next_candle()

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

        if not positions:
            return

        for pos in positions:
            try:
                self.evaluate_position_health(pos)
            except Exception as e:
                print(f"Error evaluating position {pos.ticket}: {e}")

    def evaluate_position_health(self, pos):
        symbol = pos.symbol
        ticket = pos.ticket
        current_profit = pos.profit

        price = mt5.symbol_info_tick(symbol).bid if pos.type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(
            symbol).ask

        # Track favorable price movement
        if pos.type == mt5.ORDER_TYPE_BUY:
            self.max_price[ticket] = max(self.max_price.get(ticket, price), price)
        else:
            self.min_price[ticket] = min(self.min_price.get(ticket, price), price)

        # Track max profit
        if ticket not in self.max_profit:
            self.max_profit[ticket] = current_profit
        else:
            self.max_profit[ticket] = max(self.max_profit[ticket], current_profit)

        # RULE 1: Profit decay
        if self.should_exit_profit_decay(ticket, current_profit):
            print(f"[EXIT] Profit decay triggered for {symbol} #{ticket}")
            self.close_position(ticket, "profit")
            return

        # RULE 2: Structure invalidation
        if self.should_exit_structure(symbol, pos):
            print(f"[EXIT] Structure break for {symbol} #{ticket}")
            self.close_position(ticket, "structure")
            return

        # RULE 3: Time decay
        # if self.should_exit_time_decay(pos):
        #     print(f"[EXIT] Time decay for {symbol} #{ticket}")
        #     self.close_position(ticket, "time")
        #     return

        # RULE 4: ATR trailing stop
        if self.should_exit_atr_trail(symbol, pos):
            print(f"[EXIT] ATR trailing stop for {symbol} #{ticket}")
            self.close_position(ticket, "atr_trail")
            return

    def should_exit_profit_decay(self, ticket, current_profit):
        max_profit = self.max_profit.get(ticket, current_profit)

        # Update max profit
        self.max_profit[ticket] = max(max_profit, current_profit)

        # Only apply if trade was profitable at some point
        if max_profit <= 0:
            return False

        # NEW: require minimum profit before decay logic activates
        min_profit = self.settings['monitoring']['min_profit_for_decay']
        if max_profit < min_profit:
            return False

        # Compute decay ratio
        decay_ratio = current_profit / max_profit

        threshold = self.settings['monitoring']['profit_decay_threshold']

        return decay_ratio < threshold

    def should_exit_structure(self, symbol, pos):
        try:
            df = get_bars(symbol, self.timeframe, 50)
        except:
            return False

        if len(df) < 10:
            return False

        # BUY → exit if price breaks last higher low
        if pos.type == mt5.ORDER_TYPE_BUY:
            last_higher_low = df['low'].rolling(5).min().iloc[-2]
            return df['close'].iloc[-1] < last_higher_low

        # SELL → exit if price breaks last lower high
        if pos.type == mt5.ORDER_TYPE_SELL:
            last_lower_high = df['high'].rolling(5).max().iloc[-2]
            return df['close'].iloc[-1] > last_lower_high

        return False

    def should_exit_time_decay(self, pos):
        now = time.time()
        open_time = pos.time
        elapsed = now - open_time

        max_duration = self.settings['monitoring']['max_trade_duration_sec']

        return elapsed > max_duration

    def should_exit_atr_trail(self, symbol, pos):
        atr = calculate_atr(symbol, timeframe=self.timeframe, period=14)
        if atr is None:
            return False

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False

        current_price = tick.bid if pos.type == mt5.ORDER_TYPE_SELL else tick.ask
        mult = self.settings['monitoring']['atr_multiplier']
        ticket = pos.ticket

        # BUY logic
        if pos.type == mt5.ORDER_TYPE_BUY:
            highest = self.max_price.get(ticket, pos.price_open)

            # Only activate trailing stop after price has moved meaningfully
            if highest - pos.price_open < atr * mult:
                return False

            trail_price = highest - atr * mult
            return current_price < trail_price

        # SELL logic
        if pos.type == mt5.ORDER_TYPE_SELL:
            lowest = self.min_price.get(ticket, pos.price_open)

            if pos.price_open - lowest < atr * mult:
                return False

            trail_price = lowest + atr * mult
            return current_price > trail_price

        return False

    def close_position(self, ticket, comment):
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return

        pos = pos[0]
        symbol = pos.symbol
        volume = pos.volume

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "magic": 999,
            "comment": comment
        }

        result = mt5.order_send(request)

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"Closed position #{ticket} on {symbol}")

            # 🔥 CLEANUP: remove max profit tracking for this ticket
            if ticket in self.max_profit:
                del self.max_profit[ticket]
            if ticket in self.max_price:
                del self.max_price[ticket]
            if ticket in self.min_price:
                del self.min_price[ticket]


        else:
            print(f"Failed to close position #{ticket}: {result}")

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


