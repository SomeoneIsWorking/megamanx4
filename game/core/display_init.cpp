#include "display_init.h"

#include "cfg.h"
#include "core.h"
#include "execution_services.h"
#include "guest_execution.h"

#include <cstdlib>
#include <lucent/log.h>

namespace x4::display_init {
namespace {

constexpr std::uint32_t kEnvironmentSource = 0x80166C10u;
constexpr std::uint32_t kPrimaryEnvironment = 0x801395A8u;
constexpr std::uint32_t kSecondaryEnvironment = 0x801395BCu;
constexpr std::uint32_t kEnvironmentBytes = 20u;

void require(Core *core, GuestBody body, const char *name) {
  if (core && core->game && body) {
    return;
  }
  cfg_loge("x4-display-init", "display initialization is missing Core/Game or %s body", name);
  std::abort();
}

void copyWords(Core &core, std::uint32_t destination, std::uint32_t source) {
  for (std::uint32_t offset = 0; offset < kEnvironmentBytes; offset += sizeof(std::uint32_t)) {
    core.mem_w32(destination + offset, core.mem_r32(source + offset));
  }
}

void resetGraph(Core *core) {
  guest::call(core, 0x800E9D4Cu);
}
void clearImage(Core *core) {
  guest::call(core, 0x800EA3A0u);
}
void drawSync(Core *core) {
  guest::call(core, 0x800EA20Cu);
}
void setDisplayMask(Core *core) {
  guest::call(core, 0x800EA170u);
}
void publishEnvironment(Core *core) {
  guest::call(core, 0x800E9424u);
}

void run(Core *core) {
  initialize(core, resetGraph, clearImage, drawSync, setDisplayMask, publishEnvironment);
}

} // namespace

void initialize(Core *core,
                GuestBody resetGraph,
                GuestBody clearImage,
                GuestBody drawSync,
                GuestBody setDisplayMask,
                GuestBody publishEnvironment) {
  require(core, resetGraph, "ResetGraph");
  require(core, clearImage, "ClearImage");
  require(core, drawSync, "DrawSync");
  require(core, setDisplayMask, "SetDispMask");
  require(core, publishEnvironment, "PutDrawEnv");

  // Finite transcription of SLUS_005.61 0x800185F8. The original's sole VSync(0) sits between
  // ResetGraph and the initial clear. The native frame shell owns that boundary, so initialization
  // publishes the same environments and flags without entering libetc timing.
  core->r[29] -= 48u;
  core->mem_w32(core->r[29] + 36u, core->r[17]);
  core->r[17] = core->r[4];
  core->mem_w32(core->r[29] + 40u, core->r[18]);
  core->r[18] = core->r[5];
  core->mem_w32(core->r[29] + 32u, core->r[16]);
  core->r[16] = kEnvironmentSource;
  core->mem_w32(core->r[29] + 44u, core->r[31]);
  copyWords(*core, kPrimaryEnvironment, kEnvironmentSource);
  copyWords(*core, kSecondaryEnvironment, kEnvironmentSource + 160u);
  core->r[31] = 0x800186D4u;
  core->r[4] = 0u;
  psx::cpu::accountGuestInstructions(*core, 55u);
  resetGraph(core);

  core->r[4] = 0u;
  core->mem_w16(core->r[29] + 24u, 0u);
  core->mem_w16(core->r[29] + 26u, 0u);
  core->mem_w16(core->r[29] + 28u, 480u);
  core->mem_w16(core->r[29] + 30u, 480u);
  psx::cpu::accountGuestInstructions(*core, 7u);

  core->r[4] = core->r[29] + 24u;
  core->r[5] = 0u;
  core->r[6] = 0u;
  core->r[31] = 0x80018704u;
  core->r[7] = 0u;
  psx::cpu::accountGuestInstructions(*core, 5u);
  clearImage(core);
  core->r[31] = 0x8001870Cu;
  core->r[4] = 0u;
  psx::cpu::accountGuestInstructions(*core, 2u);
  drawSync(core);
  core->r[31] = 0x80018714u;
  core->r[4] = 1u;
  psx::cpu::accountGuestInstructions(*core, 2u);
  setDisplayMask(core);

  core->r[4] = kEnvironmentSource;
  core->r[5] = 0u;
  core->r[6] = 0u;
  core->r[7] = core->r[17];
  core->r[31] = 0x8001872Cu;
  core->mem_w32(core->r[29] + 16u, core->r[18]);
  psx::cpu::accountGuestInstructions(*core, 6u);
  publishEnvironment(core);
  core->r[16] += 160u;
  core->r[4] = core->r[16];
  core->r[5] = 0u;
  core->r[6] = 240u;
  core->r[7] = core->r[17];
  core->r[31] = 0x80018748u;
  core->mem_w32(core->r[29] + 16u, core->r[18]);
  psx::cpu::accountGuestInstructions(*core, 7u);
  publishEnvironment(core);

  core->r[2] = 1u;
  core->mem_w8(0x80166CC1u, static_cast<std::uint8_t>(core->r[2]));
  core->mem_w8(0x80166C21u, static_cast<std::uint8_t>(core->r[2]));
  core->mem_w8(0x80166CC0u, 0u);
  core->mem_w8(0x80166C20u, 0u);
  core->r[31] = core->mem_r32(core->r[29] + 44u);
  core->r[18] = core->mem_r32(core->r[29] + 40u);
  core->r[17] = core->mem_r32(core->r[29] + 36u);
  core->r[16] = core->mem_r32(core->r[29] + 32u);
  core->r[29] += 48u;
  psx::cpu::accountGuestInstructions(*core, 16u);
}

void registerOverride(Core &core) {
  guest::install(core, kEntry, "display_init::initialize", run);
}

} // namespace x4::display_init
