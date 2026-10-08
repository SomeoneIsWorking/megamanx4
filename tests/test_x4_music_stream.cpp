#include "core.h"
#include "game.h"
#include "music_stream.h"

#include <cstdint>
#include <cstdio>
#include <memory>

namespace {

x4::music_stream::State *g_musicStream = nullptr;
std::uint32_t g_syncResult = 2u;
std::uint32_t g_controlResult = 1u;
std::uint32_t g_syncCalls = 0u;
std::uint32_t g_controlCalls = 0u;
std::uint32_t g_command = 0u;
std::uint32_t g_parameter = 0u;
std::uint32_t g_result = 0u;

bool check(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "x4_music_stream: %s\n", message);
  }
  return condition;
}

void cdSync(Core *core) {
  ++g_syncCalls;
  core->r[2] = g_syncResult;
}

void cdControl(Core *core) {
  ++g_controlCalls;
  g_command = core->r[4];
  g_parameter = core->r[5];
  g_result = core->r[6];
  core->r[2] = g_controlResult;
}

void yieldFields(Core &core, std::uint32_t returnAddress, std::uint32_t fields) {
  g_musicStream->yieldFields(returnAddress, fields);
  core.r[2] = 0u;
}

void dispatchState7(Core *core, std::uint32_t entry) {
  if (entry != x4::music_stream::kBeforeObjectsB) {
    std::fprintf(stderr, "x4_music_stream: unexpected dispatch 0x%08X\n", entry);
    return;
  }
  x4::music_stream::setMode(core, cdSync, cdControl, yieldFields);
}

void reset(Core &core) {
  core.r[29] = 0x801FFF00u;
  core.r[31] = 0x81234567u;
  core.r[16] = 0x10203040u;
  core.mem_w32(x4::music_stream::kMusicActive, 2u);
  core.mem_w32(x4::music_stream::kMachineState, 7u);
  core.mem_w8(0x8013952Cu, 0u);
  core.mem_w8(0x80139554u, 0u);
  g_syncResult = 2u;
  g_controlResult = 1u;
  g_syncCalls = 0u;
  g_controlCalls = 0u;
  g_command = 0u;
  g_parameter = 0u;
  g_result = 0u;
}

bool verifySuccessfulTransition(Core &core, x4::music_stream::State &state) {
  reset(core);
  g_musicStream = &state;

  if (!check(!state.dispatchBeforeObjectsB(dispatchState7), "state 7 did not yield at its first field fence") ||
      !check(g_syncCalls == 1u && g_controlCalls == 1u, "state 7 did not issue one command transaction") ||
      !check(g_command == 0x0Eu && core.mem_r8(g_parameter) == 0xC8u && g_result == 0x80139554u,
             "CdlSetmode command/parameter/result ABI diverged") ||
      !check(core.mem_r32(x4::music_stream::kMachineState) == 7u,
             "state 7 advanced before the host-owned field fence")) {
    return false;
  }

  if (!check(!state.dispatchBeforeObjectsB(dispatchState7), "field one completed the three-field fence") ||
      !check(!state.dispatchBeforeObjectsB(dispatchState7), "field two completed the three-field fence") ||
      !check(state.dispatchBeforeObjectsB(dispatchState7), "field three did not resume the retained state body")) {
    return false;
  }

  return check(g_syncCalls == 1u && g_controlCalls == 1u, "field resumes reissued the CD command") &&
         check(core.mem_r32(x4::music_stream::kMachineState) == 6u, "successful CdlSetmode did not publish state 6") &&
         check(core.r[29] == 0x801FFF00u && core.r[31] == 0x81234567u && core.r[16] == 0x10203040u,
               "state-7 replacement changed the retained stack/register return contract");
}

bool verifyStatusError(Core &core, x4::music_stream::State &state) {
  reset(core);
  core.mem_w8(0x80139554u, 0x10u);
  g_musicStream = &state;
  if (state.dispatchBeforeObjectsB(dispatchState7)) {
    return check(false, "status-error transaction did not enter its field fence");
  }
  for (std::uint32_t field = 0; field < x4::music_stream::kSetModeFields; ++field) {
    if (state.dispatchBeforeObjectsB(dispatchState7) != (field + 1u == x4::music_stream::kSetModeFields)) {
      return check(false, "status-error transaction completed at the wrong field");
    }
  }
  return check(core.mem_r8(0x8013952Cu) == 1u, "Setmode status bit 0x10 did not publish the retail error flag");
}

bool verifyNotReady(Core &core, x4::music_stream::State &state) {
  reset(core);
  g_syncResult = 1u;
  g_musicStream = &state;
  return check(state.dispatchBeforeObjectsB(dispatchState7), "incomplete CdSync unexpectedly yielded a field") &&
         check(g_syncCalls == 1u && g_controlCalls == 0u, "incomplete CdSync still issued CdlSetmode") &&
         check(core.mem_r32(x4::music_stream::kMachineState) == 7u, "incomplete CdSync advanced state 7");
}

bool verifyCommandRefusal(Core &core, x4::music_stream::State &state) {
  reset(core);
  g_controlResult = 0u;
  g_musicStream = &state;
  return check(state.dispatchBeforeObjectsB(dispatchState7), "refused CdlSetmode unexpectedly yielded a field") &&
         check(g_controlCalls == 1u, "refusal path did not issue CdlSetmode") &&
         check(core.mem_r32(x4::music_stream::kMachineState) == 7u, "refused CdlSetmode advanced state 7");
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  x4::music_stream::State state(game->core);
  if (!verifySuccessfulTransition(game->core, state) || !verifyStatusError(game->core, state) ||
      !verifyNotReady(game->core, state) || !verifyCommandRefusal(game->core, state)) {
    return 1;
  }
  std::puts("x4_music_stream: exact CdlSetmode ABI and three host-field transition passed");
  return 0;
}
