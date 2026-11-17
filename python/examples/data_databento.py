#!/usr/bin/env python3
"""Databento bars in: from a DBN file you already have, or priced and downloaded.

    pip install databento

    # A DBN file you downloaded before: no key, no cost.
    python3 examples/data_databento.py es.ohlcv-1m.dbn.zst

    # Download: key in DATABENTO_API_KEY. Databento bills per request; the
    # fetcher asks for the price first and refuses anything over $1.00.
    python3 examples/data_databento.py --download GLBX.MDP3 ES.c.0

The fetcher in fetchers/databento_bars.py reads the ohlcv-1s, -1m, -1h and
-1d schemas, converts Databento's fixed-point prices exactly, and splits a
multi-symbol file into one array per symbol. It returns {ticker: bars},
which is what rr.backtest takes.

The download asks for four weeks of one-minute bars, which fits inside
Evaluation Mode for one symbol. Databento writes no bar for a minute with no
trades; the engine runs each bar until the next, so gaps need no filling.
Equity prices from Databento are not adjusted for splits or dividends.

Databento's account, fees and terms are your own; the engine makes no
network calls.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import reamer_research as rr
from fetchers.databento_bars import bars_from_dbn, fetch_databento

if len(sys.argv) == 4 and sys.argv[1] == '--download':
    dataset, symbol = sys.argv[2], sys.argv[3]
    bars = fetch_databento(dataset, [symbol], 'ohlcv-1m', '2024-01-02', '2024-01-30',
                           stype_in='continuous' if '.c.' in symbol else 'raw_symbol',
                           max_cost_usd=1.00)
elif len(sys.argv) == 2:
    import databento
    bars = bars_from_dbn(databento.DBNStore.from_file(sys.argv[1]))
else:
    sys.exit(__doc__)

for t, b in bars.items():
    print(f'{t}: {len(b)} bars')


def on_bar(d):
    """Long while the close is above its 20-bar mean, flat otherwise."""
    if d.close[0] == 0:
        return None
    above = d.close[-1] > d.close.mean()
    if above and d.position() == 0:
        return rr.buy_market(1)
    if not above and d.position() > 0:
        return rr.close_position()
    return None


# One symbol per run without a licence; a licensed run takes them all at once.
first = sorted(bars)[0]
print(rr.backtest(on_bar, {first: bars[first]}, lookback=20))
