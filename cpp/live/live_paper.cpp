// Paper trading from C++ with Reamer Research alone: the quickstart's rule,
// live. python/live/live_paper.py is the same program in Python.
//
// Reamer Research makes no network calls and reads no market data feed.
// Going live takes three parts, and this program has all of them:
//   1. A bar source. Here, a CSV replayed one closed bar at a time; a live
//      feed calls the same step() with each bar as it closes.
//   2. Your strategy. The quickstart's ATR band rule, over a rolling window
//      of the last 20 bars, as a backtest's on_bar sees it.
//   3. rr::Relay, which sends the orders the rule makes to a receiver over a
//      Unix socket and reads the fills back as positions.
//
// The receiver is python/live/relay_receiver.py (standard library only),
// started by this program with a PaperBroker that fills against the bars.
// It also listens on "<socket>.bars", where this program marks each bar so
// the broker can fill what rests. For real orders, put your broker's API
// behind the receiver instead; a broker needs no bar channel.
//
//   ./live_paper                       # replay python/sample_data/SAMPLE_5min.csv
//   ./live_paper bars.csv              # replay your own bars
//   ./live_paper bars.csv --no-receiver /tmp/r.sock
//                                      # use a receiver you started yourself:
//                                      #   python3 python/live/relay_receiver.py /tmp/r.sock
//
// The relay needs a Reamer Research licence: Evaluation Mode has no live
// trading, so rr::Relay throws a licence error until one is activated.
// Linux and macOS (Windows through WSL2).
#include <reamer_research.hpp>

#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <signal.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <iostream>
#include <optional>
#include <string>
#include <thread>
#include <vector>

#include "../examples/sample_bars.hpp"
namespace rr = reamer_research;
namespace fs = std::filesystem;

constexpr size_t kLookback = 20;

// The last kLookback bars, oldest first and zero-padded while it fills, as a
// backtest's window is.
struct Window {
  std::vector<rr::Bar> bars = std::vector<rr::Bar>(kLookback);
  void push(const rr::Bar& b) {
    std::rotate(bars.begin(), bars.begin() + 1, bars.end());
    bars.back() = b;
  }
};

// The quickstart's rule (examples/quickstart.cpp), on the window and the
// position the relay reports.
std::optional<rr::Order> atr_bands(const Window& w, double position) {
  const auto& b = w.bars;
  if (b[0].close == 0) return std::nullopt;          // warm-up: the window is still filling
  double atr = 0, sum = b[0].close;
  for (size_t i = 1; i < b.size(); ++i) {
    atr += std::max(b[i].high, b[i - 1].close) - std::min(b[i].low, b[i - 1].close);
    sum += b[i].close;
  }
  atr /= double(b.size() - 1);
  double mid = sum / double(b.size()), px = b.back().close;
  if (position == 0 && px < mid - 2 * atr) return rr::buy_market(10).bracket(mid, px - 2 * atr);
  if (position == 0 && px > mid + 2 * atr) return rr::sell_market(10).bracket(mid, px + 2 * atr);
  return std::nullopt;
}

// A line-based client for the receiver's bar channel.
class BarChannel {
 public:
  explicit BarChannel(const fs::path& path) {
    fd_ = ::socket(AF_UNIX, SOCK_STREAM, 0);
    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::strncpy(addr.sun_path, path.c_str(), sizeof(addr.sun_path) - 1);
    if (fd_ < 0 || ::connect(fd_, reinterpret_cast<sockaddr*>(&addr), sizeof addr) != 0)
      throw std::runtime_error("cannot connect to the bar channel " + path.string());
  }
  ~BarChannel() { if (fd_ >= 0) ::close(fd_); }
  BarChannel(const BarChannel&) = delete;
  BarChannel& operator=(const BarChannel&) = delete;

