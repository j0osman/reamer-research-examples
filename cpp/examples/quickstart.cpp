// The whole research run: ATR band reversion on one CSV, the headline
// figures printed, and the visual trade diagnostics tool opened in a browser. Fades a close
// more than two ATRs from its 20-bar mean, targets the mean and stops two
// ATRs further out.
//
//   ./quickstart AAPL.csv
#include <reamer_research.hpp>
#include <algorithm>
#include <iostream>
namespace rr = reamer_research;

int main(int argc, char** argv) {
  auto r = rr::backtest([](rr::Data& d) {
    auto c = d.close(), h = d.high(), l = d.low();
    if (c[0] == 0) return;                // warm-up: the window is still filling
    double atr = 0;
    for (size_t i = 1; i < c.size(); ++i)
      atr += std::max(h[i], c[i - 1]) - std::min(l[i], c[i - 1]);
    atr /= double(c.size() - 1);
    double mid = c.mean(), px = c.back();
    if (d.position() == 0 && px < mid - 2 * atr) d.buy_market(10).bracket(mid, px - 2 * atr);
    if (d.position() == 0 && px > mid + 2 * atr) d.sell_market(10).bracket(mid, px + 2 * atr);
  }, argc > 1 ? argv[1] : "AAPL.csv", {.lookback = 20, .open_viewer = true});
  std::cout << r << '\n';
}
