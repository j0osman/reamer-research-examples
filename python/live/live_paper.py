"""Paper trading with Reamer Research alone: the quickstart's on_bar, live.

Reamer Research makes no network calls and reads no market data feed. Going
live takes three parts, and this script has all of them:

  1. A bar source. Each closed bar goes into a rolling window per ticker.
  2. Your strategy. The same on_bar as examples/quickstart.py, unchanged,
     called once per closed bar with a LiveData built from that window. It
     reads close, high, low and position(), which LiveData provides.
  3. rr.Relay, which sends the orders on_bar returns to a receiver over a
     Unix socket and reads the fills back as positions. The receiver here is
     relay_receiver.PaperBroker, which fills against the bars. For real
     orders, put your broker's API behind the receiver instead.

    python3 live/live_paper.py                  # replay sample_data/SAMPLE_5min.csv
    python3 live/live_paper.py bars.csv         # replay your own bars
    python3 live/live_paper.py --alpaca BTC/USD # Alpaca's free 1-minute crypto
                                                # bars, no key, until Ctrl-C

The relay needs a Reamer Research licence: Evaluation Mode has no live
trading, so rr.Relay raises a licence error until one is activated.
Linux and macOS (Windows through WSL2).
"""
import argparse
import pathlib
import sys
import tempfile
import time

import numpy as np
import reamer_research as rr

from relay_receiver import Receiver, PaperBroker

HERE = pathlib.Path(__file__).resolve().parent
LOOKBACK = 20


def on_bar(d):                         # examples/quickstart.py, unchanged
    c, h, l = d.close, d.high[1:], d.low[1:]
    if c[0] == 0: return               # warm-up: the window is still filling
    atr = (np.maximum(h, c[:-1]) - np.minimum(l, c[:-1])).mean()
    mid, px = c.mean(), c[-1]
    if d.position() == 0 and px < mid - 2 * atr:
        return rr.buy_market(10, take_profit=mid, stop_loss=px - 2 * atr)
    if d.position() == 0 and px > mid + 2 * atr:
        return rr.sell_market(10, take_profit=mid, stop_loss=px + 2 * atr)


class TickerWindow:
    """The last `lookback` bars of one ticker, oldest first and zero-padded
    while it fills, as a backtest's window is."""

    FIELDS = ('ts', 'open', 'high', 'low', 'close', 'volume', 'notional')

    def __init__(self, lookback):
        self._a = {f: np.zeros(lookback, np.int64 if f == 'ts' else np.float64)
                   for f in self.FIELDS}
        self.valid = False

    def push(self, bar):
        for f in self.FIELDS:
            self._a[f][:-1] = self._a[f][1:]
            self._a[f][-1] = bar[f]
        self.valid = True

    def __getattr__(self, name):
        try:
            return self._a[name]
        except KeyError:
            raise AttributeError(name) from None


class LiveData:
    """The parts of a backtest's `data` that on_bar reads, from live bars and
    the relay's positions: close, open, high, low, volume, notional and ts
    (straight off it with one ticker, or through data['AAPL']), position(),
    position_state(), ts and tickers."""

    def __init__(self, tickers, lookback, relay):
        self.tickers = list(tickers)
        self._w = {t: TickerWindow(lookback) for t in self.tickers}
        self._relay = relay
        self.ts = 0

    def push(self, ticker, bar):
        for t, w in self._w.items():
            w.valid = t == ticker     # the others are carried forward
        self._w[ticker].push(bar)
        self.ts = int(bar['ts'])

    def __getitem__(self, ticker):
        return self._w[ticker]

    def __getattr__(self, name):
        if len(self.tickers) != 1:
            raise AttributeError(f'{name}: name the ticker, data[ticker].{name}')
        return getattr(self._w[self.tickers[0]], name)

    def position_state(self, ticker=None):
        return self._relay.positions()[ticker or self.tickers[0]]

    def position(self, ticker=None):
        return self.position_state(ticker)['qty']


def replay(path):
    """Closed bars from a CSV, one at a time, as a feed would deliver them."""
    for bar in rr.load_csv(path):
        yield bar


def alpaca(symbol, warmup):
    """Alpaca's free 1-minute crypto bars, each once its minute has closed.
    The first `warmup` closed bars fill the window without trading on them."""
    sys.path.insert(0, str(HERE.parent))
    from fetchers.alpaca_bars import fetch_alpaca_crypto

    def closed_since(minutes):
        now = time.time()
        start = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now - 60 * minutes))
        end = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))
        try:
            bars = fetch_alpaca_crypto([symbol], '1Min', start, end)[symbol]
        except RuntimeError:          # no trades yet in that span
            return []
        return [b for b in bars if b['ts'] + 60 <= now]

    history = closed_since(warmup * 4)[-warmup:]
    for bar in history:
        yield bar, False
    last = int(history[-1]['ts']) if history else 0
    while True:
        time.sleep(60 - time.time() % 60 + 5)   # 5 s after each minute closes
        for bar in closed_since(10):
            if bar['ts'] > last:
                last = int(bar['ts'])
                yield bar, True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('csv', nargs='?', default=HERE.parent / 'sample_data' / 'SAMPLE_5min.csv')
    ap.add_argument('--alpaca', metavar='SYMBOL', help='e.g. BTC/USD')
    args = ap.parse_args()

    ticker = args.alpaca or 'SAMPLE'
    sock = pathlib.Path(tempfile.gettempdir()) / 'reamer-live-paper.sock'
    broker = PaperBroker()
    with Receiver(sock, broker), rr.Relay(sock, [ticker]) as relay:
        data = LiveData([ticker], LOOKBACK, relay)
        feed = alpaca(ticker, LOOKBACK) if args.alpaca else ((b, True) for b in replay(args.csv))
        try:
            for bar, live in feed:
                broker.mark(ticker, bar)          # fill what rests from earlier bars
                relay.poll(0)                     # and read those fills back
                data.push(ticker, bar)
                if args.alpaca and live:
                    print(time.strftime('%H:%M', time.gmtime(data.ts)), f'close {bar["close"]:g}')
                orders = on_bar(data) if live else None
                if orders is not None:
                    ids = relay.send(orders)
                    broker.wait_for(relay.messages)  # resting before the next bar
                    print(time.strftime('%Y-%m-%d %H:%M', time.gmtime(data.ts)),
                          f'sent order {ids}, position {data.position():g}')
        except KeyboardInterrupt:
            pass
        relay.poll(100)
        state = relay.positions()[ticker]
        print(f'{len(broker.fills)} fills, {relay.sent} orders sent, '
              f'position {state["qty"]:g} at {state["avg_entry_price"]:g}')


if __name__ == '__main__':
    try:
        main()
    except rr.ReamerError as e:
        if e.code_name != 'LICENSE_MISSING':
            raise
        sys.exit('live_paper.py: the relay needs a Reamer Research licence; Evaluation Mode has no '
                 'live trading. Activate one with reamer-license activate <key>, or buy one at '
                 'https://reamerlabs.com/pricing')
