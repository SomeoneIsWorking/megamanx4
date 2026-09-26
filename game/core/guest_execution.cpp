#include "guest_execution.h"

#include "core.h"
#include "execution_exit.h"
#include "native_dispatch.h"

#include <cstdlib>
#include <lucent/log.h>
#include <optional>

namespace x4::guest {
namespace {

// One host turn is ONE display field: psx::cpu::ExecutionBudget::currentTurn is 33'868'800/60 =
// 564,480 CPU cycles by construction (execution_exit.cpp). Exceeding it is an ORDINARY bounded exit
// under the executor contract, and a guest function needing slightly more than a field is finite
// compute, not a failure — the one measured case is DecDCTvlc (0x800ED574), which returns
// GuestReturn at its own return address 0x80018AA0 after 610,746 cycles, 1.082 fields. The budget
// constant is NOT raised; the call is resumed, through the framework primitive added for exactly
// this (psx::cpu::resumeGuestToReturn / resumeOriginal).
//
// A resume must not become a spin, so the loop is fenced by what it can MEASURE, not by a count it
// guesses:
//   1. a segment that exhausts its turn having consumed no guest cycles made no progress, so
//      resuming it could only repeat that segment — a fact about the exit, not a policy;
//   2. the call has spent kMaxCallTurns display fields of guest CPU without reaching its return
//      address. That one IS a policy, so it is stated in the unit that gives it meaning, set far
//      above anything measured, and reported per call, so it is falsifiable from the log instead of
//      trusted.
constexpr std::uint32_t kMaxCallTurns = 8u;

// Run-lifetime diagnostic tally, NOT execution state: the loop keeps no cross-call suspend record
// and nothing in the execution path reads or writes a Core through it. It exists so the run-end
// line can name a denominator. This product creates exactly one Core (game/core/main.cpp).
struct CallCensus {
  std::uint64_t completed = 0;
  std::uint64_t resumed = 0;
  std::uint32_t deepestTurns = 0;
  std::uint64_t resumedCycles = 0;
};

CallCensus census;

psx::cpu::NativeKey keyFor(Core &core, std::uint32_t address, const char *owner) {
  const auto image = core.currentImageIdentity(address);
  if (!image) {
    lucent::error("x4-guest", "{} has no authenticated image identity for guest address 0x{:08X}", owner, address);
    std::abort();
  }
  return {*image, address};
}

void requireReturn(const psx::cpu::ExecutionResult &result, const char *owner) {
  if (!psx::cpu::requireGuestReturn(result, owner)) {
    std::abort();
  }
}

void recordCompleted(std::uint32_t entry, std::uint32_t returnPc, std::uint32_t turns, std::uint64_t cycles) {
  ++census.completed;
  if (turns <= 1u) {
    return;
  }
  ++census.resumed;
  census.resumedCycles += cycles;
  if (turns > census.deepestTurns) {
    census.deepestTurns = turns;
  }
  lucent::info("x4-guest",
               "guest call 0x{:08X} to return address 0x{:08X} outlived one host turn: {} turn(s), "
               "{} cycles total. Denominator: {} of {} completed guest call(s) have needed a resume; "
               "deepest {} turn(s)",
               entry,
               returnPc,
               turns,
               cycles,
               census.resumed,
               census.completed,
               census.deepestTurns);
}

double displayFields(Core &core, std::uint64_t cycles) {
  return static_cast<double>(cycles) / static_cast<double>(psx::cpu::ExecutionBudget::currentTurn(core).cycles);
}

// The one loop both entry points share. `result` is the first segment's typed exit and `returnPc` is
// the boundary every segment must reach. `original` names the native key the first segment
// suppressed, if any: that is the ONLY thing that differs between psx::cpu::resumeOriginal and
// psx::cpu::resumeGuestToReturn, and the framework owns why (it re-establishes the suppression scope
// so a resumed original cannot re-enter its own override). Every non-BudgetExhausted exit keeps the
// caller's existing requireGuestReturn reporting and abort, so a call that genuinely cannot progress
// is reported exactly as before.
void runToReturn(Core &core,
                 std::uint32_t entry,
                 std::uint32_t returnPc,
                 const char *owner,
                 const std::optional<psx::cpu::NativeKey> &original,
                 psx::cpu::ExecutionResult result) {
  std::uint64_t cycles = result.cycles;
  std::uint32_t turns = 1u;
  while (result.reason == psx::cpu::ExecutionExitReason::BudgetExhausted) {
    if (result.cycles == 0u || result.guestPc == 0u) {
      lucent::error("x4-guest",
                    "{}: guest call 0x{:08X} to return address 0x{:08X} exhausted host turn {} with "
                    "no guest progress at 0x{:08X} after {} cycles: {}",
                    owner,
                    entry,
                    returnPc,
                    turns,
                    result.guestPc,
                    cycles,
                    result.detail);
      std::abort();
    }
    if (turns >= kMaxCallTurns) {
      lucent::error("x4-guest",
                    "{}: guest call 0x{:08X} to return address 0x{:08X} has consumed {} host turn(s) "
                    "and {} cycles ({:.3f} display fields) without returning and is still at 0x{:08X}. "
                    "A bounded guest call that needs more than {} display fields does not exist here, "
                    "so this is a guest loop: reported rather than spun on",
                    owner,
                    entry,
                    returnPc,
                    turns,
                    cycles,
                    displayFields(core, cycles),
                    result.guestPc,
                    kMaxCallTurns);
      std::abort();
    }
    const psx::cpu::ExecutionBudget turn = psx::cpu::ExecutionBudget::currentTurn(core);
    result = original ? psx::cpu::resumeOriginal(core, *original, result.guestPc, returnPc, turn)
                      : psx::cpu::resumeGuestToReturn(core, result.guestPc, returnPc, turn);
    cycles += result.cycles;
    ++turns;
  }
  requireReturn(result, owner);
  recordCompleted(entry, returnPc, turns, cycles);
}

} // namespace

void call(Core *core, std::uint32_t address) {
  if (!core) {
    lucent::error("x4-guest", "guest call 0x{:08X} received a null Core", address);
    std::abort();
  }
  // The return address is the caller's r[31] as the FIRST segment saw it. Capturing it here is what
  // keeps a resume from adopting the nested r[31] the guest left behind: that is a different address
  // and would end the call in the wrong place.
  const std::uint32_t returnPc = core->r[31];
  runToReturn(*core,
              address,
              returnPc,
              "Mega Man X4 guest call",
              std::nullopt,
              psx::cpu::dispatchGuest(*core, address, psx::cpu::ExecutionBudget::currentTurn(*core)));
}

psx::cpu::ExecutionResult dispatch(Core &core, std::uint32_t address) {
  return psx::cpu::dispatchGuest(core, address, psx::cpu::ExecutionBudget::currentTurn(core));
}

void callOriginal(Core *core, std::uint32_t address, const char *owner) {
  if (!core) {
    lucent::error("x4-guest", "{} received a null Core", owner);
    std::abort();
  }
  const psx::cpu::NativeKey key = keyFor(*core, address, owner);
  const std::uint32_t returnPc = core->r[31];
  runToReturn(*core,
              address,
              returnPc,
              owner,
              key,
              psx::cpu::callOriginal(*core, key, psx::cpu::ExecutionBudget::currentTurn(*core)));
}

void install(Core &core, std::uint32_t address, const char *name, NativeFunction function) {
  if (!function) {
    lucent::error("x4-guest", "{} has no native implementation", name);
    std::abort();
  }
  if (!core.nativeDispatcher().install({keyFor(core, address, name), name, function})) {
    lucent::error("x4-guest", "{} could not install its native override", name);
    std::abort();
  }
}

void reportGuestCallCensus(const char *why) {
  if (census.completed == 0u) {
    lucent::info("x4-guest", "run-end ({}): NO guest call completed, so this run measured nothing", why);
    return;
  }
  if (census.resumed == 0u) {
    lucent::info("x4-guest",
                 "run-end ({}): {} guest call(s) completed, 0 needed a resume — every call returned "
                 "inside the one display field its host turn allows",
                 why,
                 census.completed);
    return;
  }
  lucent::info("x4-guest",
               "run-end ({}): {} guest call(s) completed, {} needed a resume (deepest {} host turn(s), "
               "{} guest cycles over those calls); the other {} finished inside one field",
               why,
               census.completed,
               census.resumed,
               census.deepestTurns,
               census.resumedCycles,
               census.completed - census.resumed);
}

} // namespace x4::guest
