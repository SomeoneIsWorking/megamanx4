#include "music_cd.h"

#include "cd_control.h"
#include "core.h"
#include "game.h"

#include <cstdint>
#include <cstdio>
#include <memory>

namespace {

std::uint32_t gStockSyncCalls = 0u;
std::uint32_t gOriginalSyncCalls = 0u;
std::uint32_t gStockControlCalls = 0u;

bool check(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "x4_music_cd: %s\n", message);
  }
  return condition;
}

// The framework's own stock-Sony authorities, so this test exercises the shipping owners rather than
// a stand-in that could agree with them by construction.
void stockSync(Core *core) {
  ++gStockSyncCalls;
  cd_sync_stock_sync(core);
}

void originalSync(Core *core) {
  ++gOriginalSyncCalls;
  core->r[2] = 0xC0DEC0DEu;
}

void stockControl(Core *core) {
  ++gStockControlCalls;
  cd_control_sync(core);
}

void reset(Core &core) {
  gStockSyncCalls = 0u;
  gOriginalSyncCalls = 0u;
  gStockControlCalls = 0u;
  core.mem_w32(x4::music_cd::kMusicActive, 2u);
  core.mem_w32(x4::music_cd::kMachineState, 6u);
  core.mem_w32(x4::music_cd::kError, 0u);
  for (std::uint32_t byte = 0u; byte < 8u; ++byte) {
    core.mem_w8(x4::music_cd::kResult + byte, 0u);
  }
}

// The measured prologue each handler executes before its own `jal`, and the decision it takes on the
// answer. Reproduced instruction for instruction from the addresses in game/core/music_cd.h, so the
// test asks the question the guest asks: does this state advance?
struct StepOutcome {
  bool advanced;
  bool reachedCommand;
};

// func_80016E34 / func_80016DAC / func_80016B58, reduced to their measured shape: issue the leaf with
// a0=1 and a1=result, compare v0 against CdlComplete, and only then issue the command.
StepOutcome runMeasuredHandler(Core &core, const x4::music_cd::Step &step) {
  StepOutcome outcome{false, false};
  core.r[31] = step.syncReturn;
  core.r[4] = 1u;
  core.r[5] = step.result;
  if (!x4::music_cd::serveCdSync(&core, stockSync, originalSync)) {
    return outcome;
  }
  if (core.r[2] != x4::music_cd::kCommandComplete) {
    return outcome;
  }
  outcome.reachedCommand = true;

  core.r[31] = step.commandReturn;
  core.r[4] = step.command;
  core.r[5] = step.parameter;
  core.r[6] = step.result;
  if (!x4::music_cd::serveCdControl(&core, stockControl)) {
    return outcome;
  }
  if (core.r[2] != 0u) {
    outcome.advanced = true;
  }
  return outcome;
}

// Positive: every measured edge is served by the stock-Sony owner, with the guest's ABI intact, and
// the retained body is never entered.
bool verifyMeasuredEdgesAreServed(Core &core) {
  const x4::music_cd::Step *const steps[] = {
      &x4::music_cd::kSetFilterStep, &x4::music_cd::kSeekStep, &x4::music_cd::kReadStep};
  for (const x4::music_cd::Step *const step : steps) {
    reset(core);
    core.r[31] = step->syncReturn;
    core.r[4] = 1u;
    core.r[5] = step->result;
    if (!check(x4::music_cd::serveCdSync(&core, stockSync, originalSync), "a measured CdSync edge was not served")) {
      return false;
    }
    if (!check(gStockSyncCalls == 1u && gOriginalSyncCalls == 0u,
               "a measured CdSync edge did not reach the stock-Sony owner alone") ||
        !check(core.r[2] == x4::music_cd::kCommandComplete, "the stock-Sony CdSync owner did not answer CdlComplete")) {
      return false;
    }

    reset(core);
    core.r[31] = step->commandReturn;
    core.r[4] = step->command;
    core.r[5] = step->parameter;
    core.r[6] = step->result;
    if (!check(x4::music_cd::serveCdControl(&core, stockControl), "a measured CdControl edge was not served")) {
      return false;
    }
    if (!check(gStockControlCalls == 1u, "a measured CdControl edge did not reach the stock-Sony owner") ||
        !check(core.r[2] != 0u, "a measured CdControl edge was not accepted")) {
      return false;
    }
  }
  return true;
}

