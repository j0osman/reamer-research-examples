"""The smallest complete run: ATR band reversion over a CSV, opened in the visual
trade diagnostics tool.

Fades a close more than two ATRs from its 20-bar mean, targets the mean and
stops two ATRs further out.

    pip install reamer_research-*.whl     (once: the wheel in the kit's python/;
                                           free download at reamerlabs.com/download)
    python3 python/examples/quickstart.py [bars.csv]

With no argument it runs on sample_data/SAMPLE_5min.csv, synthetic bars that
fit inside Evaluation Mode, so it runs before a licence is activated.
"""
import sys, pathlib
import numpy as np
import reamer_research as rr

def on_bar(d):
    c, h, l = d.close, d.high[1:], d.low[1:]
    if c[0] == 0: return               # warm-up: the window is still filling
    atr = (np.maximum(h, c[:-1]) - np.minimum(l, c[:-1])).mean()
    mid, px = c.mean(), c[-1]
    if d.position() == 0 and px < mid - 2 * atr:
        return rr.buy_market(10, take_profit=mid, stop_loss=px - 2 * atr)
    if d.position() == 0 and px > mid + 2 * atr:
        return rr.sell_market(10, take_profit=mid, stop_loss=px + 2 * atr)

csv = sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).parent.parent / 'sample_data' / 'SAMPLE_5min.csv'
print(rr.backtest(on_bar, csv, lookback=20, open_viewer=True))
