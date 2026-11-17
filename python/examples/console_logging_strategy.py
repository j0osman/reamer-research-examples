import sys


class ConsoleLoggingStrategy:
    """Exercises every console output path for ConsoleWidget testing."""
    lookback = 1
    ticker = "AAPL"

    def __init__(self, config_path=None):
        self._step = 0
        print("[init] ConsoleLoggingStrategy loaded")

    def on_bar(self, data):
        ticker = self.ticker
        tv = data[ticker]
        if not tv.valid:
            return None

        step = self._step
        self._step += 1
        close = float(tv.close[-1])

        print(f"[bar {step}] close={close:.4f}")

        if step % 10 == 0:
            print(
                f"[milestone] bar {step}\n"
                f"  open={float(tv.open[-1]):.4f}  high={float(tv.high[-1]):.4f}\n"
                f"  low={float(tv.low[-1]):.4f}   vol={float(tv.volume[-1]):.0f}"
            )

        if step == 5:
            print("[unicode] € £ ¥ α β γ < > & \" '")

        if step == 20:
            print("[warn] position size capped by risk limit")

        if step == 30:
            print("[error] unexpected config value, using default", file=sys.stderr)

        if step == 40:
            print("[long] " + "x" * 200)

        return None