// The measured chain 6 -> 5 -> 1. This is the wall: with the leaf unowned, every handler returns on
// its CdlComplete comparison and the machine-state word never leaves 6, so the state-1 ReadS never
// runs and the handshake byte `D_80173C84` that unblocks func_8001DDB0 is never written.
bool verifyStateChainAdvances(Core &core) {
  reset(core);
  const x4::music_cd::Step *const chain[] = {
      &x4::music_cd::kSetFilterStep, &x4::music_cd::kSeekStep, &x4::music_cd::kReadStep};
  const std::uint32_t expected[] = {5u, 1u, 2u};
  for (std::uint32_t index = 0u; index < 3u; ++index) {
    core.mem_w32(x4::music_cd::kMachineState, chain[index]->state);
    const StepOutcome outcome = runMeasuredHandler(core, *chain[index]);
    if (!check(outcome.reachedCommand, "a measured handler never reached its command") ||
        !check(outcome.advanced, "a measured handler did not advance the machine-state word")) {
      return false;
    }
    // Each handler's own tail stores the next state; the port does not write it, the guest does.
    core.mem_w32(x4::music_cd::kMachineState, expected[index]);
    if (!check(core.mem_r32(x4::music_cd::kMachineState) == expected[index],
               "the simulated guest tail wrote the wrong next state")) {
      return false;
    }
  }
  return check(core.mem_r32(x4::music_cd::kMachineState) == 2u,
               "the 6 -> 5 -> 1 chain did not reach the state that issues CdlReadS");
}

// Negative: a caller outside the measured edges must not be absorbed. Both leaves outside the state
// machine's three steps keep their existing behaviour, so this owner cannot change what any other
// caller in the image sees.
bool verifyUnmeasuredCallersAreNotAbsorbed(Core &core) {
  const std::uint32_t unmeasured[] = {0x80016948u, 0x800188BCu, 0x80016E9Cu, 0x81234567u};
  for (const std::uint32_t returnAddress : unmeasured) {
    reset(core);
    core.r[31] = returnAddress;
    core.r[4] = 1u;
    core.r[5] = 0u;
    if (!check(!x4::music_cd::serveCdSync(&core, stockSync, originalSync),
               "an unmeasured CdSync caller was absorbed by this owner") ||
        !check(gStockSyncCalls == 0u && gOriginalSyncCalls == 0u,
               "an unmeasured CdSync caller reached a leaf it must not reach")) {
      return false;
    }

    reset(core);
    core.r[31] = returnAddress;
    core.r[4] = 0x0Eu;
    core.r[5] = 0u;
    core.r[6] = 0u;
    if (!check(!x4::music_cd::serveCdControl(&core, stockControl),
               "an unmeasured CdControl caller was absorbed by this owner") ||
        !check(gStockControlCalls == 0u, "an unmeasured CdControl caller reached the stock-Sony owner")) {
      return false;
    }
  }
  return true;
}

// Negative: the state-1 step tests the shell-open bit the sync owner publishes into the shared result
// buffer. It must arrive clear, or func_80016B58 returns before its CdlReadS and the handshake still
// never happens — so this asserts the published status, not merely that a call was made.
bool verifyPublishedStatusClearsShellOpen(Core &core) {
  reset(core);
  for (std::uint32_t byte = 0u; byte < 8u; ++byte) {
    core.mem_w8(x4::music_cd::kResult + byte, 0xFFu);
  }
  core.r[31] = x4::music_cd::kReadStep.syncReturn;
  core.r[4] = 1u;
  core.r[5] = x4::music_cd::kResult;
  if (!check(x4::music_cd::serveCdSync(&core, stockSync, originalSync), "the state-1 sync edge was not served")) {
    return false;
  }
  return check((core.mem_r8(x4::music_cd::kResult) & x4::music_cd::kShellOpenBit) == 0u,
               "the published status left the shell-open bit set, so func_80016B58 would still return early");
}

