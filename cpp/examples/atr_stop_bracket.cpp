#include <reamer_research.hpp>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <span>
#include <vector>

// ATR breakout-bracket strategy: matches python/examples/
// atr_stop_bracket.py. Every bracket_interval bars, place a buy-stop
// above the current close (breakout entry) with a TP/SL bracket attached,
// spaced off Average True Range rather than a fixed offset.
int main() {
  static const int64_t kBase = 1577836800;
  static const size_t kAtrPeriod = 14;
  static const size_t kBracketInterval = 25;
  static const double kAtrMult = 1.5;
  static const double kTpMult = 2.0;
  static const double kSlMult = 1.0;

  std::vector<ReamerOhlcvBar> bars(150);
  for (size_t i = 0; i < bars.size(); ++i) {
    // -1 sentinel = "not supplied, estimate from timestamp gaps" -- 0 (the
    // zero-init default) reads as "caller supplied zero ticks" and starves
    // the engine's synthetic intrabar price movement.
    bars[i].tick_count = -1;
    bars[i].ts = kBase + static_cast<int64_t>(i) * 86400;
    double base_price = 100.0 + (static_cast<double>(i % 20) * 0.5 - 5.0);
    bars[i].open = base_price;
    bars[i].high = base_price + 2.0;
    bars[i].low = base_price - 2.0;
    bars[i].close = base_price + (i % 7 == 0 ? 1.0 : -0.5);
    bars[i].volume = 5000.0 + static_cast<double>(i) * 50;
  }

  struct AtrBracketState {
    size_t bar_index = 0;
  };
  AtrBracketState state;

  auto atr = [](std::span<const ReamerOhlcvBar> window) -> double {
    if (window.size() < kAtrPeriod + 1) return -1.0;
    double sum_tr = 0.0;
    size_t n = window.size();
    for (size_t i = 0; i < kAtrPeriod; ++i) {
      const auto& bar = window[n - 1 - i];
      const auto& prev = window[n - 2 - i];
      double tr = std::max({bar.high - bar.low, std::abs(bar.high - prev.close),
                             std::abs(bar.low - prev.close)});
      sum_tr += tr;
    }
    return sum_tr / static_cast<double>(kAtrPeriod);
  };

  auto on_bar = [&](std::span<const ReamerOhlcvBar> window, size_t ticker_count,
                     std::span<const double> /*positions*/,
                     std::span<const uint8_t> /*window_valid*/,
                     std::span<const ReamerPositionState> /*position_states*/,
                     std::span<const ReamerOpenOrder> /*open_orders*/,
                     std::span<ReamerOrderRequest> out_orders,
                     std::span<ReamerOrderAction> /*out_actions*/, size_t& /*action_count*/) -> size_t {
    state.bar_index++;
    if (out_orders.size() < 2 || ticker_count == 0) return 0;
    if (state.bar_index % kBracketInterval != 0) return 0;

    double atr_value = atr(window);
    if (atr_value <= 0.0) return 0;

    double close = window.back().close;
    double offset = kAtrMult * atr_value;
    double buy_px = close + offset;

    ReamerOrderRequest entry = {};
    entry.ticker_id = 0;
    entry.order_type = REAMER_RESEARCH_ORDER_TYPE_BUY_STOP;
    entry.kind = REAMER_RESEARCH_ORDER_KIND_STOP;
    entry.side = REAMER_RESEARCH_SIDE_BUY;
    entry.tif = REAMER_RESEARCH_TIF_GTC;
    entry.valid = true;
    entry.qty = 1.0;
    entry.stop_price = buy_px;
    entry.take_profit = buy_px + kTpMult * atr_value;
    entry.stop_loss = buy_px - kSlMult * atr_value;
    out_orders[0] = entry;

    ReamerOrderRequest invalidation = {};
    invalidation.ticker_id = 0;
    invalidation.order_type = REAMER_RESEARCH_ORDER_TYPE_SELL_STOP;
    invalidation.kind = REAMER_RESEARCH_ORDER_KIND_STOP;
    invalidation.side = REAMER_RESEARCH_SIDE_SELL;
    invalidation.tif = REAMER_RESEARCH_TIF_GTC;
    invalidation.valid = true;
    invalidation.qty = 1.0;
    invalidation.stop_price = close - offset;
    out_orders[1] = invalidation;

    return 2;
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
      {{bars}}, {"SYNTH"}, on_bar, config, 10000.0, 1.0, kAtrPeriod + 1);

  if (!result) {
    std::cerr << "Backtest failed\n";
    return 1;
  }

  auto summary = result->summary();
  auto trades = result->closed_trades();

  std::cout << "ATR Breakout-Bracket Strategy Results\n";
  std::cout << "======================================\n";
  std::cout << "Gross PnL: " << summary.gross_pnl << "\n";
  std::cout << "Net PnL: " << summary.net_pnl << "\n";
  std::cout << "Total Trades: " << summary.trades << "\n";
  std::cout << "Closed Trades: " << summary.closed_trades_count << "\n";

  if (!trades.empty()) {
    for (size_t i = 0; i < trades.size(); ++i) {
      std::cout << "Trade " << (i + 1) << ":\n";
      std::cout << "  Entry Price: " << trades[i].entry_price << "\n";
      std::cout << "  Exit Price: " << trades[i].exit_price << "\n";
      std::cout << "  Qty: " << trades[i].qty << "\n";
      std::cout << "  PnL: " << trades[i].net_pnl << "\n";
    }
  }

  return 0;
}
