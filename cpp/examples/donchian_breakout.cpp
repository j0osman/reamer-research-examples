#include <reamer_research.hpp>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <iostream>
#include <span>
#include <vector>

// Donchian channel breakout: the classic trend-following channel system.
//
// Entry is a buy-stop resting at the N-bar high, so the fill happens at the
// breakout level itself rather than at the next bar's open -- the channel
// boundary is a price, and a stop order is how you express that. The position
// is protected by a stop-loss at the shorter exit channel's low, which is the
// system's own reversal level; there is no take-profit, because a trend
// system's edge is in the tail it does not cut.
//
// The callback reads positions[] -- the engine's own signed exposure per
// ticker -- and that is what keeps this a single-unit reversal system.
// Emitting a fresh buy-stop every bar without checking exposure accumulates
// one position per breakout instead of replacing the resting order.
//
// The entry stop is placed GTD, good for the current bar only. A Donchian
// trigger is only valid at the level the channel holds right now, so letting
// it expire and re-placing it next bar at the new level is the correct
// lifetime -- and it avoids leaving a stale GTC stop resting at a level the
// channel has since moved away from. A GTC entry re-emitted every bar would
// instead pile up one live order per bar.
int main() {
  static const int64_t kBase = 1577836800;
  static const size_t kEntryPeriod = 20;   // breakout channel (N-bar high)
  static const size_t kExitPeriod = 10;    // exit channel (M-bar low), M < N
  static const size_t kLookback = kEntryPeriod + 1;

  // Synthetic series with a genuine trend plus mean-reverting noise, so the
  // channel is actually broken rather than oscillating inside a flat band.
  std::vector<ReamerOhlcvBar> bars(300);
  for (size_t i = 0; i < bars.size(); ++i) {
    // -1 sentinel = "not supplied, estimate from timestamp gaps" -- 0 (the
    // zero-init default) reads as "caller supplied zero ticks" and starves
    // the engine's synthetic intrabar price movement.
    bars[i].tick_count = -1;
    bars[i].ts = kBase + static_cast<int64_t>(i) * 86400;

    double t = static_cast<double>(i);
    double trend = 0.15 * t;                       // persistent drift
    double swing = 6.0 * std::sin(t / 17.0);       // multi-bar swings
    double chop = 1.2 * std::sin(t / 2.3);         // bar-to-bar noise
    double mid = 100.0 + trend + swing + chop;

    double range = 1.5 + 0.5 * std::abs(std::sin(t / 5.0));
    bars[i].open = mid - 0.25 * range;
    bars[i].high = mid + range;
    bars[i].low = mid - range;
    bars[i].close = mid + 0.25 * range;
    bars[i].volume = 5000.0 + t * 50;
  }

  // Highest high over the `period` bars ENDING ONE BAR BACK. The current bar
  // is excluded: including it would make the breakout level a function of the
  // very bar the order is meant to trigger on, which is lookahead.
  auto channel_high = [](std::span<const ReamerOhlcvBar> window,
                          size_t period) -> double {
    size_t n = window.size();
    if (n < period + 1) return -1.0;
    double hi = window[n - 1 - period].high;
    for (size_t i = n - period; i < n - 1; ++i) {
      hi = std::max(hi, window[i].high);
    }
    return hi;
  };

  auto channel_low = [](std::span<const ReamerOhlcvBar> window,
                         size_t period) -> double {
    size_t n = window.size();
    if (n < period + 1) return -1.0;
    double lo = window[n - 1 - period].low;
    for (size_t i = n - period; i < n - 1; ++i) {
      lo = std::min(lo, window[i].low);
    }
    return lo;
  };

  // Formats an epoch second as the engine's timestamp string, matching the
  // format closed trades come back in.
  auto format_ts = [](int64_t epoch, char* out, size_t cap) {
    std::time_t t = static_cast<std::time_t>(epoch);
    std::tm tm_utc{};
    gmtime_r(&t, &tm_utc);
    std::strftime(out, cap, "%Y-%m-%d %H:%M:%S", &tm_utc);
  };

  struct DonchianState {
    size_t entries_emitted = 0;
    size_t exits_emitted = 0;
    size_t suppressed_while_long = 0;
  };
  DonchianState state;

  auto on_bar = [&](std::span<const ReamerOhlcvBar> window, size_t ticker_count,
                     std::span<const double> positions,
                     std::span<const uint8_t> /*window_valid*/,
                     std::span<const ReamerPositionState> /*position_states*/,
                     std::span<const ReamerOpenOrder> /*open_orders*/,
                     std::span<ReamerOrderRequest> out_orders,
                     std::span<ReamerOrderAction> /*out_actions*/, size_t& /*action_count*/) -> size_t {
    if (out_orders.empty() || ticker_count == 0 || positions.empty()) return 0;

    double entry_hi = channel_high(window, kEntryPeriod);
    double exit_lo = channel_low(window, kExitPeriod);
    if (entry_hi <= 0.0 || exit_lo <= 0.0) return 0;

    int64_t bar_ts_now = window.back().ts;

    // Already long: no new entry. Instead maintain the trailing exit -- a
    // sell-stop at the CURRENT exit-channel low, re-placed each bar so it
    // follows the channel up. A bracket stop_loss cannot do this: it is a
    // fixed level fixed at entry, so it would sit at the channel low as it
    // stood on the entry bar and never ratchet. The trailing exit channel is
    // the whole system, so it has to be an order the strategy re-places.
    if (positions[0] > 0.0) {
      state.suppressed_while_long++;

      ReamerOrderRequest exit = {};
      exit.ticker_id = 0;
      exit.order_type = REAMER_RESEARCH_ORDER_TYPE_SELL_STOP;
      exit.kind = REAMER_RESEARCH_ORDER_KIND_STOP;
      exit.side = REAMER_RESEARCH_SIDE_SELL;
      exit.tif = REAMER_RESEARCH_TIF_GTD;
      format_ts(bar_ts_now + 2 * 86400, exit.expiry_timestamp,
                sizeof(exit.expiry_timestamp));
      exit.valid = true;
      exit.is_close = true;             // close the open position, whatever its size
      exit.qty = positions[0];
      exit.stop_price = exit_lo;
      out_orders[0] = exit;

      state.exits_emitted++;
      return 1;
    }

    // The exit channel must sit below the entry trigger, or the protective
    // stop would be through the fill on arrival.
    if (exit_lo >= entry_hi) return 0;

    // Bar-origin orders are only eligible from the NEXT bar, so a GTD expiry
    // at the next bar's own epoch would expire it before it could ever fill.
    // Expire one bar later: eligible for exactly the next bar, then gone.
    int64_t expiry_ts = bar_ts_now + 2 * 86400;

    ReamerOrderRequest entry = {};
    entry.ticker_id = 0;
    entry.order_type = REAMER_RESEARCH_ORDER_TYPE_BUY_STOP;
    entry.kind = REAMER_RESEARCH_ORDER_KIND_STOP;
    entry.side = REAMER_RESEARCH_SIDE_BUY;
    entry.tif = REAMER_RESEARCH_TIF_GTD;
    format_ts(expiry_ts, entry.expiry_timestamp, sizeof(entry.expiry_timestamp));
    entry.valid = true;
    entry.qty = 1.0;
    entry.stop_price = entry_hi;
    // No bracket stop_loss: the exit is the trailing channel order placed on
    // subsequent bars above. A fixed bracket level would fight it.
    out_orders[0] = entry;

    state.entries_emitted++;
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
      {{bars}}, {"SYNTH"}, on_bar, config, 10000.0, 1.0, kLookback);

  if (!result) {
    std::cerr << "Backtest failed\n";
    return 1;
  }

  auto summary = result->summary();
  auto trades = result->closed_trades();

  std::cout << "Donchian Channel Breakout (" << kEntryPeriod << "/"
            << kExitPeriod << ")\n";
  std::cout << "======================================\n";
  std::cout << "Bars: " << bars.size() << "\n";
  std::cout << "Entry stops placed: " << state.entries_emitted << "\n";
  std::cout << "Trailing exit stops placed: " << state.exits_emitted << "\n";
  std::cout << "Gross PnL: " << summary.gross_pnl << "\n";
  std::cout << "Net PnL: " << summary.net_pnl << "\n";
  std::cout << "Total Fees: " << summary.total_fees << "\n";
  std::cout << "Total Trades: " << summary.trades << "\n";
  std::cout << "Closed Trades: " << summary.closed_trades_count << "\n";

  for (size_t i = 0; i < trades.size(); ++i) {
    std::cout << "Trade " << (i + 1) << " [" << trades[i].ticker << "] "
              << trades[i].open_timestamp << " -> " << trades[i].close_timestamp
              << "  entry " << trades[i].entry_price << "  exit "
              << trades[i].exit_price << "  qty " << trades[i].qty << "  pnl "
              << trades[i].net_pnl << "\n";
  }

  return 0;
}
