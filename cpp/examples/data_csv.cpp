// CSV in: pass the path, or load it first to look at or fix the bars.
// python/examples/data_csv.py is the same, with the same result.
//
//   ./data_csv [bars.csv]
//
// rr::backtest takes a CSV path directly and names the ticker after the
// file. rr::load_csv reads the same file into rr::Bars when you want the bars
// in hand first, and rr::parse_csv reads text already in memory. Both read
// most vendor exports as they are: Date and Time columns or one timestamp
// column (epoch seconds, epoch milliseconds or a date string), Open, High,
// Low, Close, and Volume, Notional and Tick_count if present, in any header
// case, MetaTrader <DATE> headers, comma, semicolon or tab. Times are UTC and
// rows are sorted by time.
#include <reamer_research.hpp>
#include <iostream>
#include <sstream>
#include "sample_bars.hpp"
namespace rr = reamer_research;

// Long while the close is above its 20-bar mean, flat otherwise.
void above_mean(rr::Data& d) {
  auto c = d.close();
  if (c[0] == 0) return;                    // window still filling
  bool above = c.back() > c.mean();
  if (above && d.position() == 0) d.buy_market(10);
  if (!above && d.position() > 0) d.close_position();
}

int main(int argc, char** argv) try {
  auto path = sample_bars(argc, argv);
  std::cout << rr::backtest(above_mean, path, {.lookback = 20}) << "\n\n";

  rr::Bars bars = rr::load_csv(path);
  std::cout << bars.size() << " bars, first close " << bars.front().close << ", last close "
            << bars.back().close << '\n';
  auto r = rr::backtest(above_mean, rr::Universe{{"SAMPLE", bars}}, {.lookback = 20});
  std::cout << "from memory: " << r.closed_trades().size() << " closed trades, net P&L "
            << r.net_pnl() << '\n';

  // The same bars as a vendor export: epoch milliseconds, semicolons, newest first.
  std::ostringstream text;
  text.precision(17);
  text << "timestamp;open;high;low;close;volume\n";
  for (auto b = bars.rbegin(); b != bars.rend(); ++b)
    text << b->ts * 1000 << ';' << b->open << ';' << b->high << ';' << b->low << ';' << b->close
         << ';' << b->volume << '\n';
  rr::Bars same = rr::parse_csv(text.str());
  bool equal = same.size() == bars.size();
  for (size_t i = 0; equal && i < bars.size(); ++i)
    equal = same[i].ts == bars[i].ts && same[i].close == bars[i].close && same[i].volume == bars[i].volume;
  std::cout << "vendor layout loads the same bars: " << (equal ? "true" : "false") << '\n';
  return equal ? 0 : 1;
} catch (const rr::Error& e) {
  std::cerr << e.what() << '\n';
  return 1;
}
