// The whole research run: ATR band reversion on one CSV, the headline
// figures printed, and the visual trade diagnostics tool opened in a browser.
// Fades a close more than two ATRs from its 20-bar mean, targets the mean and
// stops two ATRs further out. python/examples/quickstart.py is the same rule.
//
//   ./quickstart                  # python/sample_data/SAMPLE_5min.csv
//   ./quickstart bars.csv         # your own bars
//   ./quickstart --object         # the same rule as an object with on_bar
//
// A strategy is a lambda or function taking rr::Data&, or an object with
// on_bar(rr::Data&) and, optionally, a lookback member. Both forms here give
// the same result.
#include <reamer_research.hpp>
#include <algorithm>
#include <cstring>
#include <iostream>
#include "sample_bars.hpp"
namespace rr = reamer_research;

// The object form: settings and state live on the object, which can be read
// after the run.
struct AtrBands {
  size_t lookback = 20;
  double k = 2.0, qty = 10;
  int entries = 0;

  void on_bar(rr::Data& d) {
    auto c = d.close(), h = d.high(), l = d.low();
    if (c[0] == 0) return;              // warm-up: the window is still filling
    double atr = 0;
    for (size_t i = 1; i < c.size(); ++i)
      atr += std::max(h[i], c[i - 1]) - std::min(l[i], c[i - 1]);
    atr /= double(c.size() - 1);
    double mid = c.mean(), px = c.back(), band = k * atr;
    if (d.position() == 0 && px < mid - band) { ++entries; d.buy_market(qty).bracket(mid, px - band); }
    if (d.position() == 0 && px > mid + band) { ++entries; d.sell_market(qty).bracket(mid, px + band); }
  }
};

int main(int argc, char** argv) try {
  auto bars = sample_bars(argc, argv);
  bool object = argc > 1 && std::strcmp(argv[argc - 1], "--object") == 0;
  if (object) {
    AtrBands strategy;
    auto r = rr::backtest(strategy, bars, {.open_viewer = true});
    std::cout << r << "\nEntries sent   " << strategy.entries << '\n';
    return 0;
  }
  auto r = rr::backtest([](rr::Data& d) {
    auto c = d.close(), h = d.high(), l = d.low();
    if (c[0] == 0) return;              // warm-up: the window is still filling
    double atr = 0;
    for (size_t i = 1; i < c.size(); ++i)
      atr += std::max(h[i], c[i - 1]) - std::min(l[i], c[i - 1]);
    atr /= double(c.size() - 1);
    double mid = c.mean(), px = c.back();
    if (d.position() == 0 && px < mid - 2 * atr) d.buy_market(10).bracket(mid, px - 2 * atr);
    if (d.position() == 0 && px > mid + 2 * atr) d.sell_market(10).bracket(mid, px + 2 * atr);
  }, bars, {.lookback = 20, .open_viewer = true});
  std::cout << r << '\n';
} catch (const rr::Error& e) {
  std::cerr << e.what() << '\n';
  return 1;
}
