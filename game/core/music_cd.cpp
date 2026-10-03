#include "music_cd.h"

#include "cd_control.h"
#include "core.h"
#include "native_dispatch.h"
#include "resumable_guest_call.h"

#include <array>
#include <cstdlib>
#include <lucent/log.h>

namespace x4::music_cd {
namespace {

// Run-lifetime tally, so a claim that a step was served carries how many times the leaf was actually
// reached rather than how many times this owner could have served it.
struct Tally {
  std::uint32_t syncOffered = 0u;
  std::uint32_t syncServed[kStepCount]{};
  std::uint32_t commandOffered = 0u;
  std::uint32_t commandServed[kStepCount]{};
};

Tally &tally() {
  static Tally counts;
  return counts;
}

constexpr std::uint32_t kNoStep = kStepCount;

[[nodiscard]] constexpr std::uint32_t indexForSyncReturn(std::uint32_t returnAddress) noexcept {
  for (std::uint32_t index = 0; index < kStepCount; ++index) {
    if (kSteps[index].syncReturn == returnAddress) {
      return index;
    }
  }
  return kNoStep;
}

[[nodiscard]] constexpr std::uint32_t indexForCommandReturn(std::uint32_t returnAddress) noexcept {
  for (std::uint32_t index = 0; index < kStepCount; ++index) {
    if (kSteps[index].commandReturn == returnAddress) {
      return index;
    }
  }
  return kNoStep;
}

[[noreturn]] void refuse(const char *reason, const Step &step, std::uint32_t observed) {
  lucent::error("x4-music-cd",
                "XA/BGM CD step refused: {}. State {} (handler 0x{:08X}, selected through the jump "
                "table at 0x{:08X}) calls this leaf at 0x{:08X} with command 0x{:02X}, parameter "
                "0x{:08X}, result 0x{:08X}; the call carried 0x{:08X}. Every address is from "
                "SLUS_005.61 and is listed in game/core/music_cd.h.",
                reason,
                step.state,
                step.handler,
                kStepTable,
                kCommandEntry,
                step.command,
                step.parameter,
                step.result,
                observed);
  std::abort();
}

void require(Core *core, GuestBody leaf, const char *name) {
  if (!core) {
    lucent::error("x4-music-cd", "XA/BGM CD step owner received a null Core");
    std::abort();
  }
  if (!leaf) {
    lucent::error("x4-music-cd", "XA/BGM CD step owner is missing its {} owner", name);
    std::abort();
  }
}

// The framework's own stock-Sony completion authorities, and the retained body every caller outside
// the measured edges keeps.
void frameworkCdSync(Core *core) {
  cd_sync_stock_sync(core);
}

void frameworkCdControl(Core *core) {
  cd_control_sync(core);
}

void originalCdSync(Core *core) {
  psx::cpu::callOriginalResumingToReturn(*core, "music_cd::CdSync original", kCdSyncEntry, core->r[31]);
}

void serveCdSyncEntry(Core *core) {
  if (!serveCdSync(core, frameworkCdSync, originalCdSync)) {
    originalCdSync(core);
  }
}

} // namespace

const Step *stepForSyncReturn(std::uint32_t returnAddress) noexcept {
  const std::uint32_t index = indexForSyncReturn(returnAddress);
  return index == kNoStep ? nullptr : &kSteps[index];
}

const Step *stepForCommandReturn(std::uint32_t returnAddress) noexcept {
  const std::uint32_t index = indexForCommandReturn(returnAddress);
  return index == kNoStep ? nullptr : &kSteps[index];
}

bool serveCdSync(Core *core, GuestBody stockSync, GuestBody originalSync) {
  require(core, stockSync, "CdSync");
  require(core, originalSync, "original CdSync");
  Tally &counts = tally();
  ++counts.syncOffered;

  const std::uint32_t index = indexForSyncReturn(core->r[31]);
  if (index == kNoStep) {
    return false;
  }
  const Step &step = kSteps[index];
  // All three measured handlers open with `addiu $4,$zero,1`, so a0 is libcd's noblock flag.
  if (core->r[4] != 1u) {
    refuse("the noblock argument is not the image's 1", step, core->r[4]);
  }
  if (core->r[5] != step.result) {
    refuse("the result argument is not the image's literal", step, core->r[5]);
  }

  stockSync(core);
  // The substituted owner is the framework's, so this checks the ANSWER the guest's three handlers
  // branch on rather than assuming it. Each of them returns without advancing when v0 is not
  // CdlComplete, which is the park this owner exists to remove.
  if (core->r[2] != kCommandComplete) {
    lucent::error("x4-music-cd",
                  "the stock-Sony CdSync owner answered {} for state {} at edge 0x{:08X}, but every "
                  "measured handler of this state machine branches on {} and would leave the "
                  "machine-state word unchanged",
                  core->r[2],
                  step.state,
                  step.syncReturn,
                  kCommandComplete);
    std::abort();
  }
  ++counts.syncServed[index];
  lucent::debug("x4-music-cd",
                "CdSync 0x{:08X} served for state {} (0x{:08X}, edge 0x{:08X}) -> CdlComplete; "
                "machine-state word 0x{:08X} is {}, music-active 0x{:08X} is {}, sticky error 0x{:08X} "
                "is {}, published status 0x{:02X} (shell-open bit {}); {}/{} of this owner's sync "
                "edges served, of {} leaf calls offered",
                kCdSyncEntry,
                step.state,
                step.handler,
                step.syncReturn,
                kMachineState,
                core->mem_r32(kMachineState),
                kMusicActive,
                core->mem_r32(kMusicActive),
                kError,
                core->mem_r32(kError),
                core->mem_r8(kResult),
                (core->mem_r8(kResult) & kShellOpenBit) != 0u ? "SET" : "clear",
                counts.syncServed[index],
                kStepCount,
                counts.syncOffered);
  return true;
}

bool serveCdControl(Core *core, GuestBody stockControl) {
  require(core, stockControl, "CdControl");
  Tally &counts = tally();
  ++counts.commandOffered;

  const std::uint32_t index = indexForCommandReturn(core->r[31]);
  if (index == kNoStep) {
    return false;
  }
  const Step &step = kSteps[index];
  if ((core->r[4] & 0xFFu) != step.command) {
    refuse("the command is not the one this step issues", step, core->r[4] & 0xFFu);
  }
  if (core->r[5] != step.parameter) {
    refuse("the parameter is not the image's literal", step, core->r[5]);
  }
  if (core->r[6] != step.result) {
    refuse("the result address is not the image's literal", step, core->r[6]);
  }

  stockControl(core);
  if (core->r[2] == 0u) {
    lucent::error("x4-music-cd",
                  "the stock-Sony CdControl owner refused command 0x{:02X} for state {} at edge "
                  "0x{:08X}; the handler returns without advancing when its call yields zero, so "
                  "the XA/BGM machine-state word would stay at {}",
                  step.command,
                  step.state,
                  step.commandReturn,
                  core->mem_r32(kMachineState));
    std::abort();
  }
  ++counts.commandServed[index];
  lucent::debug("x4-music-cd",
                "CdControl 0x{:08X} served for state {} (0x{:08X}, edge 0x{:08X}): command 0x{:02X} "
                "parameter 0x{:08X} result 0x{:08X} accepted; machine-state word 0x{:08X} is {}, this "
                "step is {}/{} of this owner's command edges served, of {} leaf calls offered",
                kCommandEntry,
                step.state,
                step.handler,
                step.commandReturn,
                step.command,
                step.parameter,
                step.result,
                kMachineState,
                core->mem_r32(kMachineState),
                counts.commandServed[index],
                kStepCount,
                counts.commandOffered);
  return true;
}

void registerOverrides(Core &core) {
  psx::cpu::installNativeOverride(core, kCdSyncEntry, "music_cd::CdSync", serveCdSyncEntry);
}

} // namespace x4::music_cd
