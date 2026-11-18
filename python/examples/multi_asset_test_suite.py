"""
Multi-asset execution test suite.

Designed for 2+ tickers with overlapping timestamps. Verifies that the replay
engine handles concurrent positions independently per ticker and that shared
equity / margin accounting is correct across the portfolio.

Phases (SLOT bars apart):
  0  open long  ticker[0]  plain → manual close
  1  open long  ticker[1]  plain → manual close
  2  open long  BOTH simultaneously → close both independently
  3  long ticker[0] + short ticker[1] simultaneously → close both
  4  TP+SL on ticker[0] while ticker[1] holds plain position
  5  limit on ticker[0] + stop on ticker[1] → fill independently
  6  large order — insufficient margin while other position is open → rejected
"""


from reamer_research import (
    buy_market, sell_market, close_position,
    buy_limit, buy_stop, orders,
)

SLOT = 25


def _slot(n):
    return n * SLOT


class MultiAssetTestSuite:
    lookback = 1

    def __init__(self, tickers=("AAPL", "SPY")):
        self.tickers = list(tickers)
        self._phase_bar = -1

    def on_bar(self, data):
        t0, t1 = self.tickers[0], self.tickers[1]
        v0, v1 = data[t0], data[t1]
        if not v0.valid or not v1.valid:
            return None

        self._phase_bar += 1
        b    = self._phase_bar
        c0   = float(v0.close[-1])
        c1   = float(v1.close[-1])
        atr0 = max(float(v0.high[-1]) - float(v0.low[-1]), 1e-8)
        atr1 = max(float(v1.high[-1]) - float(v1.low[-1]), 1e-8)

        # ── phase 0  long ticker[0] plain ─────────────────────────────────────
        if b == _slot(0):
            return buy_market(1.0, ticker=t0)
        if b == _slot(0) + 5:
            return close_position(ticker=t0)

        # ── phase 1  long ticker[1] plain ─────────────────────────────────────
        if b == _slot(1):
            return buy_market(1.0, ticker=t1)
        if b == _slot(1) + 5:
            return close_position(ticker=t1)

        # ── phase 2  both tickers open simultaneously ──────────────────────────
        if b == _slot(2):
            return orders(
                buy_market(1.0, ticker=t0),
                buy_market(1.0, ticker=t1),
            )
        if b == _slot(2) + 5:
            return close_position(ticker=t0)
        if b == _slot(2) + 8:
            return close_position(ticker=t1)

        # ── phase 3  long t0 + short t1 simultaneously ────────────────────────
        if b == _slot(3):
            return orders(
                buy_market(1.0,  ticker=t0),
                sell_market(1.0, ticker=t1),
            )
        if b == _slot(3) + 5:
            return orders(
                close_position(ticker=t0),
                buy_market(0.0, ticker=t1),
            )

        # ── phase 4  TP+SL on t0 while t1 holds plain ────────────────────────
        if b == _slot(4):
            return orders(
                buy_market(1.0, ticker=t0,
                           take_profit=c0 + atr0 * 2, stop_loss=c0 - atr0 * 2),
                buy_market(1.0, ticker=t1),
            )
        if b == _slot(4) + 10:
            return close_position(ticker=t1)

        # ── phase 5  limit t0 + stop t1 independently ────────────────────────
        if b == _slot(5):
            return orders(
                buy_limit(c0 - atr0, 1.0, ticker=t0),
                buy_stop(c1 + atr1,  1.0, ticker=t1),
            )
        if b == _slot(5) + 15:
            return orders(
                close_position(ticker=t0),
                close_position(ticker=t1),
            )

        # ── phase 6  margin rejection: huge qty while positions open ───────────
        if b == _slot(6):
            return buy_market(1.0, ticker=t0)
        if b == _slot(6) + 1:
            return buy_market(1e9, ticker=t1)
        if b == _slot(6) + 5:
            return close_position(ticker=t0)

        return None


if __name__ == '__main__':
    # Two tickers, so this needs a licence: Evaluation Mode runs one ticker.
    # The sample bars stand in for each ticker unless you pass one file each:
    #   python3 examples/multi_asset_test_suite.py [AAPL.csv SPY.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    sample = Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    strategy = MultiAssetTestSuite()
    files = sys.argv[1:] or [sample] * len(strategy.tickers)
    try:
        print(rr.backtest(strategy, dict(zip(strategy.tickers, files)), open_viewer=True))
    except rr.ReamerError as e:
        if e.code_name != 'LICENSE_MISSING':
            raise
        sys.exit(f'{Path(__file__).name} trades {len(strategy.tickers)} tickers and Evaluation Mode runs one; '
                 'a Reamer Research licence removes the limit: https://reamerlabs.com/pricing')
