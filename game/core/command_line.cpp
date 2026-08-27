#include "command_line.h"

#include <cstring>

namespace x4::cli {
namespace {

constexpr const char *kDefaultExecutable = "scratch/bin/megamanx4/SLUS_005.61";

bool isHelp(const char *argument) {
  return argument && (std::strcmp(argument, "--help") == 0 || std::strcmp(argument, "-h") == 0);
}

} // namespace

Options parse(int argc, char *const argv[]) {
  if (argc <= 1) {
    return {.action = Action::Run, .executablePath = kDefaultExecutable};
  }
  if (isHelp(argv[1])) {
    return argc == 2 ? Options{.action = Action::Help}
                     : Options{.action = Action::Error, .error = "--help does not take arguments"};
  }
  if (!argv[1] || argv[1][0] == '-') {
    return {.action = Action::Error, .error = "unknown option"};
  }
  if (argc != 2) {
    return {.action = Action::Error, .error = "expected at most one executable path"};
  }
  return {.action = Action::Run, .executablePath = argv[1]};
}

void printUsage(std::FILE *output, const char *program) {
  std::fprintf(output,
               "Usage: %s [SLUS_005.61]\n"
               "\n"
               "Run the Mega Man X4 port. With no path, the executable is provisioned at\n"
               "scratch/bin/megamanx4/SLUS_005.61 from PSXPORT_X4_DISC, .env, or a local CHD.\n"
               "\n"
               "Options:\n"
               "  -h, --help  Show this help and exit.\n",
               program && *program ? program : "megamanx4_port");
}

} // namespace x4::cli
