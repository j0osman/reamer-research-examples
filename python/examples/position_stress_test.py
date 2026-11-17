"""
Dense stress-test strategy for visual verification of partial closes,
scale-ins, and trade reversals in both long and short directions.

Repeating 16-bar cycle on any single-asset dataset:

  phase  0  buy  2.0  — open long
  phase  2  buy  1.0  — scale-in long        → 3 units
  phase  4  sell 1.0  — partial close long   → 2 units
  phase  6  sell 4.0  — reversal             → close 2 long, open 2 short
  phase  8  sell 1.0  — scale-in short       → 3 units
  phase 10  buy  1.0  — partial close short  → 2 units
  phase 12  buy  4.0  — reversal             → close 2 short, open 2 long
  phase 14  close     — flat

Every other bar has an order; on a 500-bar dataset this produces ~250 orders
covering all execution paths. Run it with open_viewer=True to verify the
chart markers (entries, exits, scale-in arrows), position lines, trade spans,
and PnL accounting.
"""


from reamer_research import buy_market, sell_market, close_position

CYCLE = 16
_SIDE_NAME = {0: "flat", 1: "long", -1: "short"}


class PositionStressTest:
    lookback = 1
    ticker = "AAPL"

    def __init__(self, config_path=None):
        self._bar = -1

    def on_bar(self, data):
        self._bar += 1
        ticker = self.ticker
        tv = data[ticker]
        if not tv.valid:
            return None

        pos    = data.position(ticker)
        side   = (pos > 0) - (pos < 0)
        qty    = abs(pos)
        phase  = self._bar % CYCLE
        sname  = _SIDE_NAME.get(side, str(side))

        if phase == 0:
            print(f"[{self._bar:4d}] open long    buy 2.0          pos_before={sname}/{qty:.1f}")
            return buy_market(2.0, ticker=ticker)

        if phase == 2:
            print(f"[{self._bar:4d}] scale-in     buy +1.0         pos_before={sname}/{qty:.1f}")
            return buy_market(1.0, ticker=ticker)

        if phase == 4:
            print(f"[{self._bar:4d}] partial close sell 1.0        pos_before={sname}/{qty:.1f}")
            return sell_market(1.0, ticker=ticker)

        if phase == 6:
            print(f"[{self._bar:4d}] reversal     sell 4.0         pos_before={sname}/{qty:.1f}  → opens short 2")
            return sell_market(4.0, ticker=ticker)

        if phase == 8:
            print(f"[{self._bar:4d}] scale-in     sell +1.0        pos_before={sname}/{qty:.1f}")
            return sell_market(1.0, ticker=ticker)

        if phase == 10:
            print(f"[{self._bar:4d}] partial close buy 1.0         pos_before={sname}/{qty:.1f}")
            return buy_market(1.0, ticker=ticker)

        if phase == 12:
            print(f"[{self._bar:4d}] reversal     buy 4.0          pos_before={sname}/{qty:.1f}  → opens long 2")
            return buy_market(4.0, ticker=ticker)

        if phase == 14:
            if side != 0:
                print(f"[{self._bar:4d}] close all                       pos_before={sname}/{qty:.1f}")
                return close_position(ticker=ticker)

        return None


if __name__ == '__main__':
    print(f"{__name__} defines a strategy class ({PositionStressTest.__name__}), "
          "not a standalone script -- drive it with run_backtest() the way "
          "examples/quickstart_run.py drives BuyAndHold, or pass it to "
          "rr.backtest(..., open_viewer=True) to check every fill in the visual "
          "trade diagnostics tool.")
