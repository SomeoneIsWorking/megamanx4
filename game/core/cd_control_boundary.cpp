#include "cd_control_boundary.h"

#include "core.h"

#include <cstdlib>
#include <lucent/log.h>

namespace x4::cd_control_boundary {

void blocking(Core *core,
              GuestBody retailBody,
              SynchronousControl synchronousControl,
              ExistingControlPolicy existingPolicy) {
  if (!core || !retailBody || !synchronousControl || !existingPolicy) {
    lucent::error("x4-cd-control", "CdControlB boundary requires core, super, and both native policies");
    std::abort();
  }

  if ((core->r[4] & 0xFFu) == kPauseCommand) {
    // SLUS_005.61 reaches this wrapper from movie cleanup 0x80018E50. The retained wrapper would
    // enter stock libcd's VSync(-1)-clocked command/sync loops. The framework CD owner already
    // completes the same command synchronously, including the result buffer, XA stop, finite-read
    // stop, and continuous-stream release. Preserve the incoming a0/a1/a2 ABI exactly.
    synchronousControl(core);
    return;
  }

  existingPolicy(core, retailBody, true);
}

void control(Core *core,
             GuestBody retailBody,
             ExistingControlPolicy existingPolicy,
             SynchronousSetMode synchronousSetMode) {
  if (!core || !retailBody || !existingPolicy || !synchronousSetMode) {
    lucent::error("x4-cd-control", "CdControl boundary requires core, super, existing policy, and Setmode owner");
    std::abort();
  }

  const std::uint32_t command = core->r[4] & 0xFFu;
  const bool cleanupSetMode = core->r[31] == kCleanupSetModeReturn;
  const bool musicSetMode = core->r[31] == kMusicSetModeReturn;
  if (command == kSetModeCommand && (cleanupSetMode || musicSetMode)) {
    const bool resultMatches = cleanupSetMode ? core->r[6] == 0u : core->r[6] == kMusicSetModeResult;
    if (core->r[5] == 0u || !resultMatches) {
      lucent::error("x4-cd-control",
                    "owned Setmode ABI differs from retained caller: ra=0x{:08X} param=0x{:08X} result=0x{:08X}",
                    core->r[31],
                    core->r[5],
                    core->r[6]);
      std::abort();
    }
    synchronousSetMode(*core, core->mem_r8(core->r[5]));
    if (musicSetMode) {
      for (std::uint32_t byte = 0u; byte < 8u; ++byte) {
        core->mem_w8(kMusicSetModeResult + byte, 0u);
      }
    }
    core->r[2] = 1u;
    return;
  }

  existingPolicy(core, retailBody, false);
}

} // namespace x4::cd_control_boundary
