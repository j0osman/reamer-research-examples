#!/usr/bin/env python3
"""CSV in: pass the path, or load it first to look at or fix the bars.

    python3 examples/data_csv.py [bars.csv]

rr.backtest takes a CSV path directly and names the ticker after the file.
rr.load_csv reads the same file into a numpy array (BAR_DTYPE) when you want
the bars in hand first. It reads most vendor exports as they are:

  - Date and Time columns, or one timestamp column (timestamp, ts, datetime)
    holding epoch seconds, epoch milliseconds or a date string
  - Open, High, Low, Close; Volume, Notional and Tick_count if present
  - any header case, MetaTrader <DATE> style headers, and comma, semicolon
    or tab delimiters, detected from the header line

Times are UTC. Rows are sorted by time, so an export written newest first
loads the right way round.
"""
import sys
from pathlib import Path

import reamer_research as rr

SAMPLE = Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'


def on_bar(d):
    """Long while the close is above its 20-bar mean, flat otherwise."""
    if d.close[0] == 0:                      # window still filling
        return None
    above = d.close[-1] > d.close.mean()
    if above and d.position() == 0:
        return rr.buy_market(10)
    if not above and d.position() > 0:
        return rr.close_position()
    return None


path = Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE

# 1. The path itself. The ticker is named after the file: 'SAMPLE_5min'.
print(rr.backtest(on_bar, str(path), lookback=20))

# 2. Load first, then run the array under a ticker name of your choice.
bars = rr.load_csv(path)
print(f'{len(bars)} bars, first close {bars["close"][0]:.2f}, last close {bars["close"][-1]:.2f}')
print(repr(rr.backtest(on_bar, {'SAMPLE': bars}, lookback=20)))

# 3. A vendor layout: semicolon delimited, epoch-millisecond timestamps,
#    lower-case headers, newest row first. CSV text works as well as a path.
text = 'timestamp;open;high;low;close;volume\n' + '\n'.join(
    f'{int(b["ts"]) * 1000};{b["open"]};{b["high"]};{b["low"]};{b["close"]};{b["volume"]}'
    for b in bars[::-1])
same = rr.load_csv(text)
print('vendor layout loads the same bars:', bool((same == bars).all()))
