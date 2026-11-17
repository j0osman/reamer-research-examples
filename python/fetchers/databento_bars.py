"""Historical OHLCV bars from Databento, ready for run_backtest().

Needs the databento client (pip install databento) and an API key, passed as
api_key= or set in DATABENTO_API_KEY. Databento bills per request, so
fetch_databento() asks Databento for the price first and refuses a request
estimated above max_cost_usd.

    from fetchers.databento_bars import fetch_databento
    bars = fetch_databento('GLBX.MDP3', ['ES.c.0'], 'ohlcv-1m',
                           '2024-01-02', '2024-02-01', stype_in='continuous')

bars_from_dbn() reads a DBN file you already downloaded, at no cost:

    import databento
    bars = bars_from_dbn(databento.DBNStore.from_file('es.ohlcv-1m.dbn.zst'))

Databento writes no bar for an interval with no trades. The engine runs each
bar until the next one, so a quiet minute is folded into the bar before it,
as with any gapped data. Equity prices from Databento are not adjusted for
splits or dividends; adjust them before a run that spans one.
"""

import datetime
import os
import sys

import numpy as np

from fetchers import BAR_DTYPE

OHLCV_SCHEMAS = ('ohlcv-1s', 'ohlcv-1m', 'ohlcv-1h', 'ohlcv-1d')

# Databento prices are fixed-point integers in units of 1e-9. Divide rather
# than multiply by 1e-9: 3702750000000 / 1e9 is exactly 3702.75, while
# 3702750000000 * 1e-9 is 3702.7500000000005.
_PRICE_SCALE = 1e9
_NS_PER_S = 1_000_000_000


def _import_databento():
    try:
        import databento
    except ImportError:
        raise ImportError('pip install databento to use fetch_databento()') from None
    return databento


def _resolve_api_key(api_key):
    key = api_key or os.environ.get('DATABENTO_API_KEY')
    if not key:
        raise ValueError('No Databento API key: pass api_key= or set DATABENTO_API_KEY')
    return key


def _day_ns(d):
    return int(datetime.datetime(d.year, d.month, d.day,
                                 tzinfo=datetime.timezone.utc).timestamp()) * _NS_PER_S


def _symbol_masks(records, mappings):
    """Yield (requested symbol, row mask) pairs.

    mappings is DBNStore.mappings: requested symbol -> list of
    {start_date, end_date, symbol} where symbol is the instrument ID that
    the requested symbol pointed to over [start_date, end_date). Matching on
    the date range as well as the ID keeps a continuous contract such as
    ES.c.0 on the right instrument either side of a roll.
    """
    ids = records['instrument_id']
    ts = records['ts_event'].astype(np.int64)
    if not mappings:
        for iid in np.unique(ids):
            yield str(int(iid)), ids == iid
        return
    for requested, intervals in mappings.items():
        mask = np.zeros(len(records), dtype=bool)
        for iv in intervals:
            try:
                iid = int(iv['symbol'])
            except (TypeError, ValueError):
                continue
            mask |= ((ids == iid)
                     & (ts >= _day_ns(iv['start_date']))
                     & (ts < _day_ns(iv['end_date'])))
        yield requested, mask


def bars_from_dbn(store):
    """Convert a Databento OHLCV DBNStore into {symbol: bars}.

    Keys are the symbols as requested (e.g. 'ESH4', 'ES.c.0', 'AAPL').
    """
    schema = str(getattr(store.schema, 'value', store.schema))
    if schema not in OHLCV_SCHEMAS:
        raise ValueError(f'expected one of {OHLCV_SCHEMAS}, got schema {schema!r}')
    records = store.to_ndarray()
    if not isinstance(records, np.ndarray):
        records = np.concatenate(list(records))
    out = {}
    for symbol, mask in _symbol_masks(records, store.mappings):
        r = records[mask]
        if not len(r):
            continue
        bars = np.empty(len(r), dtype=BAR_DTYPE)
        # Integer division: ts_event is nanoseconds, beyond float64's exact range.
        bars['ts'] = r['ts_event'].astype(np.int64) // _NS_PER_S
        for f in ('open', 'high', 'low', 'close'):
            bars[f] = r[f].astype(np.float64) / _PRICE_SCALE
        bars['volume'] = r['volume'].astype(np.float64)
        bars['notional'] = 0.0
        bars['tick_count'] = -1
        out[symbol] = bars[np.argsort(bars['ts'], kind='stable')]
    return out


def fetch_databento(dataset, symbols, schema, start, end, api_key=None,
                    stype_in='raw_symbol', max_cost_usd=1.0):
    """Download OHLCV bars from Databento's historical API.

    dataset      : e.g. 'GLBX.MDP3' (CME futures), 'XNAS.ITCH' (Nasdaq)
    symbols      : list, e.g. ['ESH4'] or, with stype_in='continuous', ['ES.c.0']
    schema       : one of OHLCV_SCHEMAS
    start, end   : passed to Databento as given, e.g. '2024-01-02'
    stype_in     : Databento symbology of `symbols`: 'raw_symbol',
                   'continuous' or 'parent'
    max_cost_usd : refuse a request Databento prices above this; None skips
                   the check
    """
    if schema not in OHLCV_SCHEMAS:
        raise ValueError(f'schema must be one of {OHLCV_SCHEMAS}, got {schema!r}')
    if isinstance(symbols, str):
        symbols = [symbols]
    databento = _import_databento()
    client = databento.Historical(_resolve_api_key(api_key))
    request = dict(dataset=dataset, symbols=list(symbols), schema=schema,
                   start=start, end=end, stype_in=stype_in)

    if max_cost_usd is not None:
        cost = float(client.metadata.get_cost(**request))
        if cost > max_cost_usd:
            raise RuntimeError(
                f'Databento prices this request at ${cost:.2f}, above '
                f'max_cost_usd=${max_cost_usd:.2f}. Narrow it or raise the limit.')
        print(f'Databento cost estimate: ${cost:.2f}', file=sys.stderr)

    bars = bars_from_dbn(client.timeseries.get_range(**request))
    missing = [s for s in symbols if s not in bars]
    if missing:
        raise RuntimeError(f'No bars returned for {missing} in {dataset} {schema} '
                           f'between {start} and {end}')
    return bars
