// Reading rejected orders out of a result.
//
// A backtest that rejects every order it was handed still SUCCEEDS. It returns
// a valid handle and a summary -- one reporting zero trades. Nothing about the
// return value distinguishes "the strategy saw no setup" from "every order the
// strategy sent was malformed".
//
// That distinction lives in the order log, which reaches the caller through
// the result JSON document, not through summary() or closed_trades(). This
// example submits one good order and three bad ones, then reads back what the
// engine did with each.
//
// The strategy here is deliberately wrong. Do not copy its order construction;
// copy the part at the bottom that inspects the outcome.

#include <reamer_research.hpp>

#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <span>
#include <string>
#include <vector>

namespace {

// Minimal substring scan over the result document. A real integration parses
// the JSON with whatever library it already uses; pulling in a parser for a
// reference example would obscure the point, which is that the data is there.
void print_rejections(const std::string& json) {
  size_t pos = 0;
  int found = 0;
  const std::string key = "\"reject_reason\":";

  while ((pos = json.find(key, pos)) != std::string::npos) {
    const size_t open_quote = json.find('"', pos + key.size());
    if (open_quote == std::string::npos) break;
    const size_t close_quote = json.find('"', open_quote + 1);
    if (close_quote == std::string::npos) break;

    const std::string reason =
        json.substr(open_quote + 1, close_quote - open_quote - 1);
    if (!reason.empty()) {
      std::cout << "  rejected: " << reason << "\n";
      ++found;
    }
    pos = close_quote + 1;
  }

  if (found == 0) {
    std::cout << "  (no rejections)\n";
  }
}

}  // namespace

int main() {
  static const int64_t kBase = 1577836800;

  std::vector<ReamerOhlcvBar> bars(6);
  // tick_count's -1 sentinel means "estimate from timestamp gaps"; left at 0
  // it reads as "zero ticks supplied" and no intrabar movement is generated.
  for (auto& b : bars) b.tick_count = -1;

  for (size_t i = 0; i < bars.size(); ++i) {
    bars[i].ts = kBase + static_cast<int64_t>(i) * 86400;
    bars[i].open = 100.0 + i;
    bars[i].high = 102.0 + i;
    bars[i].low = 98.0 + i;
    bars[i].close = 100.0 + i;
    bars[i].volume = 1000.0;
  }

  struct State {
    int bar = 0;
  };
  State state;

  auto on_bar = [&state](std::span<const ReamerOhlcvBar> window,
                         size_t ticker_count,
                         std::span<const double> /*positions*/,
                         std::span<const uint8_t> /*window_valid*/,
                         std::span<const ReamerPositionState> /*position_states*/,
                         std::span<const ReamerOpenOrder> /*open_orders*/,
                         std::span<ReamerOrderRequest> out_orders,
                         std::span<ReamerOrderAction> /*out_actions*/, size_t& /*action_count*/) -> size_t {
    state.bar++;

    if (out_orders.empty() || ticker_count == 0) {
      return 0;
    }

    ReamerOrderRequest order = {};
    order.ticker_id = 0;
    order.order_type = REAMER_RESEARCH_ORDER_TYPE_BUY;
    order.kind = REAMER_RESEARCH_ORDER_KIND_MARKET;
    order.side = REAMER_RESEARCH_SIDE_BUY;
    order.tif = REAMER_RESEARCH_TIF_GTC;
    order.valid = true;
    order.qty = 1.0;

    switch (state.bar) {
      case 1:
        // Good: this one fills.
        break;

      case 2:
        // A quantity computed from an empty window, or divided by a zero
        // that a guard missed. NaN is not caught by a `qty <= 0` check --
        // every comparison against NaN is false -- so it must be rejected
        // where it crosses the ABI, and it is.
        order.qty = std::nan("");
        break;

      case 3:
        // A limit price from an unbounded calculation. Passes a `> 0` guard.
        order.order_type = REAMER_RESEARCH_ORDER_TYPE_BUY_LIMIT;
        order.kind = REAMER_RESEARCH_ORDER_KIND_LIMIT;
        order.limit_price = std::numeric_limits<double>::infinity();
        break;

      case 4:
        // An enum from an integer that was never range-checked -- the shape
        // of a bug where a strategy maps its own signal type onto the ABI's.
        order.side = static_cast<ReamerResearchSide>(7);
        break;

      default:
        return 0;
    }

    out_orders[0] = order;
    return 1;
  };

  ReamerBacktestConfig config = {};
  config.commission_per_unit = 0.0;
  config.commission_mode = REAMER_RESEARCH_COMMISSION_ROUND_TRIP;
  config.slippage = 0.0;
  config.price_volatility = 0.0;
  config.spread = 0.0;
  config.ohlcv_type = REAMER_RESEARCH_OHLCV_BID;
  config.rng_seed = 42;
  config.roll_cycle_months_count = 0;
  config.roll_days_before_monthend = 5;

  auto result = reamer_research_ref::run_backtest(
      {{bars}}, {"SYNTH"}, on_bar, config, 10000.0, 1.0, 1);

  // This checks that the RUN succeeded. It says nothing about whether the
  // orders did.
  if (!result) {
    std::cerr << "Backtest failed\n";
    return 1;
  }

  auto summary = result->summary();

  std::cout << "Rejected-order handling\n";
  std::cout << "=======================\n";
  std::cout << "Run status:    SUCCESS (a rejected order is not a failed run)\n";
  std::cout << "Orders sent:   4\n";
  std::cout << "Trades:        " << summary.trades << "\n";
  std::cout << "Net PnL:       " << summary.net_pnl << "\n\n";

  // Everything above is what a caller sees by default, and it is not enough:
  // three of four orders never reached the book, and nothing so far says so.
  const std::string json = result->result_json();
  if (json.empty()) {
    std::cerr << "could not read result document\n";
    return 1;
  }

  std::cout << "What the engine refused, and why:\n";
  print_rejections(json);

  std::cout << "\nEach names the field that was wrong. Surface these to\n"
               "whoever owns the strategy -- a run that trades less than\n"
               "expected is usually this, not the market.\n";

  return 0;
}
