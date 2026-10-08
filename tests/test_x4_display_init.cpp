#include "display_init.h"

#include "core.h"
#include "game.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <memory>

namespace {

std::array<std::uint32_t, 6> g_calls{};
std::size_t g_callCount = 0;
std::size_t g_environmentCount = 0;
bool g_argumentsValid = true;

void record(std::uint32_t call) {
  g_calls[g_callCount++] = call;
}

void reset_graph(Core *core) {
  record(1);
  g_argumentsValid &= core->r[4] == 0u;
}

void clear_image(Core *core) {
  record(2);
  const std::uint32_t rect = core->r[4];
  g_argumentsValid &= core->mem_r16(rect) == 0u && core->mem_r16(rect + 2u) == 0u && core->mem_r16(rect + 4u) == 480u &&
                      core->mem_r16(rect + 6u) == 480u && core->r[5] == 0u && core->r[6] == 0u && core->r[7] == 0u;
}

void draw_sync(Core *core) {
  record(3);
  g_argumentsValid &= core->r[4] == 0u;
}

void set_display_mask(Core *core) {
  record(4);
  g_argumentsValid &= core->r[4] == 1u;
}

void publish_environment(Core *core) {
  record(5);
  const bool first = g_environmentCount++ == 0u;
  g_argumentsValid &= core->r[4] == (first ? 0x80166C10u : 0x80166CB0u) && core->r[5] == 0u &&
                      core->r[6] == (first ? 0u : 240u) && core->r[7] == 320u &&
                      core->mem_r32(core->r[29] + 16u) == 240u;
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  constexpr std::uint32_t kStack = 0x801FFF00u;
  constexpr std::uint32_t kReturnAddress = 0x81234567u;
  core.r[29] = kStack;
  core.r[31] = kReturnAddress;
  core.r[16] = 0x16161616u;
  core.r[17] = 0x17171717u;
  core.r[18] = 0x18181818u;
  for (std::uint32_t offset = 0; offset < 20u; offset += 4u) {
    core.mem_w32(0x80166C10u + offset, 0x11000000u + offset);
    core.mem_w32(0x80166CB0u + offset, 0x22000000u + offset);
  }
  core.r[4] = 320u;
  core.r[5] = 240u;
  const std::uint64_t ticksBefore = game->timing.guestInstructionTicks;

  x4::display_init::initialize(&core, reset_graph, clear_image, draw_sync, set_display_mask, publish_environment);

  bool copiesValid = true;
  for (std::uint32_t offset = 0; offset < 20u; offset += 4u) {
    copiesValid &= core.mem_r32(0x801395A8u + offset) == 0x11000000u + offset;
    copiesValid &= core.mem_r32(0x801395BCu + offset) == 0x22000000u + offset;
  }
  const bool passed = g_callCount == 6u && g_calls == std::array<std::uint32_t, 6>{1, 2, 3, 4, 5, 5} &&
                      g_argumentsValid && copiesValid && core.mem_r8(0x80166CC1u) == 1u &&
                      core.mem_r8(0x80166C21u) == 1u && core.mem_r8(0x80166CC0u) == 0u &&
                      core.mem_r8(0x80166C20u) == 0u && core.r[29] == kStack && core.r[31] == kReturnAddress &&
                      core.r[16] == 0x16161616u && core.r[17] == 0x17171717u && core.r[18] == 0x18181818u &&
                      game->timing.guestInstructionTicks - ticksBefore == 100u;
  if (!passed) {
    std::fprintf(stderr, "x4_display_init: finite display publication diverged\n");
    return 1;
  }
  std::puts("x4_display_init: finite VSync-free display publication passed");
  return 0;
}
