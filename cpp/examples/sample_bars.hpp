// Where the examples find their bars: the path given on the command line,
// else the sample bars the Python examples use, python/sample_data/
// SAMPLE_5min.csv (1,638 five-minute bars over 28 days, inside Evaluation
// Mode), looked for from the kit or repository root and from the
// directories below it that the examples are built and run in.
#pragma once
#include <filesystem>
#include <initializer_list>

inline std::filesystem::path sample_bars(int argc, char** argv, const char* name = "SAMPLE_5min.csv") {
  if (argc > 1 && argv[1][0] != '-') return argv[1];
  for (const char* up : {".", "..", "../..", "../../.."}) {
    auto p = std::filesystem::path(up) / "python" / "sample_data" / name;
    if (std::filesystem::exists(p)) return p.lexically_normal();
  }
  return name;
}
