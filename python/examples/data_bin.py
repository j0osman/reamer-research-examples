#!/usr/bin/env python3
"""Binary .bin files: convert once, then every run memory-maps the file.

    python3 examples/data_bin.py [bars.csv]

A .bin file holds the bars in the engine's own 64-byte layout. When every
ticker in rr.backtest is a .bin path, the engine maps the files in place
instead of copying them into Python, so a run starts without a parse step
and data larger than RAM still runs. start= and end= pick a time range
inside the file without rewriting it.

rr.write_bin makes a .bin from anything rr.to_bars takes: a CSV path, a
numpy array, a list of tuples or a pandas DataFrame. The kit's
bin/reamer-csv-build does the same from the command line. rr.read_bin reads
one back as a numpy array. Neither needs a licence.
"""
import sys
import tempfile
from pathlib import Path

import reamer_research as rr

SAMPLE = Path(__file__).resolve().parent.parent / 'sample_data' / 'SAMPLE_5min.csv'


def on_bar(d):
    """Long while the close is above its 20-bar mean, flat otherwise."""
    if d.close[0] == 0:
        return None
    above = d.close[-1] > d.close.mean()
    if above and d.position() == 0:
        return rr.buy_market(10)
    if not above and d.position() > 0:
        return rr.close_position()
    return None


src = Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE
out = Path(tempfile.mkdtemp()) / 'SAMPLE.bin'

# Convert once. The file is named for the ticker: SAMPLE.bin runs as 'SAMPLE'.
rr.write_bin(out, src)
print(f'wrote {out} ({out.stat().st_size:,} bytes)')

# Every run after that maps the file.
print(rr.backtest(on_bar, str(out), lookback=20))

# A time range inside the file: the second half, by timestamp.
bars = rr.read_bin(out)
middle = int(bars['ts'][len(bars) // 2])
print(repr(rr.backtest(on_bar, str(out), lookback=20, start=middle)))

# The file reads back bar for bar.
print('round trip exact:', bool((bars == rr.load_csv(src)).all()))
