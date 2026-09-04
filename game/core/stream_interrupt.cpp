#include "stream_interrupt.h"

#include "core.h"
#include "guest_execution.h"

#include <cstdlib>
#include <lucent/log.h>

namespace x4::stream_interrupt {
namespace {

// callback 0x800E7944 publishes the libcd sync result through this byte before dispatching the
// callback stored at 0x8011DD20. CD_ready 0x800E6B48 normally consumes and clears the same byte,
// except for CdlDataReady: that interrupt also publishes the higher-priority ready result below.
constexpr std::uint32_t kSyncResult = 0x8011DFF9u;
constexpr std::uint32_t kDataReadyResult = 0x8011DFFAu;
constexpr std::uint32_t kDataReadyResponse = 0x8013BA88u;
constexpr std::uint32_t kResponseBytes = 8u;

struct CallbackScope {
  Core *core = nullptr;
  std::uint32_t status = 0u;
  std::uint32_t response = 0u;
  bool consumed = false;
};

// The guest and its IRQ callback execute serially on one host thread. Keeping this lexical scope
// thread-local prevents a second Game/Core from borrowing another core's callback response.
thread_local CallbackScope g_scope;

class ScopeReset final {
public:
  ~ScopeReset() {
    g_scope = {};
  }
};

[[noreturn]] void refuse(const char *reason, const Core &core) {
  lucent::error("x4-stream-interrupt",
                "StCdInterrupt completion refused: {} (pc=0x{:08X} ra=0x{:08X})",
                reason,
                core.pc,
                core.r[31]);
  std::abort();
}

} // namespace

bool consumeCompletedCallback(Core &core) {
  if (g_scope.core != &core || core.r[31] != kCdReadyReturn) {
    return false;
  }
  if (g_scope.consumed) {
    refuse("the completed libcd callback was consumed twice", core);
  }
  if (core.r[4] != 1u) {
    refuse("retail StCdInterrupt changed its nonblocking CdReady mode", core);
  }
  if (core.r[5] == 0u || g_scope.response == 0u) {
    refuse("the callback result buffer is absent", core);
  }

  // Preserve CD_ready's result priority exactly. A CdlDataReady completion publishes both result
  // bytes and both response buffers; CD_ready consumes 0x8011DFFA/0x8013BA88 first and deliberately
  // leaves the sync result pending. Other sync completions consume the callback's DFF9/BA80 pair.
  const std::uint32_t dataReadyStatus = core.mem_r8(kDataReadyResult);
  const std::uint32_t status = dataReadyStatus != 0u ? dataReadyStatus : g_scope.status;
  const std::uint32_t response = dataReadyStatus != 0u ? kDataReadyResponse : g_scope.response;
  const std::uint32_t consumedResult = dataReadyStatus != 0u ? kDataReadyResult : kSyncResult;
  if (status == 0u) {
    refuse("the completed callback has no published libcd result", core);
  }

  for (std::uint32_t byte = 0u; byte < kResponseBytes; ++byte) {
    core.mem_w8(core.r[5] + byte, core.mem_r8(response + byte));
  }

  // The IRQ was already acknowledged and decoded by callback 0x800E7944; only CD_ready's published
  // result consumption remains. No controller or timing operation is needed at this call edge.
  core.mem_w8(consumedResult, 0u);
  core.r[2] = status;
  g_scope.consumed = true;
  return true;
}

void run(Core &core, GuestBody retailBody) {
  if (!retailBody) {
    refuse("the original guest-body dispatcher is absent", core);
  }
  if (g_scope.core) {
    refuse("nested callback completion scope", core);
  }

  // callback 0x800E7944 calls the registered 0x8011DD20 target with the already-decoded libcd sync
  // status in a0 and its eight-byte response at a1. StCdInterrupt preserves neither value before
  // issuing CdReady, so retain them at this owning boundary.
  g_scope = {
      .core = &core,
      .status = core.r[4],
      .response = core.r[5],
      .consumed = false,
  };
  ScopeReset reset;
  retailBody(&core);
}

void run(Core *core) {
  if (!core) {
    lucent::error("x4-stream-interrupt", "StCdInterrupt received a null Core");
    std::abort();
  }
  const auto original = [](Core *active) {
    guest::callOriginal(active, kEntry, "stream_interrupt::completeSector original");
  };
  run(*core, original);
}

void registerOverride(Core &core) {
  guest::install(core, kEntry, "stream_interrupt::completeSector", run);
}

} // namespace x4::stream_interrupt
