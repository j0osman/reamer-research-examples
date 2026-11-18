"""
Limit-entry strategy: enters long when price dips 30% of the way from the
bar open to the bar low, then closes at the next bar open.

The threshold is range-based so the strategy triggers on any bar with a
downward wick, regardless of price level or timeframe.

A buy_limit at the threshold fills at the synthetic tick where the simulated
ask crosses that level — identical execution semantics to the former on_tick
approach, at zero extra cost.
"""
from reamer_research import buy_limit, close_position


class TickEntryStrategy:
    lookback = 1
    ticker = "AAPL"

    def __init__(self, config_path=None):
        self.qty      = 1.0
        self.wick_pct = 0.30

    def on_bar(self, data):
        ticker = self.ticker
        tv = data[ticker]
        if not tv.valid:
            return None
        bar_open  = float(tv.open[-1])
        bar_low   = float(tv.low[-1])
        down_wick = bar_open - bar_low

        orders = [close_position(ticker=ticker)]

        if down_wick > 0:
            threshold = bar_open - down_wick * self.wick_pct
            orders.append(buy_limit(threshold, self.qty, ticker=ticker))

        return orders


if __name__ == '__main__':
    # Runs on the sample bars, or on a CSV or .bin you pass:
    #   python3 examples/tick_entry_strategy.py [bars.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    bars = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    print(rr.backtest(TickEntryStrategy, {TickEntryStrategy.ticker: bars}, open_viewer=True))
