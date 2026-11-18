"""Limit order entry strategy.

Places a GTC buy limit 0.5% below the current close on a crossover signal.
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

        self.entry_pct_below = float(cfg.get("entry_pct_below", 0.005))
        self.hold_bars       = int(cfg.get("hold_bars", 10))
        self.qty             = float(cfg.get("qty", 5.0))

        self._order_count = 0
        self.pending_id   = None
        self.held         = 0

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

        # The limit filled: hold for hold_bars, then close.
        if data.position(ticker) > 0:
            self.pending_id = None
            self.held += 1
            if self.held < self.hold_bars:
                return None
            self.held = 0
            self._order_count += 1               # a close takes the next order ID too
            print(f"Closing after {self.hold_bars} bars, close={close:.2f}")
            return close_position(ticker=ticker)

        resting = any(o['order_id'] == self.pending_id for o in data.open_orders())
        if self.pending_id is not None and not resting:
            self.pending_id = None

        if self.pending_id is not None and not in_uptrend:
            cxl = cancel_order(self.pending_id, ticker=ticker)
            self.pending_id = None
            print(f"Cancelled stale limit — trend reversed, close={close:.2f}")
            return cxl

        if self.pending_id is None and in_uptrend:
            entry_price = round(close * (1 - self.entry_pct_below), 2)
            self._order_count += 1               # order IDs count up from 1
            self.pending_id = self._order_count
            print(f"Limit buy submitted: id={self.pending_id} price={entry_price:.2f}")
            return buy_limit(entry_price, self.qty, ticker=ticker)

        return None

if __name__ == '__main__':
    # Runs on the sample bars, or on a CSV or .bin you pass:
    #   python3 examples/limit_entry_strategy.py [bars.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    bars = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    print(rr.backtest(LimitEntryStrategy, {LimitEntryStrategy.ticker: bars}, open_viewer=True))
