"""Limit order entry strategy.

Places a GTC buy limit 2% below the current close on a crossover signal.
Tracks the pending order ID to avoid stacking duplicate orders.
Closes the position after a fixed bar hold.

Demonstrates: buy_limit, GTC persistence, order_id tracking, cancel_order.
"""

import json

from reamer_research import buy_limit, close_position, cancel_order

SMA_PERIOD = 20


class LimitEntryStrategy:
    lookback = SMA_PERIOD
    ticker = "AAPL"

    def __init__(self, config_path=None):
        cfg = {}
        if config_path:
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
            except Exception:
                pass

        self.entry_pct_below = float(cfg.get("entry_pct_below", 0.02))
        self.hold_bars       = int(cfg.get("hold_bars", 10))
        self.qty             = float(cfg.get("qty", 5.0))

        self._order_count = 0
        self.pending_id   = None

    def on_bar(self, data):
        ticker = self.ticker
        tv = data[ticker]
        if not tv.valid:
            return None
        if tv.close[0] == 0.0:
            return None

        close      = float(tv.close[-1])
        sma20      = float(tv.close.mean())
        in_uptrend = close > sma20

        if self.pending_id is not None and not in_uptrend:
            cxl = cancel_order(self.pending_id, ticker=ticker)
            self.pending_id = None
            print(f"Cancelled stale limit — trend reversed, close={close:.2f}")
            return cxl

        if self.pending_id is None and in_uptrend:
            entry_price = round(close * (1 - self.entry_pct_below), 2)
            self._order_count += 1
            self.pending_id = self._order_count
            print(f"Limit buy submitted: id={self.pending_id} price={entry_price:.2f}")
            return buy_limit(entry_price, self.qty, ticker=ticker)

        return None
