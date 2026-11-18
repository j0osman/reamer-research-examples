"""Bracket order strategy: automatic TP and SL exits.

Enters on an SMA crossover with take_profit and stop_loss attached to the entry.
The engine closes the position automatically when either level is reached.

Key thing to observe after running:
  - result.order_log has one entry per trade (the entry orders only)
  - result.closed_trades has one entry per trade WITH the exit fill price
  - Bracket exits do NOT appear in order_log — always use closed_trades to count trades

Demonstrates: take_profit, stop_loss, ATR-based bracket sizing, closed_trades vs order_log.

Logging convention used here:
  - print(...)            → stdout → shown in white in the console
  - print(..., file=sys.stderr) → stderr → shown in amber in the console
"""

import json
import sys

from reamer_research import buy_market


class BracketStrategy:
    ticker = "AAPL"
    def __init__(self, config_path=None):
        cfg = {}
        if config_path:
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
            except Exception:
                pass

        self.sma_period  = int(cfg.get("sma_period", 20))
        self.atr_period  = int(cfg.get("atr_period", 14))
        self.tp_atr_mult = float(cfg.get("tp_atr_mult", 2.0))
        self.sl_atr_mult = float(cfg.get("sl_atr_mult", 1.0))
        self.qty         = float(cfg.get("qty", 5.0))
        self.lookback    = max(self.sma_period, self.atr_period + 1)

        self.in_position = False

    def _atr(self, tv):
        if tv.close[0] == 0.0:
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
        ticker = self.ticker
        tv = data[ticker]
        if not tv.valid:
            return None
        if tv.close[0] == 0.0:
            return None

        close  = float(tv.close[-1])
        sma    = float(tv.close[-self.sma_period:].mean())
        atr    = self._atr(tv)

        if atr is None or atr <= 0:
            return None

        if self.in_position:
            print(f"in position — waiting for bracket exit", file=sys.stderr)
            return None

        tp = round(close + self.tp_atr_mult * atr, 4)
        sl = round(close - self.sl_atr_mult * atr, 4)

        if close > sma:
            self.in_position = True
            print(f"BUY  close={close:.2f} sma={sma:.2f} atr={atr:.4f} TP={tp:.2f} SL={sl:.2f}")
            return buy_market(self.qty, ticker=ticker, take_profit=tp, stop_loss=sl)

        return None


if __name__ == '__main__':
    # Runs on the sample bars, or on a CSV or .bin you pass:
    #   python3 examples/bracket_strategy.py [bars.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    bars = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    print(rr.backtest(BracketStrategy, {BracketStrategy.ticker: bars}, open_viewer=True))
