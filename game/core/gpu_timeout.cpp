#include "gpu_timeout.h"

#include "cfg.h"
#include "core.h"
#include "override_registry.h"

#include <cstdlib>
#include <lucent/log.h>

#ifdef MMX4_HAVE_SUBSTRATE
extern void gen_func_800ECB38(Core *);
extern void shard_set_override(std::uint32_t, void (*)(Core *));
#endif

namespace x4::gpu_timeout {
namespace {

// Retail set_alarm reads libetc's VBlank counter through VSync(-1), adds four seconds at 60 Hz,
// and clears the elapsed-poll count. The native frame driver already owns that exact counter.
constexpr std::uint32_t kVblankCounter = 0x8011DC50u;
constexpr std::uint32_t kAlarmDeadline = 0x8011E2A0u;
constexpr std::uint32_t kAlarmPollCount = 0x8011E2A4u;
constexpr std::uint32_t kGpuStatusPointerPointer = 0x8011CB8Cu;
constexpr std::uint32_t kAlarmFields = 240u;

} // namespace

void setAlarm(Core *core) {
  if (!core) {
    cfg_loge("x4-gpu-timeout", "set_alarm received a null Core");
    std::abort();
  }

  // Transcribe gen_func_800ECB38 and the negative-query branch of gen_func_800E4DB0. Keeping the
  // original tick boundaries and volatile-register results makes the retained generated super a
  // meaningful A/B control; only the guest VSync dispatch itself is absent.
  core->r[29] -= 24u;
  core->mem_w32(core->r[29] + 16u, core->r[31]);
  core->r[31] = 0x800ECB48u;
  core->r[4] = UINT32_MAX;
  rec_guest_instruction_ticks(core, 4u);

  core->r[2] = core->mem_r32(0x8011CB84u);
  core->r[3] = core->mem_r32(0x8011CB88u);
  core->r[29] -= 32u;
  core->mem_w32(core->r[29] + 24u, core->r[31]);
  core->mem_w32(core->r[29] + 20u, core->r[17]);
  core->mem_w32(core->r[29] + 16u, core->r[16]);
  core->r[16] = core->mem_r32(core->r[2]);
  core->r[2] = core->mem_r32(core->r[3]);
  core->r[3] = core->mem_r32(kGpuStatusPointerPointer);
  core->r[17] = (core->r[2] - core->mem_r32(core->r[3])) & 0xFFFFu;
  rec_guest_instruction_ticks(core, 16u);
  core->r[2] = core->mem_r32(kVblankCounter);
  rec_guest_instruction_ticks(core, 4u);

  // VSync's callee-saved register and stack restoration. r3/r4 deliberately retain the same
  // volatile values as the generated negative-query path.
  core->r[31] = core->mem_r32(core->r[29] + 24u);
  core->r[17] = core->mem_r32(core->r[29] + 20u);
  core->r[16] = core->mem_r32(core->r[29] + 16u);
  core->r[29] += 32u;
  rec_guest_instruction_ticks(core, 6u);

  core->r[2] += kAlarmFields;
  core->r[1] = 0x80120000u;
  core->mem_w32(kAlarmDeadline, core->r[2]);
  core->mem_w32(kAlarmPollCount, 0u);
  core->r[31] = core->mem_r32(core->r[29] + 16u);
  core->r[29] += 24u;
  rec_guest_instruction_ticks(core, 9u);
}

void registerOverride() {
#ifdef MMX4_HAVE_SUBSTRATE
  overrides::install(kSetAlarmEntry, "gpu_timeout::setAlarm", setAlarm, gen_func_800ECB38, shard_set_override);
#else
  lucent::debug("x4-gpu-timeout", "GPU timeout ownership registration deferred: no generated substrate");
#endif
}

} // namespace x4::gpu_timeout
