"""
Execution engine test suite.

Covers all user-facing order types and TIF variants using real market prices
derived from live bar data. Bracket levels are set as ATR multiples so they
are plausible on any dataset with normal volatility.

Phases (one per SLOT bars, entry at slot_start):
  0  buy_market  plain          → manual close at +5
  1  sell_market plain          → manual close at +5
  2  buy_market  TP+SL          → bracket handles close
  3  sell_market TP+SL          → bracket handles close
  4  buy_limit   plain          → manual close at +15 (may still be pending)
  5  sell_limit  plain          → manual close at +15
  6  buy_limit   TP+SL          → bracket or timeout
  7  sell_limit  TP+SL          → bracket or timeout
  8  buy_stop    plain          → manual close at +15
  9  sell_stop   plain          → manual close at +15
  10 buy_stop    TP+SL          → bracket or timeout
  11 sell_stop   TP+SL          → bracket or timeout
  12 GTD limit   (far OTM)      → expires after 3 bars
  13 IOC market  buy            → fills bar N (same bar) or cancels at bar N's seal
  14 IOC buy_limit (deep OTM)   → cancelled at bar N's seal
  15 cancel_order pending GTC
  16 multi-order list (OCO pair)
  17 invalid bracket buy        → rejected
  18 reversal attempt           → rejected
"""


from datetime import datetime, timedelta, timezone

from reamer_research import (
    buy_market, sell_market, close_position,
    buy_limit, sell_limit,
    buy_stop, sell_stop,
    cancel_order, orders,
)

SLOT = 30


def _slot(n):
    return n * SLOT


class ExecutionTestSuite:
    lookback = 1

    def __init__(self, ticker="AAPL"):
        self.ticker = ticker
        self._bar = -1
        self._n   = 0

    def _emit(self, o):
        self._n += 1
        return o

    def on_bar(self, data):
        self._bar += 1
        b = self._bar
        t = self.ticker
        tv = data[t]
        if not tv.valid:
            return None
        c   = float(tv.close[-1])
        h   = float(tv.high[-1])
        lo  = float(tv.low[-1])
        atr = max(h - lo, 1e-6)

        # ── phase 0  buy_market plain ─────────────────────────────────────────
        if b == _slot(0):
            return self._emit(buy_market(1.0, ticker=t))
        if b == _slot(0) + 5:
            return self._emit(close_position(ticker=t))

        # ── phase 1  sell_market plain ────────────────────────────────────────
        if b == _slot(1):
            return self._emit(sell_market(1.0, ticker=t))
        if b == _slot(1) + 5:
            return self._emit(buy_market(0.0, ticker=t))

        # ── phase 2  buy_market TP+SL ─────────────────────────────────────────
        if b == _slot(2):
            return self._emit(buy_market(1.0, ticker=t,
                                         take_profit=c + atr * 2,
                                         stop_loss=c  - atr * 2))

        # ── phase 3  sell_market TP+SL ────────────────────────────────────────
        if b == _slot(3):
            return self._emit(sell_market(1.0, ticker=t,
                                          take_profit=c - atr * 2,
                                          stop_loss=c  + atr * 2))

        # ── phase 4  buy_limit plain ──────────────────────────────────────────
        if b == _slot(4):
            return self._emit(buy_limit(c - atr, 1.0, ticker=t))
        if b == _slot(4) + 15:
            return self._emit(close_position(ticker=t))

        # ── phase 5  sell_limit plain ─────────────────────────────────────────
        if b == _slot(5):
            return self._emit(sell_limit(c + atr, 1.0, ticker=t))
        if b == _slot(5) + 15:
            return self._emit(buy_market(0.0, ticker=t))

        # ── phase 6  buy_limit TP+SL ──────────────────────────────────────────
        if b == _slot(6):
            entry = c - atr
            return self._emit(buy_limit(entry, 1.0, ticker=t,
                                        take_profit=entry + atr * 3,
                                        stop_loss=entry   - atr * 1.5))

        # ── phase 7  sell_limit TP+SL ─────────────────────────────────────────
        if b == _slot(7):
            entry = c + atr
            return self._emit(sell_limit(entry, 1.0, ticker=t,
                                         take_profit=entry - atr * 3,
                                         stop_loss=entry   + atr * 1.5))

        # ── phase 8  buy_stop plain ───────────────────────────────────────────
        if b == _slot(8):
            return self._emit(buy_stop(c + atr, 1.0, ticker=t))
        if b == _slot(8) + 15:
            return self._emit(close_position(ticker=t))

        # ── phase 9  sell_stop plain ──────────────────────────────────────────
        if b == _slot(9):
            return self._emit(sell_stop(c - atr, 1.0, ticker=t))
        if b == _slot(9) + 15:
            return self._emit(buy_market(0.0, ticker=t))

        # ── phase 10  buy_stop TP+SL ──────────────────────────────────────────
        if b == _slot(10):
            entry = c + atr
            return self._emit(buy_stop(entry, 1.0, ticker=t,
                                       take_profit=entry + atr * 2,
                                       stop_loss=entry   - atr))

        # ── phase 11  sell_stop TP+SL ─────────────────────────────────────────
        if b == _slot(11):
            entry = c - atr
            return self._emit(sell_stop(entry, 1.0, ticker=t,
                                        take_profit=entry - atr * 2,
                                        stop_loss=entry   + atr))

        # ── phase 12  GTD limit — far OTM, expires in 3 bars ─────────────────
        if b == _slot(12):
            dt     = datetime.fromtimestamp(data.ts, timezone.utc)
            expiry = (dt + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
            return self._emit(buy_limit(c * 0.5, 1.0, tif="GTD", ticker=t,
                                        expiry_timestamp=expiry))

        # ── phase 13  IOC market buy ──────────────────────────────────────────
        if b == _slot(13):
            return self._emit(buy_market(1.0, ticker=t, tif="IOC"))
        if b == _slot(13) + 5:
            return self._emit(close_position(ticker=t))

        # ── phase 14  IOC buy_limit deep OTM → always cancelled ──────────────
        if b == _slot(14):
            return self._emit(buy_limit(c * 0.5, 1.0, tif="IOC", ticker=t))

        # ── phase 15  cancel pending GTC limit ────────────────────────────────
        if b == _slot(15):
            return self._emit(buy_limit(c * 0.5, 1.0, ticker=t))
        if b == _slot(15) + 2:
            return cancel_order(self._n, ticker=t)

        # ── phase 16  multi-order list (OCO pair) ─────────────────────────────
        if b == _slot(16):
            self._n += 2
            return [
                buy_limit(c - atr,  1.0, ticker=t),
                sell_limit(c + atr, 1.0, ticker=t),
            ]

        # ── phase 17  invalid bracket → rejected ──────────────────────────────
        if b == _slot(17):
            return self._emit(buy_market(1.0, ticker=t,
                                         take_profit=c * 0.5))

        # ── phase 18  reversal attempt → rejected ─────────────────────────────
        if b == _slot(18):
            return self._emit(buy_market(1.0, ticker=t))
        if b == _slot(18) + 2:
            return self._emit(buy_market(1.0, ticker=t))
        if b == _slot(18) + 5:
            return self._emit(close_position(ticker=t))

        return None


if __name__ == '__main__':
    print(f"{__name__} defines a strategy class ({ExecutionTestSuite.__name__}), "
          "not a standalone script -- drive it with run_backtest() the way "
          "examples/quickstart_run.py drives BuyAndHold, or pass it to "
          "rr.backtest(..., open_viewer=True) to check every fill in the visual "
          "trade diagnostics tool.")