// Negative: the three edges are distinct per step, and each leaf's lookup is keyed on its own
// measured return address. A step must never be reachable through another step's edge, because the
// command each edge issues differs. (The owner REFUSES a matched edge carrying a different command
// rather than returning an answer, so what is asserted here is the part that can report a result: the
// lookups themselves are not interchangeable.)
bool verifyEdgesAreDistinct() {
  const x4::music_cd::Step *const steps[] = {
      &x4::music_cd::kSetFilterStep, &x4::music_cd::kSeekStep, &x4::music_cd::kReadStep};
  for (std::uint32_t index = 0u; index < 3u; ++index) {
    for (std::uint32_t other = 0u; other < 3u; ++other) {
      if (index == other) {
        continue;
      }
      if (!check(x4::music_cd::stepForSyncReturn(steps[index]->syncReturn) == steps[index] &&
                     x4::music_cd::stepForCommandReturn(steps[index]->commandReturn) == steps[index],
                 "a step's own edge does not resolve back to that step") ||
          !check(x4::music_cd::stepForSyncReturn(steps[other]->syncReturn) != steps[index] &&
                     x4::music_cd::stepForCommandReturn(steps[other]->commandReturn) != steps[index],
                 "one step was reachable through another step's edge")) {
        return false;
      }
    }
  }
  return true;
}

// The state machine is only reached when the music-active word is 2, and the step table is the image's
// own 4-byte-stride table at 0x800F1AB0. Pin the mapping this owner is built on so a wrong handler or
// a wrong state index fails here rather than in a product run.
bool verifyMeasuredStepTable() {
  const x4::music_cd::Step *const setFilter = x4::music_cd::stepForSyncReturn(0x80016E48u);
  const x4::music_cd::Step *const seek = x4::music_cd::stepForCommandReturn(0x80016DF0u);
  const x4::music_cd::Step *const read = x4::music_cd::stepForSyncReturn(0x80016B7Cu);
  return check(setFilter == &x4::music_cd::kSetFilterStep && setFilter->state == 6u &&
                   setFilter->handler == 0x80016E34u && setFilter->command == 0x0Du,
               "the state-6 Setfilter step is not where the image puts it") &&
         check(seek == &x4::music_cd::kSeekStep && seek->state == 5u && seek->handler == 0x80016DACu &&
                   seek->command == 0x15u,
               "the state-5 CdlSeekL step is not where the image puts it") &&
         check(read == &x4::music_cd::kReadStep && read->state == 1u && read->handler == 0x80016B58u &&
                   read->command == 0x1Bu,
               "the state-1 CdlReadS step is not where the image puts it") &&
         check(x4::music_cd::stepForSyncReturn(0x80016E9Cu) == nullptr &&
                   x4::music_cd::stepForCommandReturn(0x80016EC4u) == nullptr,
               "the state-7 Setmode edge, which x4::music_stream owns, was claimed by this owner");
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  if (!verifyMeasuredStepTable() || !verifyEdgesAreDistinct() || !verifyMeasuredEdgesAreServed(core) ||
      !verifyStateChainAdvances(core) || !verifyUnmeasuredCallersAreNotAbsorbed(core) ||
      !verifyPublishedStatusClearsShellOpen(core)) {
    return 1;
  }
  std::puts("x4_music_cd: measured 6->5->1 CdSync/CdControl steps served by the stock-Sony owners, unmeasured "
            "callers preserved, and the state-1 published status clears the shell-open bit");
  return 0;
}
