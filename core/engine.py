import time
from datetime import datetime
from core.data_feed import get_bars
from core.candles import add_candle_metrics
from core.signals import generate_signals
from core.execution import send_order
from core.risk import calc_lot_size, can_execute
import MetaTrader5 as mt5
from core.logger import setup_logger
from core.db import get_connection, init_db


class BotEngine:
    def __init__(self, symbols, timeframe, htf, bars, settings, sleep_time=10):
        self.symbols = symbols
        self.timeframe = timeframe
        self.htf = htf
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

            time.sleep(self.sleep_time)

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

        # check for signals
        if last["long_signal"]:
            action = "BUY"
            lots, sl, tp = self.execute_trade(symbol, "buy", df_ltf, last)

        elif last["short_signal"]:
            action = "SELL"
            lots, sl, tp = self.execute_trade(symbol, "sell", df_ltf, last)

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
        self.log_to_db(symbol, last, df_ltf, action, lots, sl, tp)

    def log_to_db(self, symbol, last, df_ltf, action, lots, sl, tp):
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            INSERT INTO logs (
                timestamp, symbol, timeframe, candle_time,
                open, high, low, close,
                bull_eng, bear_eng, hammer, shooting_star, inside_bar,
                near_sr, long_sig, short_sig,
                action, lots, sl, tp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            tp
        ))

        conn.commit()
        conn.close()

    def execute_trade(self, symbol, direction, df, last):
        if not can_execute(symbol, self.settings):
            return
        entry = df["close"].iloc[-1]
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

            stop_pips = (entry - sl) / point

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

            stop_pips = (sl - entry) / point

        # risk-based lot size
        balance = mt5.account_info().balance
        risk = self.settings["trading"]["risk_per_trade"]
        lots = calc_lot_size(symbol, balance, risk, stop_pips)

        send_order(symbol, direction, lots, sl, tp, last)
        return lots, sl, tp


