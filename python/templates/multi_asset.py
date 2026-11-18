from reamer_research import buy_market, close_position, orders


class MultiAsset:
    lookback = 1
    tickers = ["AAPL", "SPY"]

    def __init__(self, config_path=None):
        self.in_pos = {}
        self.qty    = 1.0

    def on_bar(self, data):
        out = []
        for ticker in self.tickers:
            tv = data[ticker]
            if not tv.valid:
                continue
            in_pos = self.in_pos.get(ticker, False)
            if float(tv.close[-1]) > float(tv.open[-1]) and not in_pos:
                out.append(buy_market(self.qty, ticker=ticker))
                self.in_pos[ticker] = True
            elif float(tv.close[-1]) < float(tv.open[-1]) and in_pos:
                out.append(close_position(ticker=ticker))
                self.in_pos[ticker] = False
        return orders(*out) if out else None


if __name__ == '__main__':
    # Two tickers, so this needs a licence: Evaluation Mode runs one ticker.
    # The sample bars stand in for each ticker unless you pass one file each:
    #   python3 templates/multi_asset.py [AAPL.csv SPY.csv]
    import sys
    from pathlib import Path
    import reamer_research as rr
    sample = Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
    files = sys.argv[1:] or [sample] * len(MultiAsset.tickers)
    try:
        print(rr.backtest(MultiAsset, dict(zip(MultiAsset.tickers, files)), open_viewer=True))
    except rr.ReamerError as e:
        if e.code_name != 'LICENSE_MISSING':
            raise
        sys.exit(f'{Path(__file__).name} trades {len(MultiAsset.tickers)} tickers and Evaluation Mode runs one; '
                 'a Reamer Research licence removes the limit: https://reamerlabs.com/pricing')
