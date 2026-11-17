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
