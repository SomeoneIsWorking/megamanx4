#include "core.h"
#include "game.h"
#include "gpu_timeout.h"

#include <cstdint>
#include <cstdio>
#include <memory>

int main() {
  auto game = std::make_unique<Game>();
  Core *core = &game->core;
  constexpr std::uint32_t kStack = 0x801FFF00u;
  constexpr std::uint32_t kReturnAddress = 0x81234567u;
  constexpr std::uint32_t kCounter = 317u;
  constexpr std::uint32_t kGpuWordA = 0x80110000u;
  constexpr std::uint32_t kGpuWordB = 0x80110004u;
  constexpr std::uint32_t kGpuWordC = 0x80110008u;

  core->r[29] = kStack;
  core->r[31] = kReturnAddress;
  core->r[16] = 0x16161616u;
  core->r[17] = 0x17171717u;
  core->mem_w32(0x8011CB84u, kGpuWordA);
  core->mem_w32(0x8011CB88u, kGpuWordB);
  core->mem_w32(0x8011CB8Cu, kGpuWordC);
  core->mem_w32(kGpuWordA, 0x12345678u);
  core->mem_w32(kGpuWordB, 0x00023456u);
  core->mem_w32(kGpuWordC, 0x00012345u);
  core->mem_w32(0x8011DC50u, kCounter);
  core->mem_w32(0x8011E2A0u, 0xA5A5A5A5u);
  core->mem_w32(0x8011E2A4u, 0xA5A5A5A5u);
  const std::uint64_t ticksBefore = game->timing.guestInstructionTicks;

  x4::gpu_timeout::setAlarm(core);

  const bool passed = core->r[29] == kStack && core->r[31] == kReturnAddress && core->r[16] == 0x16161616u &&
                      core->r[17] == 0x17171717u && core->r[2] == kCounter + 240u && core->r[3] == kGpuWordC &&
                      core->r[4] == UINT32_MAX && core->r[1] == 0x80120000u &&
                      core->mem_r32(0x8011E2A0u) == kCounter + 240u && core->mem_r32(0x8011E2A4u) == 0u &&
                      game->timing.guestInstructionTicks - ticksBefore == 39u;
  if (!passed) {
    std::fprintf(stderr, "x4_gpu_timeout: native set_alarm diverged from the retail negative-query path\n");
    return 1;
  }

  std::puts("x4_gpu_timeout: direct field-counter deadline and exact guest state passed");
  return 0;
}
