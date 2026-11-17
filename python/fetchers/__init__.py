"""Market-data fetchers for the Reamer Research Python binding.

Each fetcher downloads historical bars from a vendor and returns them in the
form run_backtest() takes: a dict of ticker name -> numpy structured array
of BAR_DTYPE, sorted by timestamp. write_csv() saves one ticker's bars in a
layout bin/reamer-csv-build reads, for runs over memory-mapped .bin files.

    from fetchers.alpaca_bars import fetch_alpaca_stocks
    bars = fetch_alpaca_stocks(['AAPL'], '1Min', '2024-01-02', '2024-01-31')
    result = run_backtest(MyStrategy, config, bars)

The fetchers are reference material in source, like the binding: read them,
change them, or copy the pattern for another vendor. The engine itself makes
no network calls. Vendor accounts, fees and terms of use are your own.
"""

import csv
import datetime

import numpy as np

# Field order and types of ReamerOhlcvBar. ts is the UTC epoch second the bar
# opens; notional 0.0 and tick_count -1 mean "not supplied".
BAR_DTYPE = np.dtype([
    ('ts', 'i8'), ('open', 'f8'), ('high', 'f8'), ('low', 'f8'),
    ('close', 'f8'), ('volume', 'f8'), ('notional', 'f8'), ('tick_count', 'i8'),
])


def write_csv(bars, path):
    """Write one ticker's bars to a CSV that bin/reamer-csv-build converts:

        bin/reamer-csv-build AAPL.csv AAPL.bin

    Notional and Tick_count columns are written only when the vendor
    supplied them.
    """
    bars = np.asarray(bars, dtype=BAR_DTYPE)
    has_notional = bool(len(bars)) and bool(np.any(bars['notional'] != 0.0))
    has_ticks = bool(len(bars)) and bool(np.any(bars['tick_count'] >= 0))
    header = ['Date', 'Time', 'Open', 'High', 'Low', 'Close', 'Volume']
    if has_notional:
        header.append('Notional')
    if has_ticks:
        header.append('Tick_count')
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        for b in bars:
            stamp = datetime.datetime.fromtimestamp(int(b['ts']), tz=datetime.timezone.utc)
            row = [stamp.strftime('%Y-%m-%d'), stamp.strftime('%H:%M:%S'),
                   repr(float(b['open'])), repr(float(b['high'])),
                   repr(float(b['low'])), repr(float(b['close'])),
                   repr(float(b['volume']))]
            if has_notional:
                row.append(repr(float(b['notional'])))
            if has_ticks:
                row.append(int(b['tick_count']))
            w.writerow(row)
