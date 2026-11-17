#!/usr/bin/env python3
"""Alpaca bars in: download, run, and keep a .bin copy.

    python3 examples/data_alpaca.py                  # BTC/USD, no key needed
    python3 examples/data_alpaca.py AAPL 1Hour       # US stocks: free paper keys

Crypto bars need no Alpaca account. Stock bars need an API key pair in
ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY (a free paper account has one;
its feed is IEX). The fetcher in fetchers/alpaca_bars.py uses only the
standard library and numpy, and fills each bar's trade count and notional
from Alpaca's n and vwap, so the engine simulates every bar at its real
number of trades.

The fetcher returns {ticker: bars}, which is exactly what rr.backtest takes.
Four weeks of one ticker fits inside Evaluation Mode.

Alpaca's account and terms are your own; the engine makes no network calls.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import reamer_research as rr
from fetchers.alpaca_bars import fetch_alpaca_crypto, fetch_alpaca_stocks

symbol = sys.argv[1] if len(sys.argv) > 1 else 'BTC/USD'
timeframe = sys.argv[2] if len(sys.argv) > 2 else '1Hour'
start, end = '2025-01-01', '2025-01-29'

if '/' in symbol:
    bars = fetch_alpaca_crypto([symbol], timeframe, start, end)
else:
    bars = fetch_alpaca_stocks([symbol], timeframe, start, end)   # adjustment='all'
b = bars[symbol]
print(f'{symbol}: {len(b)} {timeframe} bars, {int((b["tick_count"] > 0).sum())} with trades')

CAPITAL = 10_000.0


def on_bar(d):
    """Long while the close is above its 20-bar mean, 90% of capital, flat otherwise."""
    if d.close[0] == 0:
        return None
    above = d.close[-1] > d.close.mean()
    if above and d.position() == 0:
        return rr.buy_market(0.9 * CAPITAL / d.close[-1])
    if not above and d.position() > 0:
        return rr.close_position()
    return None


print(rr.backtest(on_bar, bars, lookback=20, initial_capital=CAPITAL))

# Keep a local copy so later runs skip the download and map the file.
out = os.path.join(tempfile.mkdtemp(), symbol.replace('/', '-') + '.bin')
rr.write_bin(out, b)
print(f'saved {out}; next time: rr.backtest(on_bar, {out!r}, lookback=20)')
