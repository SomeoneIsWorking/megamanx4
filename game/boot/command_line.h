#pragma once

#include <cstdio>

namespace x4::cli {

enum class Action { Run, Help, Error };

struct Options {
  Action action = Action::Run;
  const char *executablePath = nullptr;
  const char *error = nullptr;
};

Options parse(int argc, char *const argv[]);
void printUsage(std::FILE *output, const char *program);

} // namespace x4::cli
