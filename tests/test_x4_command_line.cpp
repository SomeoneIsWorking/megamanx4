#include "command_line.h"

#include <cstdio>
#include <cstring>

namespace {

bool check(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "x4_command_line: %s\n", message);
  }
  return condition;
}

} // namespace

int main() {
  char program[] = "megamanx4_port";
  char help[] = "--help";
  char shortHelp[] = "-h";
  char executable[] = "scratch/custom/SLUS_005.61";
  char unknown[] = "--unknown";
  char extra[] = "extra";

  char *defaultArgv[] = {program};
  const x4::cli::Options defaults = x4::cli::parse(1, defaultArgv);
  if (!check(defaults.action == x4::cli::Action::Run && defaults.executablePath != nullptr &&
                 std::strcmp(defaults.executablePath, "scratch/bin/megamanx4/SLUS_005.61") == 0,
             "zero arguments did not select the shipping executable path")) {
    return 1;
  }

  char *helpArgv[] = {program, help};
  char *shortHelpArgv[] = {program, shortHelp};
  if (!check(x4::cli::parse(2, helpArgv).action == x4::cli::Action::Help &&
                 x4::cli::parse(2, shortHelpArgv).action == x4::cli::Action::Help,
             "help options were not recognized before provisioning")) {
    return 1;
  }

  char *pathArgv[] = {program, executable};
  const x4::cli::Options path = x4::cli::parse(2, pathArgv);
  if (!check(path.action == x4::cli::Action::Run && path.executablePath == executable,
             "explicit executable path was not preserved")) {
    return 1;
  }

  char *unknownArgv[] = {program, unknown};
  char *extraArgv[] = {program, executable, extra};
  if (!check(x4::cli::parse(2, unknownArgv).action == x4::cli::Action::Error &&
                 x4::cli::parse(3, extraArgv).action == x4::cli::Action::Error,
             "invalid options could still be interpreted as extraction targets")) {
    return 1;
  }

  std::puts("x4_command_line: help, default, explicit path, and refusal contracts passed");
  return 0;
}
