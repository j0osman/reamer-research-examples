from reamer_research import buy_market, close_position


class SampleStrategy:
    lookback = 1
    ticker = "AAPL"

    def __init__(self, config_path=None):
        self.in_pos = False
        self.qty = 1.0

    def on_bar(self, data):
        ticker = self.ticker
        tv = data[ticker]
        if not tv.valid:
            return None
        if (not self.in_pos) and (float(tv.close[-1]) > float(tv.open[-1])):
            self.in_pos = True
            return buy_market(self.qty, ticker=ticker)
        if self.in_pos and (float(tv.close[-1]) < float(tv.open[-1])):
            self.in_pos = False
            return close_position(ticker=ticker)
        return None


if __name__ == '__main__':
    # Runs on the sample bars, or on a CSV or .bin you pass:
    #   python3 examples/sample_strategy.py [bars.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    bars = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    print(rr.backtest(SampleStrategy, {SampleStrategy.ticker: bars}, open_viewer=True))
