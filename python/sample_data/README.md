# Sample data

Both files are synthetic. They are not market data and do not show any real
instrument's prices.

| File | Bars | What it is |
|---|---|---|
| `SAMPLE_5min.csv` | 1,638 five-minute bars, 2025-01-02 to 2025-01-30 | A seeded random walk. It fits inside Evaluation Mode, so it runs without a licence. |
| `AAPL.csv` | 100 daily bars over 139 days, from 2024-01-02 | A synthetic daily series named for the ticker the multi-ticker examples expect. Its span is over 30 days, so it needs a licence. |

Both use the CSV layout `rr.backtest` and `rr.load_csv` read:
`Date,Time,Open,High,Low,Close,Volume`, times in UTC.

For real bars, `../examples/fetch_and_run.py` downloads them from Alpaca or
Databento.
