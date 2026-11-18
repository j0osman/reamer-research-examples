import json
import math
from reamer_research import buy_market, close_position


class MeanReversion:
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
        self.window  = int(cfg.get("window", 20))
        self.z_entry = float(cfg.get("z_entry", 1.5))
        self.qty     = float(cfg.get("qty", 1.0))
        self.closes  = []
        self.in_pos  = False

    def on_bar(self, data):
        ticker = self.ticker
        tv = data[ticker]
        if not tv.valid:
            return None
        c = float(tv.close[-1])
        self.closes.append(c)
        if len(self.closes) > self.window:
            self.closes.pop(0)
        if len(self.closes) < self.window:
            return None
        mean = sum(self.closes) / self.window
        std  = math.sqrt(sum((x - mean) ** 2 for x in self.closes) / self.window)
        if std == 0:
            return None
        z = (c - mean) / std
        if z < -self.z_entry and not self.in_pos:
            self.in_pos = True
            return buy_market(self.qty, ticker=ticker)
        if z > 0 and self.in_pos:
            self.in_pos = False
            return close_position(ticker=ticker)
        return None


if __name__ == '__main__':
    # Runs on the sample bars, or on a CSV or .bin you pass:
    #   python3 templates/mean_reversion.py [bars.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    bars = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    print(rr.backtest(MeanReversion, {MeanReversion.ticker: bars}, open_viewer=True))
