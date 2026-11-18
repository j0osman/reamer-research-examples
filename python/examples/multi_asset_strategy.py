from reamer_research import buy_market, close_position, orders


class MultiAssetSampleStrategy:
    lookback = 1
    tickers = ["AAPL", "SPY"]

    def __init__(self, config_path=None):
        self.in_position = {}
        self.qty = 1.0

    def on_bar(self, data):
        out = []
        for ticker in self.tickers:
            tv = data[ticker]
            if not tv.valid:
                continue
            in_pos = self.in_position.get(ticker, False)
            if (not in_pos) and float(tv.close[-1]) > float(tv.open[-1]):
                out.append(buy_market(self.qty, ticker=ticker))
                self.in_position[ticker] = True
            elif in_pos and float(tv.close[-1]) < float(tv.open[-1]):
                out.append(close_position(ticker=ticker))
                self.in_position[ticker] = False

        return orders(*out) if out else None


if __name__ == '__main__':
    # Two tickers, so this needs a licence: Evaluation Mode runs one ticker.
    # The sample bars stand in for each ticker unless you pass one file each:
    #   python3 examples/multi_asset_strategy.py [AAPL.csv SPY.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    sample = Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    files = sys.argv[1:] or [sample] * len(MultiAssetSampleStrategy.tickers)
    try:
        print(rr.backtest(MultiAssetSampleStrategy, dict(zip(MultiAssetSampleStrategy.tickers, files)), open_viewer=True))
    except rr.ReamerError as e:
        if e.code_name != 'LICENSE_MISSING':
            raise
        sys.exit(f'{Path(__file__).name} trades {len(MultiAssetSampleStrategy.tickers)} tickers and Evaluation Mode runs one; '
                 'a Reamer Research licence removes the limit: https://reamerlabs.com/pricing')
