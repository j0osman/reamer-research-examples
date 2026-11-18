// Donchian channel breakout, as a plain function: the classic trend system.
//
// Flat, it rests a buy stop at the 20-bar high, so the fill is at the
// breakout level itself rather than the next bar's open. The stop is good
// for two bars (GTD) and re-placed at the channel's new level after that,
// so no stale entry rests where the channel used to be. Long, it trails the
// position's stop loss up to the 10-bar low with modify_position, which is
// the system's own exit. There is no take profit: a trend system's edge is
// in the tail it does not cut.
//
// Both channels end one bar back. Including the current bar would make the
// breakout level depend on the bar the order is meant to trigger on.
//
//   ./donchian_breakout [bars.csv]
#include <reamer_research.hpp>
#include <algorithm>
#include <ctime>
#include <iostream>
#include <string>
#include "sample_bars.hpp"
namespace rr = reamer_research;

constexpr size_t kEntry = 20, kExit = 10;

// Highest high or lowest low over `period` bars, ending one bar back.
double channel_high(const rr::Column& h, size_t period) {
  double hi = h.ago(1);
  for (size_t k = 2; k <= period; ++k) hi = std::max(hi, h.ago(k));
  return hi;
}
double channel_low(const rr::Column& l, size_t period) {
  double lo = l.ago(1);
  for (size_t k = 2; k <= period; ++k) lo = std::min(lo, l.ago(k));
  return lo;
}

// An epoch second as an expiry timestamp EXECUTION_SPEC.md accepts.
std::string utc(int64_t epoch) {
  std::time_t t = epoch;
  std::tm tm{};
  gmtime_r(&t, &tm);
  char out[32];
  std::strftime(out, sizeof out, "%Y-%m-%d %H:%M:%S", &tm);
  return out;
}

int entries = 0;

void donchian(rr::Data& d) {
  auto h = d.high(), l = d.low(), c = d.close();
  if (c[0] == 0) return;                          // window still filling
  double entry_hi = channel_high(h, kEntry), exit_lo = channel_low(l, kExit);

  if (d.position() > 0) {                         // long: trail the exit
    d.modify_position(0, exit_lo);
    return;
  }
  if (!d.open_orders().empty() || exit_lo >= entry_hi) return;
  int64_t bar_secs = d.bar(0).ts - d.bar(1).ts;
  // An order is eligible from the next bar, so expire it two bars out.
  d.buy_stop(entry_hi, 1).gtd(utc(d.ts() + 2 * bar_secs));
  ++entries;
}

int main(int argc, char** argv) try {
  auto r = rr::backtest(donchian, sample_bars(argc, argv), {.lookback = kEntry + 1});
  std::cout << r << "\nEntry stops placed  " << entries << '\n';
} catch (const rr::Error& e) {
  std::cerr << e.what() << '\n';
  return 1;
}
