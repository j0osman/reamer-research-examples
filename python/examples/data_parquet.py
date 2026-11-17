#!/usr/bin/env python3
"""Parquet (and any pandas DataFrame) in.

    pip install pandas pyarrow
    python3 examples/data_parquet.py [bars.parquet]

rr.backtest takes a pandas DataFrame directly. Column names are matched
without regard to case: open, high, low, close, and volume, notional and
tick_count if present. The time can be a DatetimeIndex, a ts column of
datetimes or epoch seconds, or a timestamp, datetime or date column.
Timezone-aware times are converted to UTC; naive times are read as UTC.

So Parquet is one pandas call: read it, pass the frame. The same goes for
anything else pandas reads (Feather, HDF5, SQL, Excel), and for frames
from yfinance and other libraries.

With no argument the script writes the sample CSV to Parquet first, so it
runs as it is.
"""
import sys
import tempfile
from pathlib import Path

import pandas as pd

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


if len(sys.argv) > 1:
    path = Path(sys.argv[1])
else:
    # Make a Parquet file the way most pipelines store bars: a timezone-aware
    # DatetimeIndex and lower-case OHLCV columns.
    csv = pd.read_csv(SAMPLE)
    frame = pd.DataFrame(
        {'open': csv.Open, 'high': csv.High, 'low': csv.Low, 'close': csv.Close,
         'volume': csv.Volume},
    ).set_index(pd.to_datetime(csv.Date + ' ' + csv.Time, utc=True).rename('timestamp'))
    path = Path(tempfile.mkdtemp()) / 'SAMPLE.parquet'
    frame.to_parquet(path)

df = pd.read_parquet(path)
print(df.head(3))

# The frame is the bars.
print(rr.backtest(on_bar, {'SAMPLE': df}, lookback=20))

# rr.to_bars gives the numpy array the engine runs, if you want it, e.g.
# to keep a .bin copy so later runs skip pandas: rr.write_bin('SAMPLE.bin', df)
bars = rr.to_bars(df)
print(f'{len(bars)} bars from {path.name}')
