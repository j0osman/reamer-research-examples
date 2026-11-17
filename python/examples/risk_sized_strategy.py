"""Risk-sized position strategy.

Sizes each position so that hitting the stop loss costs exactly `risk_per_trade`
dollars — a standard risk management approach.

Position sizing formula:
    qty = risk_per_trade / (entry_price - stop_price)

Uses SMA crossover for the signal, ATR for stop distance, and 2R take profit.

Demonstrates: position sizing from risk budget, buy_market with TP/SL, config-driven params.
"""

import json

from reamer_research import buy_market


class RiskSizedStrategy:
    ticker = "AAPL"
    def __init__(self, config_path=None):
        cfg = {}
        if config_path:
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
            except Exception:
                pass

        self.sma_period    = int(cfg.get("sma_period", 20))
        self.atr_period    = int(cfg.get("atr_period", 14))
        self.risk_per_trade = float(cfg.get("risk_per_trade", 200.0))
        self.sl_atr_mult   = float(cfg.get("sl_atr_mult", 1.5))
        self.tp_rr         = float(cfg.get("tp_rr", 2.0))
        self.lookback      = max(self.sma_period, self.atr_period + 1)

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

    def _position_size(self, entry, stop):
        risk_per_unit = abs(entry - stop)
        if risk_per_unit < 1e-6:
            return 0.0
        return self.risk_per_trade / risk_per_unit

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

        if atr is None or atr <= 0 or self.in_position:
            return None

        if close > sma:
            entry_est   = close
            sl          = round(entry_est - self.sl_atr_mult * atr, 4)
            sl_distance = entry_est - sl
            tp          = round(entry_est + self.tp_rr * sl_distance, 4)
            qty         = round(self._position_size(entry_est, sl), 4)

            if qty <= 0:
                return None

            self.in_position = True
            print(
                f"BUY qty={qty:.4f}  entry≈{entry_est:.2f}  "
                f"SL={sl:.2f}  TP={tp:.2f}  "
                f"risk=${self.risk_per_trade:.0f}"
            )
            return buy_market(qty, ticker=ticker, take_profit=tp, stop_loss=sl)

        return None
