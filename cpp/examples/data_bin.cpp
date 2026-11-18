// Binary .bin files: convert once, then every run memory-maps the file.
// python/examples/data_bin.py is the same, with the same result.
//
//   ./data_bin [bars.csv]
//
// A .bin holds the bars in the engine's own 64-byte layout. When every file
// passed to rr::backtest is a .bin, the engine maps them in place, so a run
// starts with no parse step and data larger than RAM still runs. Options
// start and end pick a time range inside the file without rewriting it.
// rr::write_bin and rr::read_bin need no licence; the kit's
// bin/reamer-csv-build converts a CSV from the command line. A .bin that a
// Python fetcher wrote with rr.write_bin loads here unchanged.
#include <reamer_research.hpp>
#include <cstring>
#include <filesystem>
#include <iostream>
#include "sample_bars.hpp"
namespace rr = reamer_research;
namespace fs = std::filesystem;

// Long while the close is above its 20-bar mean, flat otherwise.
void above_mean(rr::Data& d) {
  auto c = d.close();
  if (c[0] == 0) return;
  bool above = c.back() > c.mean();
  if (above && d.position() == 0) d.buy_market(10);
  if (!above && d.position() > 0) d.close_position();
}

int main(int argc, char** argv) try {
  auto src = sample_bars(argc, argv);
  fs::path out = fs::temp_directory_path() / "reamer-data-bin-example" / "SAMPLE.bin";
  fs::create_directories(out.parent_path());

  rr::Bars csv = rr::load_csv(src);
  rr::write_bin(out, csv);
  std::cout << "wrote " << out.string() << " (" << fs::file_size(out) << " bytes)\n";

  std::cout << rr::backtest(above_mean, out, {.lookback = 20}) << "\n\n";

  rr::Bars bars = rr::read_bin(out);
  int64_t middle = bars[bars.size() / 2].ts;
  auto half = rr::backtest(above_mean, std::vector<fs::path>{out}, {.lookback = 20, .start = middle});
  std::cout << "from the middle: " << half.closed_trades().size() << " closed trades, net P&L "
            << half.net_pnl() << '\n';

  bool exact = bars.size() == csv.size();
  for (size_t i = 0; exact && i < bars.size(); ++i)
    exact = std::memcmp(&bars[i], &csv[i], sizeof(rr::Bar)) == 0;
  std::cout << "round trip exact: " << (exact ? "true" : "false") << '\n';
  fs::remove_all(out.parent_path());
  return exact ? 0 : 1;
} catch (const rr::Error& e) {
  std::cerr << e.what() << '\n';
  return 1;
}
