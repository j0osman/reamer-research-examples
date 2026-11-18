from reamer_research import buy_market


class BuyAndHold:
    lookback = 1
    ticker = "AAPL"

    def __init__(self, config_path=None):
        self.bought = False
        self.qty    = 1.0

    def on_bar(self, data):
        ticker = self.ticker
        if self.bought or not data[ticker].valid:
            return None
        self.bought = True
        return buy_market(self.qty, ticker=ticker)


if __name__ == '__main__':
    # Runs on the sample bars, or on a CSV or .bin you pass:
    #   python3 templates/buy_and_hold.py [bars.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    bars = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    print(rr.backtest(BuyAndHold, {BuyAndHold.ticker: bars}, open_viewer=True))
