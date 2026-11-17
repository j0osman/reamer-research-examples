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
