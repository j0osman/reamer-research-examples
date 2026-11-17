from datetime import datetime, timedelta

from reamer_research import (
    buy_market, sell_market, close_position,
    buy_limit, sell_limit,
    buy_stop, sell_stop,
    cancel_order,
)

# Exercises every order kind, TIF, bracket, scale-in/partial-close/reversal,
# cancellation, and rejection path in one deterministic run — built for
# manually verifying engine fill/rejection behavior against known-expected
# outcomes.
#
# Multi-asset: each ticker in `tickers` runs the full scenario suite
# independently, keyed off its OWN valid-bar count (self._local_bar[ticker]),
# not the global step counter — so a deliberately sparser/asynchronous ticker
# still runs through every scenario on its own cadence, the same way a real
# strategy reacting to independently-sampled activity bars would. This is
# also what exercises tv.valid == False / "no new bar this step" for the
# sparse ticker.
SLOT = 25


def _slot(n):
    return n * SLOT


class ReplayVerify:
    lookback = 1
    tickers = ["AAPL", "SPY"]

    def __init__(self, config_path=None):
        self._local_bar     = {t: -1 for t in self.tickers}
        self._next_id       = 1   # mirrors ReplayEngine::m_nextOrderId (starts at 1)
        self._cancel_target = {}  # ticker -> predicted order id awaiting cancellation

    def _emit(self, out, ticker, order_dict, tag):
        assigned_id = self._next_id
        self._next_id += 1
        print(f"[ReplayVerify] {ticker} order#{assigned_id} {tag}: "
              f"{order_dict.get('order_type')} qty={order_dict.get('qty', 0):.2f}")
        out.append(order_dict)
        return assigned_id

    def _range_atr(self, tv):
        # Crude proxy (this bar's own high-low range), not a real rolling ATR --
        # deterministic and needs no extra lookback, matching the original template.
        h, lo = float(tv.high[-1]), float(tv.low[-1])
        return max(h - lo, 1e-6)

    def on_bar(self, data):
        out = []
        for ticker in self.tickers:
            tv = data[ticker]
            if not tv.valid:
                continue
            self._local_bar[ticker] += 1
            b   = self._local_bar[ticker]
            c   = float(tv.close[-1])
            atr = self._range_atr(tv)

            # ── S0/S1: plain market round trips (long, then short) ──────────────
            if b == _slot(0):
                self._emit(out, ticker, buy_market(1.0, ticker=ticker), "S0 long entry")
            if b == _slot(0) + 6:
                self._emit(out, ticker, close_position(ticker=ticker), "S0 long close")

            if b == _slot(1):
                self._emit(out, ticker, sell_market(1.0, ticker=ticker), "S1 short entry")
            if b == _slot(1) + 6:
                self._emit(out, ticker, buy_market(0.0, ticker=ticker), "S1 short close")

            # ── S2/S3: market entries with TP/SL brackets ────────────────────────
            if b == _slot(2):
                self._emit(out, ticker, buy_market(1.0, ticker=ticker,
                           take_profit=c + atr * 2, stop_loss=c - atr * 2),
                           "S2 long+bracket")
            if b == _slot(3):
                self._emit(out, ticker, sell_market(1.0, ticker=ticker,
                           take_profit=c - atr * 2, stop_loss=c + atr * 2),
                           "S3 short+bracket")

            # ── S4/S5: limit entries, manual close ───────────────────────────────
            if b == _slot(4):
                self._emit(out, ticker, buy_limit(c - atr, 1.0, ticker=ticker), "S4 buy_limit entry")
            if b == _slot(4) + 10:
                self._emit(out, ticker, close_position(ticker=ticker), "S4 close")

            if b == _slot(5):
                self._emit(out, ticker, sell_limit(c + atr, 1.0, ticker=ticker), "S5 sell_limit entry")
            if b == _slot(5) + 10:
                self._emit(out, ticker, buy_market(0.0, ticker=ticker), "S5 close")

            # ── S6/S7: limit entries with brackets ───────────────────────────────
            if b == _slot(6):
                entry = c - atr
                self._emit(out, ticker, buy_limit(entry, 1.0, ticker=ticker,
                           take_profit=entry + atr * 3, stop_loss=entry - atr * 1.5),
                           "S6 buy_limit+bracket")
            if b == _slot(7):
                entry = c + atr
                self._emit(out, ticker, sell_limit(entry, 1.0, ticker=ticker,
                           take_profit=entry - atr * 3, stop_loss=entry + atr * 1.5),
                           "S7 sell_limit+bracket")

            # ── S8/S9: stop entries, manual close ─────────────────────────────────
            if b == _slot(8):
                self._emit(out, ticker, buy_stop(c + atr, 1.0, ticker=ticker), "S8 buy_stop entry")
            if b == _slot(8) + 10:
                self._emit(out, ticker, close_position(ticker=ticker), "S8 close")

            if b == _slot(9):
                self._emit(out, ticker, sell_stop(c - atr, 1.0, ticker=ticker), "S9 sell_stop entry")
            if b == _slot(9) + 10:
                self._emit(out, ticker, buy_market(0.0, ticker=ticker), "S9 close")

            # ── S10/S11: stop entries with brackets ───────────────────────────────
            if b == _slot(10):
                entry = c + atr
                self._emit(out, ticker, buy_stop(entry, 1.0, ticker=ticker,
                           take_profit=entry + atr * 2, stop_loss=entry - atr),
                           "S10 buy_stop+bracket")
            if b == _slot(11):
                entry = c - atr
                self._emit(out, ticker, sell_stop(entry, 1.0, ticker=ticker,
                           take_profit=entry - atr * 2, stop_loss=entry + atr),
                           "S11 sell_stop+bracket")

            # ── S12: scale-in (same-side add, weighted-avg entry) ────────────────
            if b == _slot(12):
                self._emit(out, ticker, buy_market(1.0, ticker=ticker), "S12 scale-in open")
            if b == _slot(12) + 3:
                self._emit(out, ticker, buy_market(1.0, ticker=ticker), "S12 scale-in add")
            if b == _slot(12) + 8:
                self._emit(out, ticker, close_position(ticker=ticker), "S12 scale-in close")

            # ── S13: partial close, then full close of the remainder ────────────
            if b == _slot(13):
                self._emit(out, ticker, buy_market(2.0, ticker=ticker), "S13 open qty=2")
            if b == _slot(13) + 4:
                self._emit(out, ticker, close_position(1.0, ticker=ticker), "S13 partial close qty=1")
            if b == _slot(13) + 8:
                self._emit(out, ticker, close_position(ticker=ticker), "S13 remainder close")

            # ── S14: reversal (close-side qty > position.qty nets into opposite) ─
            if b == _slot(14):
                self._emit(out, ticker, buy_market(1.0, ticker=ticker), "S14 open long qty=1")
            if b == _slot(14) + 4:
                self._emit(out, ticker, sell_market(2.0, ticker=ticker), "S14 reversal to short")
            if b == _slot(14) + 8:
                self._emit(out, ticker, buy_market(0.0, ticker=ticker), "S14 close short")

            # ── S15: IOC that fills same eligible bar (priced at the market) ────
            if b == _slot(15):
                self._emit(out, ticker, buy_limit(c, 1.0, tif="IOC", ticker=ticker), "S15 IOC at-market")
            if b == _slot(15) + 3:
                self._emit(out, ticker, close_position(ticker=ticker), "S15 close (no-op if IOC never filled)")

            # ── S16: IOC placed far from market — expect Cancelled at bar seal ───
            if b == _slot(16):
                self._emit(out, ticker, buy_limit(c - atr * 50, 1.0, tif="IOC", ticker=ticker),
                           "S16 IOC far from market")

            # ── S17: GTD that fills a few bars later ──────────────────────────────
            if b == _slot(17):
                exp = (datetime(2000, 1, 1) + timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")
                self._emit(out, ticker, buy_limit(c - atr, 1.0, tif="GTD",
                           expiry_timestamp=exp, ticker=ticker), "S17 GTD (far expiry)")
            if b == _slot(17) + 12:
                self._emit(out, ticker, close_position(ticker=ticker), "S17 close (no-op if never filled)")

            # ── S18: GTD priced away from market with a near-term expiry — expect Expired ─
            if b == _slot(18):
                exp = (datetime(2000, 1, 1)).strftime("%Y-%m-%d %H:%M:%S")  # already in the past
                self._emit(out, ticker, buy_limit(c - atr * 50, 1.0, tif="GTD",
                           expiry_timestamp=exp, ticker=ticker), "S18 GTD (expired)")

            # ── S19: guaranteed rejection (TP on the wrong side of a long entry) ──
            if b == _slot(19):
                self._emit(out, ticker, buy_market(1.0, ticker=ticker, take_profit=c - atr),
                           "S19 invalid TP -> Rejected")

            # ── S20: submit then cancel by predicted id ──────────────────────────
            if b == _slot(20):
                order_id = self._emit(out, ticker, buy_limit(c - atr * 20, 1.0, ticker=ticker),
                                       "S20 GTC far from market (to be cancelled)")
                self._cancel_target[ticker] = order_id
            if b == _slot(20) + 2 and ticker in self._cancel_target:
                self._emit(out, ticker, cancel_order(self._cancel_target.pop(ticker), ticker=ticker),
                           "S20 cancel")

        return out if out else None
