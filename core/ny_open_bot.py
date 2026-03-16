from datetime import datetime

from core.db import log_to_db
import MetaTrader5 as mt5


class NYOpenBot:
    def __init__(self, settings, ny_controller):
        self.settings = settings
        self.controller = ny_controller

    def process_symbol(self, symbol, now):
        # Phase 1: No-trade window
        if self.controller.in_no_trade_phase(now):
            return

        # Phase 2: Define opening range
        if self.controller.should_define_range(now):
            self.define_opening_range(symbol)
            return

        # Phase 3: Breakout detection (5m)
        if not self.controller.breakout_detected():
            self.detect_breakout(symbol)
            return

        # Phase 4 (later): 1m entry logic
        self.handle_entries(symbol, now)
        print(f"[NY-OPEN] Breakout detected for {symbol}, side={self.controller.breakout_side}")

    def define_opening_range(self, symbol):
        """
        Reads the 15-minute candle that formed during the no-trade window.
        """
        try:
            # We need exactly 1 candle: the last closed M15 bar
            from core.data_feed import get_bars
            df = get_bars(symbol, "M15", 1)

            last = df.iloc[-1]
            high = last["high"]
            low = last["low"]

            self.controller.set_opening_range(high, low)

            print(f"[NY-OPEN] Opening range for {symbol}: HIGH={high}, LOW={low}")

        except Exception as e:
            print(f"[NY-OPEN] Failed to define range for {symbol}: {e}")

    def detect_breakout(self, symbol):
        """
        Detects breakout of the opening range using the 5-minute chart.
        """
        if not self.controller.range_defined:
            return  # safety check

        try:
            from core.data_feed import get_bars
            df = get_bars(symbol, "M5", 2)  # last 2 bars, we need the last CLOSED one

            last = df.iloc[-1]
            close = last["close"]

            high = self.controller.range_high
            low = self.controller.range_low

            if close > high:
                self.controller.set_breakout("LONG")
                print(f"[NY-OPEN] Breakout UP for {symbol} (close={close} > high={high})")
                return

            if close < low:
                self.controller.set_breakout("SHORT")
                print(f"[NY-OPEN] Breakout DOWN for {symbol} (close={close} < low={low})")
                return

            # No breakout yet
            # print(f"[NY-OPEN] No breakout for {symbol}")

        except Exception as e:
            print(f"[NY-OPEN] Breakout detection failed for {symbol}: {e}")

    def handle_entries(self, symbol, now: datetime):
        """
        1m entry logic after breakout is detected.
        Implements breakout / retest / reversal patterns.
        """
        side = self.controller.breakout_side  # "LONG" or "SHORT"

        from core.data_feed import get_bars
        try:
            m1 = get_bars(symbol, "M1", 5)  # last 5 bars
        except Exception as e:
            print(f"[NY-OPEN] Failed to get M1 data for {symbol}: {e}")
            return

        pattern = self.detect_entry_pattern(m1, side)

        if pattern is None:
            return  # no entry signal yet

        self.place_ny_trade(symbol, side, pattern, m1)

        print(f"[NY-OPEN][ENTRY] {symbol} {pattern} ({side}) at {now}")

        # Later:
        # self.place_ny_trade(symbol, side, pattern, m1)

    def detect_entry_pattern(self, m1_df, side):
        last = m1_df.iloc[-1]
        prev = m1_df.iloc[-2]

        high = self.controller.range_high
        low = self.controller.range_low

        # BREAKOUT: strong close away from range
        if side == "LONG" and last["close"] > high and last["close"] > last["open"]:
            return "BREAKOUT"
        if side == "SHORT" and last["close"] < low and last["close"] < last["open"]:
            return "BREAKOUT"

        # RETEST: price dipped back to level and rejected
        if side == "LONG" and prev["low"] <= high <= prev["close"] and last["close"] > prev["close"]:
            return "RETEST"
        if side == "SHORT" and prev["high"] >= low >= prev["close"] and last["close"] < prev["close"]:
            return "RETEST"

        # REVERSAL: fakeout beyond range then strong opposite close
        if side == "LONG" and prev["close"] > high and last["close"] < high and last["close"] < last["open"]:
            return "REVERSAL"
        if side == "SHORT" and prev["close"] < low and last["close"] > low and last["close"] > last["open"]:
            return "REVERSAL"

        return None

    def place_ny_trade(self, symbol, side, pattern, m1_df):
        """
        Executes a trade based on the NY-open pattern.
        Uses your existing MT5 trade manager.
        """

        last = m1_df.iloc[-1]
        high = self.controller.range_high
        low = self.controller.range_low

        # -------------------------
        # ENTRY PRICE
        # -------------------------
        entry_price = last["close"]

        # -------------------------
        # STOP LOSS LOGIC
        # -------------------------
        if side == "LONG":
            if pattern == "BREAKOUT":
                sl = low  # SL below opening range
            elif pattern == "RETEST":
                sl = last["low"]  # SL below retest candle
            else:  # REVERSAL
                sl = last["low"]
        else:
            if pattern == "BREAKOUT":
                sl = high
            elif pattern == "RETEST":
                sl = last["high"]
            else:
                sl = last["high"]

        # -------------------------
        # TAKE PROFIT LOGIC (RR 2.0)
        # -------------------------
        risk = abs(entry_price - sl)
        tp = entry_price + 2 * risk if side == "LONG" else entry_price - 2 * risk

        # -------------------------
        # CALL YOUR EXISTING TRADE MANAGER
        # -------------------------
        try:
            from core.trade_executor import execute_trade

            lots, sl, tp, result = execute_trade(
                symbol=symbol,
                direction="buy" if side == "LONG" else "sell",
                df=m1_df,
                last=last,
                settings=self.settings,
                magic=1
            )
            if result is None:
                result_text = "NO_TRADE"
            else:
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    result_text = f"EXECUTED: order={result.order}"
                else:
                    result_text = f"FAILED: retcode={result.retcode}, comment={result.comment}"

            log_to_db(symbol, last, m1_df, f"NY_{pattern}", lots, sl, tp, result_text, "M1")

            print(f"[NY-OPEN][TRADE] {symbol} {side} {pattern} entry={entry_price} SL={sl} TP={tp}")

        except Exception as e:
            print(f"[NY-OPEN][ERROR] Failed to place trade for {symbol}: {e}")

    def build_log_last(self, pattern, m1_df):
        last = {
            "bullish_engulfing": 0,
            "bearish_engulfing": 0,
            "hammer": 0,
            "shooting_star": 0,
            "morning_star": 0,
            "evening_star": 0,
            "bullish_pin_bar": 0,
            "bearish_pin_bar": 0,
            "bullish_three_bar_reversal": 0,
            "bearish_three_bar_reversal": 0,
            "bullish_breakout_bar": 0,
            "bearish_breakout_bar": 0,
            "bullish_inside_bar": 0,
            "bearish_inside_bar": 0,
            "doji": 0,
            "outside_bar": 0,
            "near_sr": 0,
            "in_demand": 0,
            "in_supply": 0,
            "vol_ok": 1,  # NY strategy always uses volatility filters
            "bullish_count": 0,
            "bearish_count": 0,
            "recent_bullish": 0,
            "recent_bearish": 0,
            "bias_long": 1 if pattern in ("BREAKOUT", "RETEST") else 0,
            "bias_short": 1 if pattern == "REVERSAL" else 0,
            "htf_ma_fast": 0.0,
            "htf_ma_slow": 0.0,
            "htf_ma_fast_slope": 0.0,
            "long_signal": 1 if pattern in ("BREAKOUT", "RETEST") else 0,
            "short_signal": 1 if pattern == "REVERSAL" else 0,
            "trigger_pattern": f"NY_{pattern}"
        }
        return last