  // Mark one bar after the relay messages sent so far; returns fills so far.
  long mark(uint64_t messages_sent, const std::string& instrument, const rr::Bar& b) {
    char line[256];
    int n = std::snprintf(line, sizeof line, "%llu %s %lld %.17g %.17g %.17g %.17g\n",
                          static_cast<unsigned long long>(messages_sent), instrument.c_str(),
                          static_cast<long long>(b.ts), b.open, b.high, b.low, b.close);
    if (::write(fd_, line, size_t(n)) != n) throw std::runtime_error("bar channel write failed");
    std::string reply;
    for (char c; reply.empty() || reply.back() != '\n';) {
      if (::read(fd_, &c, 1) != 1) throw std::runtime_error("bar channel closed");
      reply += c;
    }
    if (reply.rfind("ok ", 0) != 0) throw std::runtime_error("receiver: " + reply);
    return std::stol(reply.substr(3));
  }

 private:
  int fd_ = -1;
};

// Start python/live/relay_receiver.py on `sock` and wait for its bar channel.
pid_t start_receiver(const fs::path& sock) {
  fs::path script;
  for (const char* up : {".", "..", "../..", "../../.."}) {
    auto p = fs::path(up) / "python" / "live" / "relay_receiver.py";
    if (fs::exists(p)) { script = p; break; }
  }
  if (script.empty()) throw std::runtime_error("python/live/relay_receiver.py not found; run from the kit");
  pid_t pid = fork();
  if (pid == 0) {
    execlp("python3", "python3", script.c_str(), sock.c_str(), static_cast<char*>(nullptr));
    _exit(127);
  }
  fs::path bars = sock.string() + ".bars";
  for (int i = 0; i < 100 && !fs::exists(bars); ++i)
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  if (!fs::exists(bars)) throw std::runtime_error("the receiver did not start");
  return pid;
}

// Stops the receiver this program started, however main() ends: SIGTERM,
// then SIGKILL if it has not exited within three seconds.
struct Child {
  pid_t pid = 0;
  ~Child() {
    if (pid <= 0) return;
    kill(pid, SIGTERM);
    for (int i = 0; i < 60; ++i) {
      if (waitpid(pid, nullptr, WNOHANG) == pid) return;
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    kill(pid, SIGKILL);
    waitpid(pid, nullptr, 0);
  }
};

std::string utc(int64_t epoch) {
  std::time_t t = epoch;
  std::tm tm{};
  gmtime_r(&t, &tm);
  char out[20];
  std::strftime(out, sizeof out, "%Y-%m-%d %H:%M", &tm);
  return out;
}

int main(int argc, char** argv) try {
  fs::path csv = sample_bars(argc, argv);
  fs::path sock = fs::temp_directory_path() / "reamer-live-paper-cpp.sock";
  bool own_receiver = true;
  for (int i = 1; i < argc; ++i)
    if (std::strcmp(argv[i], "--no-receiver") == 0 && i + 1 < argc) sock = argv[i + 1], own_receiver = false;
  Child receiver;
  if (own_receiver) receiver.pid = start_receiver(sock);

  const std::string ticker = "SAMPLE";
  long fills = 0;
  BarChannel bars(sock.string() + ".bars");
  rr::Relay relay(sock, {ticker});
  Window window;
  for (const rr::Bar& bar : rr::load_csv(csv)) {
    fills = bars.mark(relay.messages_sent(), ticker, bar);  // fill what rests from earlier bars
    relay.poll(0);                                           // and read those fills back
    window.push(bar);
    double position = relay.positions()[0].qty;
    if (auto order = atr_bands(window, position)) {
      auto ids = relay.send(*order);
      std::cout << utc(bar.ts) << " sent order " << ids.front() << ", position " << position << '\n';
    }
  }
  relay.poll(100);
  auto state = relay.positions()[0];
  std::cout << fills << " fills, " << relay.orders_sent() << " orders sent, position " << state.qty
            << " at " << state.avg_entry_price << '\n';
} catch (const std::exception& e) {
  std::cerr << e.what() << '\n';
  return 1;
}
