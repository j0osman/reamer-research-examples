"""Minimal strategy for the quickstart guide.

Buys 10 units on bar 5, closes on bar 15. Used to verify your build and data
are working before adding real signal logic.

Run:
    python3 examples/quickstart_strategy.py [bars.csv]
"""

from reamer_research import buy_market, close_position


class QuickstartStrategy:
    lookback = 1
    ticker = "AAPL"

    def __init__(self, config_path=None):
        self.bar = 0
        self.in_position = False

    def on_bar(self, data):
        self.bar += 1
        ticker = self.ticker
        tv = data[ticker]
        if not tv.valid:
            return None
        close  = float(tv.close[-1])

        if self.bar == 5 and not self.in_position:
            self.in_position = True
            print(f"Entering long at bar {self.bar}, close={close:.2f}")
            return buy_market(10.0, ticker=ticker)

        if self.bar == 15 and self.in_position:
            self.in_position = False
            print(f"Closing at bar {self.bar}, close={close:.2f}")
            return close_position(ticker=ticker)

        return None


if __name__ == '__main__':
    # Runs on the sample bars, or on a CSV or .bin you pass:
    #   python3 examples/quickstart_strategy.py [bars.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    bars = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    print(rr.backtest(QuickstartStrategy, {QuickstartStrategy.ticker: bars}, open_viewer=True))
