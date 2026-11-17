"""Historical bars from Alpaca's Market Data API, ready for run_backtest().

Standard library only. Stock bars need an Alpaca API key pair (a free paper
account has one), passed as arguments or set in ALPACA_API_KEY_ID and
ALPACA_API_SECRET_KEY. Crypto bars need no key.

    from fetchers.alpaca_bars import fetch_alpaca_stocks, fetch_alpaca_crypto
    bars = fetch_alpaca_stocks(['AAPL', 'MSFT'], '1Min', '2024-01-02', '2024-01-31')
    bars = fetch_alpaca_crypto(['BTC/USD'], '1Hour', '2024-01-01', '2024-02-01')

Stock bars default to adjustment='all', so splits and dividends are already
applied, which the engine requires. Alpaca reports each bar's trade count
and volume-weighted price, so tick_count and notional (volume x VWAP) are
filled and the engine simulates each bar at its real trade count. A crypto
bar with no trades (Alpaca reports n 0 and v 0) gets tick_count -1, since
the engine refuses 0. Alpaca's crypto bars come from Alpaca's own venue, where
most minutes of a 1Min pull can have no trades; check the volume before
treating them as a market-wide price.

The free plan's stock feed is 'iex' (one exchange); 'sip' is the full
consolidated tape and needs a paid plan. timeframe is Alpaca's own string:
'1Min', '5Min', '15Min', '1Hour', '1Day', '1Week', '1Month'.
"""

import datetime
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np

from fetchers import BAR_DTYPE

STOCK_BARS_URL = 'https://data.alpaca.markets/v2/stocks/bars'
CRYPTO_BARS_URL = 'https://data.alpaca.markets/v1beta3/crypto/{loc}/bars'

_MAX_RETRIES = 5


def _resolve_keys(api_key_id, api_secret_key):
    key_id = api_key_id or os.environ.get('ALPACA_API_KEY_ID')
    secret = api_secret_key or os.environ.get('ALPACA_API_SECRET_KEY')
    if not key_id or not secret:
        raise ValueError('No Alpaca API keys: pass api_key_id= and api_secret_key=, '
                         'or set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY')
    return key_id, secret


def _get_json(url, params, headers):
    """GET one page. Retries with backoff on rate limits (429), server errors
    (5xx) and dropped connections, which a long multi-page pull will meet."""
    full = url + '?' + urllib.parse.urlencode(params)
    last = None
    for attempt in range(_MAX_RETRIES):
        req = urllib.request.Request(full, headers=dict(headers, Accept='application/json'))
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                body = e.read().decode('utf-8', 'replace')[:300]
                raise RuntimeError(f'Alpaca returned HTTP {e.code}: {body}') from None
            last = f'HTTP {e.code}'
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            last = f'{type(e).__name__}: {e}'
        if attempt + 1 < _MAX_RETRIES:
            time.sleep(2 ** attempt)
    raise RuntimeError(f'Alpaca request failed after {_MAX_RETRIES} attempts ({last})')


def _fetch_pages(url, params, headers, symbols):
    by_symbol = {s: [] for s in symbols}
    params = dict(params, symbols=','.join(symbols))
    while True:
        data = _get_json(url, params, headers)
        for sym, rows in (data.get('bars') or {}).items():
            by_symbol.setdefault(sym, []).extend(rows)
        token = data.get('next_page_token')
        if not token:
            return by_symbol
        params['page_token'] = token


def _epoch_seconds(stamp):
    """RFC 3339 ('2024-01-02T14:30:00Z', fractional seconds allowed) -> epoch s."""
    core, _, _ = stamp.rstrip('Z').partition('.')
    dt = datetime.datetime.strptime(core, '%Y-%m-%dT%H:%M:%S')
    return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())


def bars_from_rows(rows):
    """Convert Alpaca bar objects ({t, o, h, l, c, v, n, vw}) to bars."""
    bars = np.empty(len(rows), dtype=BAR_DTYPE)
    for i, r in enumerate(rows):
        vw = r.get('vw')
        n = r.get('n')
        bars[i] = (_epoch_seconds(r['t']), float(r['o']), float(r['h']),
                   float(r['l']), float(r['c']), float(r['v']),
                   float(r['v']) * float(vw) if vw is not None else 0.0,
                   # The engine refuses tick_count 0. Alpaca's crypto feed has
                   # bars with no trades (n 0, v 0), so those count as unknown.
                   int(n) if n is not None and int(n) > 0 else -1)
    return bars[np.argsort(bars['ts'], kind='stable')]


def _to_bars(by_symbol, symbols, start, end):
    missing = [s for s in symbols if not by_symbol.get(s)]
    if missing:
        raise RuntimeError(f'No bars returned for {missing} between {start} and {end}')
    return {s: bars_from_rows(by_symbol[s]) for s in symbols}


def fetch_alpaca_stocks(symbols, timeframe, start, end, api_key_id=None,
                        api_secret_key=None, feed='iex', adjustment='all'):
    """Download US stock bars. Returns {symbol: bars}.

    start, end : RFC 3339 or YYYY-MM-DD
    feed       : 'iex' (free plan) or 'sip' (paid plan)
    adjustment : 'all' (splits and dividends, default), 'split', 'dividend'
                 or 'raw'
    """
    if isinstance(symbols, str):
        symbols = [symbols]
    key_id, secret = _resolve_keys(api_key_id, api_secret_key)
    headers = {'APCA-API-KEY-ID': key_id, 'APCA-API-SECRET-KEY': secret}
    params = {'timeframe': timeframe, 'start': start, 'end': end,
              'feed': feed, 'adjustment': adjustment, 'limit': 10000, 'sort': 'asc'}
    return _to_bars(_fetch_pages(STOCK_BARS_URL, params, headers, list(symbols)),
                    symbols, start, end)


def fetch_alpaca_crypto(symbols, timeframe, start, end, loc='us',
                        api_key_id=None, api_secret_key=None):
    """Download crypto bars, e.g. symbols=['BTC/USD']. No key needed; a key
    pair, if given, raises Alpaca's rate limit. Returns {symbol: bars}."""
    if isinstance(symbols, str):
        symbols = [symbols]
    headers = {}
    if api_key_id or os.environ.get('ALPACA_API_KEY_ID'):
        key_id, secret = _resolve_keys(api_key_id, api_secret_key)
        headers = {'APCA-API-KEY-ID': key_id, 'APCA-API-SECRET-KEY': secret}
    params = {'timeframe': timeframe, 'start': start, 'end': end,
              'limit': 10000, 'sort': 'asc'}
    url = CRYPTO_BARS_URL.format(loc=loc)
    return _to_bars(_fetch_pages(url, params, headers, list(symbols)),
                    symbols, start, end)
