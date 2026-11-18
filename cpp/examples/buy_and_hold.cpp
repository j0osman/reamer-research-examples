// Buy and hold, as a lambda: one market buy on the first full window, held to
// the last bar. The engine closes what is still open at the end of the run,
// so the result has one closed trade. python/templates/buy_and_hold.py is
// the same strategy.
//
//   ./buy_and_hold [bars.csv]
#include <reamer_research.hpp>
#include <iostream>
#include "sample_bars.hpp"
namespace rr = reamer_research;

int main(int argc, char** argv) try {
  bool bought = false;
  auto r = rr::backtest([&](rr::Data& d) {
    if (!bought && d.position() == 0) {
      d.buy_market(1);
      bought = true;
    }
  }, sample_bars(argc, argv), {.lookback = 1});

  std::cout << r << '\n';
  for (const auto& t : r.closed_trades())
    std::cout << "held " << t.open_timestamp << " -> " << t.close_timestamp << ", entry "
              << t.entry_price << ", exit " << t.exit_price << ", P&L " << t.net_pnl << '\n';
} catch (const rr::Error& e) {
  std::cerr << e.what() << '\n';
  return 1;
}
