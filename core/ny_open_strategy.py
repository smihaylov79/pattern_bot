from datetime import datetime, time, timedelta


class NYOpenController:
    def __init__(self, settings, ny_symbols):
        self.enabled = settings["ny_open_strategy"]["enabled"]
        self.ny_symbols = set(ny_symbols)

        cfg = settings["ny_open_strategy"]
        self.ny_open_time_str = cfg["ny_open_time"]
        self.no_trade_minutes = cfg["no_trade_minutes"]
        self.max_duration_minutes = cfg["max_duration_minutes"]

        # Internal state (for later phases)
        self.range_defined = False
        self.range_high = None
        self.range_low = None
        self.breakout_resolved = False

    def get_ny_times(self, now: datetime):
        ny_open = datetime.combine(now.date(), time.fromisoformat(self.ny_open_time_str))
        no_trade_end = ny_open + timedelta(minutes=self.no_trade_minutes)
        ny_end = ny_open + timedelta(minutes=self.max_duration_minutes)
        return ny_open, no_trade_end, ny_end

    def is_ny_session_active(self, now: datetime) -> bool:
        ny_open, _, ny_end = self.get_ny_times(now)
        return ny_open <= now <= ny_end

    def in_no_trade_phase(self, now: datetime) -> bool:
        ny_open, no_trade_end, _ = self.get_ny_times(now)
        return ny_open <= now < no_trade_end

    def should_use_ny_strategy(self, symbol, now: datetime) -> bool:
        if not self.enabled:
            return False
        if symbol not in self.ny_symbols:
            return False
        if not self.is_ny_session_active(now):
            return False
        return True

    def should_define_range(self, now):
        """
        Returns True exactly once: at the moment the no-trade phase ends.
        """
        ny_open, no_trade_end, _ = self.get_ny_times(now)

        # If we are past the no-trade phase AND range not yet defined
        return now >= no_trade_end and not self.range_defined

    def set_opening_range(self, high, low):
        self.range_high = high
        self.range_low = low
        self.range_defined = True

    def breakout_detected(self):
        return self.breakout_resolved or hasattr(self, "breakout_side")

    def set_breakout(self, side):
        self.breakout_side = side  # "LONG" or "SHORT"




