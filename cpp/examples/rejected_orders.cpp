// Reading rejected orders out of a result.
//
// A run whose orders are all rejected still succeeds: it returns a result
// with a summary, one that reports no trades. What separates "the strategy
// saw no setup" from "every order it sent was malformed" is the order log,
// which comes back in the result JSON with a reject_reason on each refused
// order. This strategy, an object with on_bar, sends one good order and
// three bad ones, then the program reads back what the engine did with each.
//
// The bad orders are deliberate. Copy the part at the bottom that inspects
// the outcome, not the order construction.
//
//   ./rejected_orders [bars.csv]
#include <reamer_research.hpp>
#include <cmath>
#include <iostream>
#include <limits>
#include <string>
#include "sample_bars.hpp"
namespace rr = reamer_research;

struct BadOrders {
  size_t lookback = 1;
  int bar = 0;

  void on_bar(rr::Data& d) {
    ReamerOrderRequest raw{};
    raw.valid = true;
    raw.order_type = REAMER_RESEARCH_ORDER_TYPE_BUY;
    raw.kind = REAMER_RESEARCH_ORDER_KIND_MARKET;
    raw.side = REAMER_RESEARCH_SIDE_BUY;
    raw.tif = REAMER_RESEARCH_TIF_GTC;
    raw.qty = 1;
    switch (++bar) {
      case 1:                       // good: this one fills
        d.buy_market(1);
        return;
      case 2:                       // a NaN quantity passes a `qty <= 0` guard
        raw.qty = std::nan("");
        break;
      case 3:                       // an unbounded limit price passes a `> 0` guard
        raw.order_type = REAMER_RESEARCH_ORDER_TYPE_BUY_LIMIT;
        raw.kind = REAMER_RESEARCH_ORDER_KIND_LIMIT;
        raw.limit_price = std::numeric_limits<double>::infinity();
        break;
      case 4:                       // an enum cast from an unchecked integer
        raw.side = static_cast<ReamerResearchSide>(7);
        break;
      default:
        return;
    }
    d.submit(raw);
  }
};

// A substring scan over the result JSON, to keep the example free of a JSON
// library. A real integration parses order_log with the one it already uses.
int print_rejections(const std::string& json) {
  const std::string key = "\"reject_reason\":";
  int found = 0;
  for (size_t pos = 0; (pos = json.find(key, pos)) != std::string::npos;) {
    size_t open = json.find('"', pos + key.size());
    if (open == std::string::npos) break;
    size_t close = json.find('"', open + 1);
    if (close == std::string::npos) break;
    std::string reason = json.substr(open + 1, close - open - 1);
    if (!reason.empty()) {
      std::cout << "  rejected: " << reason << '\n';
      ++found;
    }
    pos = close + 1;
  }
  return found;
}

int main(int argc, char** argv) try {
  BadOrders strategy;
  auto r = rr::backtest(strategy, sample_bars(argc, argv));

  // The run succeeded. That says nothing about whether the orders did.
  std::cout << "Orders sent     4\nClosed trades   " << r.closed_trades().size()
            << "\nNet P&L         " << r.net_pnl() << "\n\nWhat the engine refused, and why:\n";
  int n = print_rejections(r.json());
  if (n == 0) std::cout << "  (no rejections)\n";
  std::cout << "\nEach names the field that was wrong. A run that trades less than\n"
               "expected is usually this, not the market.\n";
  return n == 3 ? 0 : 1;
} catch (const rr::Error& e) {
  std::cerr << e.what() << '\n';
  return 1;
}
