#include <reamer_research.hpp>
#include <iostream>
#include <span>
#include <vector>
#include <cstdint>

int main() {
  static const int64_t kBase = 1577836800;

  std::vector<ReamerOhlcvBar> bars(5);
  // ReamerOhlcvBar zero-inits on construction; tick_count's -1 sentinel
  // ("not supplied, estimate from timestamp gaps") must be set explicitly --
  // left at 0 it reads as "caller supplied zero ticks" and the backtest
  // engine never generates intrabar price movement for the strategy to
  // trade against.
  for (auto& b : bars) b.tick_count = -1;

  bars[0].ts = kBase + 0 * 86400;
  bars[0].open = 100.0;
  bars[0].high = 101.0;
  bars[0].low = 99.0;
  bars[0].close = 100.5;
  bars[0].volume = 1000.0;

  bars[1].ts = kBase + 1 * 86400;
  bars[1].open = 100.5;
  bars[1].high = 102.0;
  bars[1].low = 100.0;
  bars[1].close = 101.0;
  bars[1].volume = 1200.0;

  bars[2].ts = kBase + 2 * 86400;
  bars[2].open = 101.0;
  bars[2].high = 103.0;
  bars[2].low = 101.0;
  bars[2].close = 102.0;
  bars[2].volume = 1100.0;

  bars[3].ts = kBase + 3 * 86400;
  bars[3].open = 102.0;
  bars[3].high = 102.5;
  bars[3].low = 101.5;
  bars[3].close = 102.0;
  bars[3].volume = 1000.0;

  bars[4].ts = kBase + 4 * 86400;
  bars[4].open = 102.0;
  bars[4].high = 103.5;
  bars[4].low = 101.5;
  bars[4].close = 103.0;
  bars[4].volume = 1300.0;

  struct BuyAndHoldState {
    int bar_count = 0;
    int current_bar = 0;
    bool bought = false;
  };

  BuyAndHoldState state;
  state.bar_count = 5;

  auto on_bar = [&state](std::span<const ReamerOhlcvBar> window,
                          size_t ticker_count,
                          std::span<const double> /*positions*/,
                          std::span<const uint8_t> /*window_valid*/,
                          std::span<const ReamerPositionState> /*position_states*/,
                          std::span<const ReamerOpenOrder> /*open_orders*/,
                          std::span<ReamerOrderRequest> out_orders,
                          std::span<ReamerOrderAction> /*out_actions*/, size_t& /*action_count*/) -> size_t {
    state.current_bar++;

    if (out_orders.empty()) {
      return 0;
    }

    if (state.current_bar == 1 && ticker_count > 0 && !state.bought) {
      ReamerOrderRequest order = {};
      order.ticker_id = 0;
      order.order_type = REAMER_RESEARCH_ORDER_TYPE_BUY;
      order.kind = REAMER_RESEARCH_ORDER_KIND_MARKET;
      order.side = REAMER_RESEARCH_SIDE_BUY;
      order.tif = REAMER_RESEARCH_TIF_GTC;
      order.valid = true;
      order.qty = 1.0;
      out_orders[0] = order;
      state.bought = true;
      return 1;
    }

    if (state.current_bar == state.bar_count && ticker_count > 0) {
      ReamerOrderRequest order = {};
      order.ticker_id = 0;
      order.is_close = true;
      order.valid = true;
      order.qty = 0;
      out_orders[0] = order;
      return 1;
    }

    return 0;
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

  if (!result) {
    std::cerr << "Backtest failed\n";
    return 1;
  }

  auto summary = result->summary();
  auto trades = result->closed_trades();

  std::cout << "Buy-and-Hold Strategy Results\n";
  std::cout << "=============================\n";
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
