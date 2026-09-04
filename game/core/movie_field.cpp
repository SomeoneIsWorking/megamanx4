#include "movie_field.h"

#include "bios_threads.h"
#include "core.h"
#include "execution_control.h"
#include "guest_execution.h"

#include <array>
#include <cstdlib>
#include <lucent/log.h>

namespace x4::movie {
namespace {

constexpr std::uint32_t kVSync = 0x800E4DB0u;

constexpr std::array<std::uint32_t, 4> kFieldReturnAddresses = {
    0x8001810Cu,
    0x8001842Cu,
    0x800185D8u,
    0x80018BC4u,
};

bool isFieldReturnAddress(std::uint32_t address) {
  for (const std::uint32_t expected : kFieldReturnAddresses) {
    if (address == expected) {
      return true;
    }
  }
  return false;
}

void fieldBoundary(Core *core) {
  if (!core) {
    lucent::error("x4-movie", "movie VSync boundary received a null Core");
    std::abort();
  }
  yieldField(core, core->r[31]);
}

} // namespace

void yieldField(Core *core, std::uint32_t returnAddress) {
  if (!core) {
    lucent::error("x4-movie", "native movie field boundary received a null Core at 0x{:08X}", returnAddress);
    std::abort();
  }
  if (core->r[31] != returnAddress || !isFieldReturnAddress(returnAddress)) {
    lucent::error("x4-movie",
                  "unauthenticated native movie field boundary argument=0x{:08X} ra=0x{:08X}",
                  returnAddress,
                  core->r[31]);
    std::abort();
  }
  core->r[2] = 0u;
  psx::cpu::requestExecutionExit(
      *core, {psx::cpu::ExecutionExitReason::FrameBoundary, returnAddress, 0u, "Mega Man X4 movie VSync"});
}

void yieldField(Core &core, std::uint32_t returnAddress, bios_threads::Service &threads) {
  if (core.r[31] != returnAddress || !isFieldReturnAddress(returnAddress)) {
    lucent::error("x4-movie",
                  "unauthenticated native movie field boundary argument=0x{:08X} ra=0x{:08X}",
                  returnAddress,
                  core.r[31]);
    std::abort();
  }

  // Unit-test seam for the host scheduler: park the existing retail task stack until X4FrameDriver
  // begins the next host-owned field, then preserve VSync(0)'s unconsumed zero result.
  threads.yieldToMain();
  core.r[2] = 0u;
}

void registerOverrides(Core &core) {
  guest::install(core, kVSync, "movie::fieldBoundary", fieldBoundary);
}

} // namespace x4::movie
