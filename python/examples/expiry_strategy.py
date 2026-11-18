"""Order expiry strategy: GTD and IOC demonstrations.

Shows three expiry patterns side by side:
  1. GTD limit — cancels at a specific timestamp if unfilled
  2. IOC market — fills on bar N's tick sequence or cancels at bar N's seal
  3. cancel_order — manually cancels a GTC limit 5 bars after submission

Demonstrates: tif="GTD", tif="IOC", expiry_timestamp, cancel_order, order_id tracking.
"""

import json
from datetime import datetime, timedelta, timezone

from reamer_research import buy_limit, buy_market, cancel_order


class ExpiryStrategy:
    lookback = 1
    ticker = "AAPL"

    def __init__(self, config_path=None):
        cfg = {}
        if config_path:
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
            except Exception:
                pass

        self.qty              = float(cfg.get("qty", 1.0))
        self.gtd_expiry_hours = int(cfg.get("gtd_expiry_hours", 48))

        self._bar                = 0
        self._order_count        = 0
        self._pending_cancel_id  = None
        self._cancel_at_bar      = None

    def on_bar(self, data):
        self._bar += 1
        ticker = self.ticker
        tv = data[ticker]
        if not tv.valid:
            return None

        close  = float(tv.close[-1])
        dt     = datetime.fromtimestamp(int(tv.ts[-1]), tz=timezone.utc)

        if self._bar == 5:
            self._order_count += 1
            expiry = (dt + timedelta(hours=self.gtd_expiry_hours)).strftime("%Y-%m-%d %H:%M:%S")
            entry  = round(close * 0.97, 2)
            print(f"GTD limit buy at {entry:.2f}, expires {expiry}")
            return buy_limit(entry, self.qty, ticker=ticker, tif="GTD", expiry_timestamp=expiry)

        if self._bar == 20:
            self._order_count += 1
            print(f"IOC market buy submitted at bar {self._bar} — fills bar {self._bar} or cancels")
            return buy_market(self.qty, ticker=ticker, tif="IOC")

        if self._bar == 40:
            entry = round(close * 0.90, 2)
            self._order_count += 1
            self._pending_cancel_id = self._order_count
            self._cancel_at_bar     = self._bar + 5
            print(f"GTC limit buy id={self._pending_cancel_id} at {entry:.2f}, will cancel at bar {self._cancel_at_bar}")
            return buy_limit(entry, self.qty, ticker=ticker)

        if self._bar == self._cancel_at_bar and self._pending_cancel_id is not None:
            oid = self._pending_cancel_id
            self._pending_cancel_id = None
            print(f"Cancelling order id={oid}")
            return cancel_order(oid, ticker=ticker)

        return None


if __name__ == '__main__':
    # Runs on the sample bars, or on a CSV or .bin you pass:
    #   python3 examples/expiry_strategy.py [bars.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    bars = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    print(rr.backtest(ExpiryStrategy, {ExpiryStrategy.ticker: bars}, open_viewer=True))
