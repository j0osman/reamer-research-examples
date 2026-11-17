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
