import json
from reamer_research import buy_stop, sell_stop, orders


class AtrStopBracket:
    ticker = "AAPL"
    # Engine reads lookback off the class before construction (it can't see
    # config_path-derived values), so this must cover the largest atr_period
    # this strategy is meant to be configured with; _atr() guards against a
    # config that raises atr_period past this.
    lookback = 15

    def __init__(self, config_path=None):
        cfg = {}
        if config_path:
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
            except Exception:
                pass
        self.atr_period       = int(cfg.get("atr_period", 14))
        self.atr_mult         = float(cfg.get("atr_mult", 1.5))
        self.tp_mult          = float(cfg.get("tp_mult", 2.0))
        self.sl_mult          = float(cfg.get("sl_mult", 1.0))
        self.qty              = float(cfg.get("qty", 1.0))
        self.bracket_interval = int(cfg.get("bracket_interval", 25))
        self._bar = 0

    def _atr(self, tv):
        if len(tv.close) < self.atr_period + 1 or tv.close[0] == 0.0:
            return None
        trs = []
        for i in range(self.atr_period):
            h  = float(tv.high[-(i + 1)])
            l  = float(tv.low[-(i + 1)])
            pc = float(tv.close[-(i + 2)])
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        return sum(trs) / len(trs)

    def on_bar(self, data):
        self._bar += 1
        if self._bar % self.bracket_interval != 0:
            return None
        ticker = self.ticker
        tv = data[ticker]
        if not tv.valid:
            return None
        atr = self._atr(tv)
        if atr is None or atr <= 0:
            return None
        close  = float(tv.close[-1])
        offset = self.atr_mult * atr
        buy_px = close + offset
        return orders(
            buy_stop(buy_px, self.qty, ticker=ticker,
                     take_profit=buy_px + self.tp_mult * atr,
                     stop_loss=buy_px - self.sl_mult * atr),
            sell_stop(close - offset, self.qty, ticker=ticker),
        )


if __name__ == '__main__':
    # Runs on the sample bars, or on a CSV or .bin you pass:
    #   python3 templates/atr_stop_bracket.py [bars.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    bars = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    print(rr.backtest(AtrStopBracket, {AtrStopBracket.ticker: bars}, open_viewer=True))
