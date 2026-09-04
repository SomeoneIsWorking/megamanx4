#include "cd_control.h"
#include "cd_control_boundary.h"
#include "cd_controller.h"
#include "core.h"
#include "game.h"
#include "movie_cleanup.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <vector>

namespace {

struct Call {
  std::uint32_t entry;
  std::uint32_t returnAddress;
  std::uint32_t a0;
  std::uint32_t a1;
  std::uint32_t a2;
};

std::vector<Call> gCalls;
std::vector<x4::movie_cleanup::Phase> gFieldPhases;
std::uint32_t gRetainedBlockingCalls = 0u;
std::uint32_t gExistingBlockingCalls = 0u;
std::uint32_t gControllerResets = 0u;
std::uint32_t gGuestVsyncCalls = 0u;
x4::movie_cleanup::State *gState = nullptr;

bool check(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "x4_movie_cleanup: %s\n", message);
  }
  return condition;
}

std::uint64_t testTicks(void *context) {
  return *static_cast<std::uint64_t *>(context);
}

void retainedBlocking(Core *) {
  ++gRetainedBlockingCalls;
}

void existingBlocking(Core *, x4::cd_control_boundary::GuestBody, bool) {
  ++gExistingBlockingCalls;
}

void synchronousControl(Core *core) {
  cd_control_sync(core);
}

void resetController(Core &core) {
  ++gControllerResets;
  x4::cd_controller::reset(core);
}

void suspendField(Core &) {
  gFieldPhases.push_back(gState->phase());
}

void dispatch(Core *core, std::uint32_t entry) {
  gCalls.push_back({entry, core->r[31], core->r[4], core->r[5], core->r[6]});
  switch (entry) {
  case 0x800E5FF4u:
    x4::cd_control_boundary::blocking(core, retainedBlocking, synchronousControl, existingBlocking);
    return;
  case 0x800E5D90u:
    cd_control_sync(core);
    return;
  case 0x800E4DB0u:
    ++gGuestVsyncCalls;
    return;
  default:
    core->r[2] = 1u;
    return;
  }
}

void resetHarness(Core &core, Game &game) {
  gCalls.clear();
  gFieldPhases.clear();
  gRetainedBlockingCalls = 0u;
  gExistingBlockingCalls = 0u;
  gControllerResets = 0u;
  gGuestVsyncCalls = 0u;

  core.r[29] = 0x801FFF00u;
  core.r[31] = 0x81234567u;
  game.xa.active = 1;
  game.xa.mode = 0xC8u;
  game.cd.stock_reading = 1;
  game.cd.stream_active = 1;
  game.cdc.mode = 0xC8u;
  game.cdc.reading = 1;
  game.cdc.irq_en = 0u;
  core.mem_w8(0x8011DD3Du, 0x55u);
  core.mem_w8(0x8011DD3Cu, 0x66u);
  core.mem_w32(0x8011DD1Cu, 0x11111111u);
  core.mem_w32(0x8011DD20u, 0x22222222u);
  core.mem_w32(0x8011DD2Cu, 0x33333333u);
  core.mem_w32(0x8011DD30u, 0x44444444u);
}

bool verifyTransaction(Core &core, Game &game, x4::movie_cleanup::State &state) {
  constexpr std::array<std::uint32_t, 7> kEntries = {
      0x800192F8u,
      0x800E5FF4u,
      0x800E6178u,
      0x800E5D78u,
      0x800ED084u,
      0x800E8130u,
      0x800E5D90u,
  };
  constexpr std::array<std::uint32_t, 7> kReturns = {
      0x80018E64u,
      0x80018E74u,
      0x80018E8Cu,
      0x80018E94u,
      0x80018E9Cu,
      0x80018EA4u,
      0x80018ECCu,
  };

  resetHarness(core, game);
  std::uint64_t ticks = 1234u;
  game.cdc.tick_context = &ticks;
  game.cdc.tick_now = testTicks;
  gState = &state;

  x4::movie_cleanup::run(core, state, dispatch, resetController);

  if (!check(gCalls.size() == kEntries.size(), "cleanup dispatched the wrong retained leaf count")) {
    return false;
  }
  for (std::size_t call = 0u; call < kEntries.size(); ++call) {
    if (!check(gCalls[call].entry == kEntries[call] && gCalls[call].returnAddress == kReturns[call],
               "cleanup changed a retained leaf or return edge")) {
      return false;
    }
  }

  constexpr std::array<x4::movie_cleanup::Phase, x4::movie_cleanup::kTotalFields> kPhases = {
      x4::movie_cleanup::Phase::DisplayFence,
      x4::movie_cleanup::Phase::ResetFence,
      x4::movie_cleanup::Phase::ResetFence,
      x4::movie_cleanup::Phase::ResetFence,
      x4::movie_cleanup::Phase::SetModeFence,
      x4::movie_cleanup::Phase::SetModeFence,
      x4::movie_cleanup::Phase::SetModeFence,
  };

  return check(gFieldPhases == std::vector<x4::movie_cleanup::Phase>(kPhases.begin(), kPhases.end()),
               "cleanup did not consume the exact 1+3+3 field phase order") &&
         check(!state.pending() && state.phase() == x4::movie_cleanup::Phase::Idle &&
                   state.completedFields() == x4::movie_cleanup::kTotalFields,
               "cleanup FSM did not finish exactly seven fields") &&
         check(gGuestVsyncCalls == 0u && gRetainedBlockingCalls == 0u && gExistingBlockingCalls == 0u,
               "cleanup dispatched guest VSync or bypassed the synchronous Pause owner") &&
         check(gControllerResets == 1u && game.cdc.irq_en == x4::cd_controller::kLibCdInterruptMask &&
                   game.cdc.tick_context == &ticks && game.cdc.tick_now == testTicks,
               "cleanup did not reuse the shipping controller-reset authority") &&
         check(game.xa.active == 0 && game.cd.stock_reading == 0 && game.cd.stream_active == 0,
               "cleanup did not release every movie stream owner") &&
         check(game.xa.mode == 0x80u && game.cdc.mode == 0x80u,
               "cleanup Setmode did not reach both shipping mode owners") &&
         check(core.mem_r8(0x8011DD3Du) == 0u && core.mem_r8(0x8011DD3Cu) == 0u && core.mem_r32(0x8011DD1Cu) == 0u &&
                   core.mem_r32(0x8011DD20u) == 0u && core.mem_r32(0x8011DD2Cu) == 0u &&
                   core.mem_r32(0x8011DD30u) == 0u,
               "cleanup did not publish completed stock libcd reset state") &&
         check(gCalls[1].a0 == 9u && gCalls[1].a1 == 0u && gCalls[1].a2 == 0u, "cleanup changed the CdlPause ABI") &&
         check(gCalls[6].a0 == 14u && core.mem_r8(gCalls[6].a1) == 0x80u && gCalls[6].a2 == 0u,
               "cleanup changed the CdlSetmode ABI") &&
         check(core.r[29] == 0x801FFF00u && core.r[31] == 0x81234567u,
               "cleanup changed the retained stack/return contract");
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  x4::movie_cleanup::State state(game->core, suspendField);
  if (!verifyTransaction(game->core, *game, state)) {
    return 1;
  }
  std::puts("x4_movie_cleanup: exact seven-field cleanup and synchronous CD contracts passed");
  return 0;
}
