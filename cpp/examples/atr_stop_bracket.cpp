// ATR breakout bracket, as an object with on_bar: the same strategy as
// python/examples/atr_stop_bracket.py, with the same result on the same bars.
//
// Every bracket_interval bars it rests a buy stop above the close (a breakout
// entry) with a take profit and stop loss attached, and a sell stop the same
// distance below, both spaced by Average True Range rather than a fixed
// offset. Whichever triggers first opens the position.
//
//   ./atr_stop_bracket [bars.csv]
#include <reamer_research.hpp>
#include <algorithm>
#include <cmath>
#include <iostream>
#include "sample_bars.hpp"
namespace rr = reamer_research;

struct AtrStopBracket {
  // Bars per window: atr_period true ranges need one bar more.
  size_t lookback = 15;
  size_t atr_period = 14;
  double atr_mult = 1.5, tp_mult = 2.0, sl_mult = 1.0, qty = 1.0;
  size_t bracket_interval = 25;
  size_t bar = 0;

  double atr(rr::Data& d) const {
    auto c = d.close(), h = d.high(), l = d.low();
    if (c.size() < atr_period + 1 || c[0] == 0) return 0;   // window still filling
    double sum = 0;
    for (size_t i = 0; i < atr_period; ++i) {
      double hi = h.ago(i), lo = l.ago(i), prev = c.ago(i + 1);
      sum += std::max({hi - lo, std::abs(hi - prev), std::abs(lo - prev)});
    }
    return sum / double(atr_period);
  }

  void on_bar(rr::Data& d) {
    if (++bar % bracket_interval != 0) return;
    double a = atr(d);
    if (a <= 0) return;
    double close = d.close().back(), offset = atr_mult * a, buy_px = close + offset;
    d.buy_stop(buy_px, qty).bracket(buy_px + tp_mult * a, buy_px - sl_mult * a);
    d.sell_stop(close - offset, qty);
  }
};

int main(int argc, char** argv) try {
  AtrStopBracket strategy;
  auto r = rr::backtest(strategy, sample_bars(argc, argv), {.open_viewer = true});
  std::cout << r << '\n';
  auto trades = r.closed_trades();
  for (size_t i = 0; i < std::min<size_t>(trades.size(), 3); ++i)
    std::cout << "trade " << i + 1 << ": entry " << trades[i].entry_price << ", exit "
              << trades[i].exit_price << ", P&L " << trades[i].net_pnl << '\n';
} catch (const rr::Error& e) {
  std::cerr << e.what() << '\n';
  return 1;
}
