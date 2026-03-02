import time
from datetime import datetime
import pandas as pd
import MetaTrader5 as mt5

from .utils import open_scalper_order, close_scalper_order
from core.data_feed import timeframe_to_seconds
from .utils import atr


class ScalperBot:
    def __init__(self, symbol, timeframe="M5", atr_period=14, body_threshold=0.5,
                 magic=999001, comment="scalper_bot"):
        self.symbol = symbol
        self.timeframe = timeframe
        self.atr_period = atr_period
        self.body_threshold = body_threshold
        self.magic = magic
        self.comment = comment
        self.tf_seconds = timeframe_to_seconds(timeframe)
        self.last_check = 0

    def process(self):
        now = time.time()
        if now - self.last_check < 1:
            return
        self.last_check = now
        self.process_symbol()

    def process_symbol(self):
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
        }

        rates = mt5.copy_rates_from_pos(self.symbol, tf_map[self.timeframe], 0, 20)
        if rates is None or len(rates) < 15:
            return

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)

        current = df.iloc[-1]

        atr_value = atr(df, self.atr_period).iloc[-1]
        if pd.isna(atr_value):
            return

        body = abs(current["close"] - current["open"])
        if body < atr_value * self.body_threshold:
            return

        now = datetime.utcnow()
        seconds_into_candle = int(now.timestamp()) % self.tf_seconds
        seconds_left = self.tf_seconds - seconds_into_candle

        if seconds_left > 5:
            return

        direction = "sell" if current["close"] > current["open"] else "buy"

        ticket = open_scalper_order(
            symbol=self.symbol,
            order_type=direction,
            lots=1,
            magic=self.magic,
            comment=self.comment
        )

        if ticket:
            time.sleep(15)
            close_scalper_order(ticket)
