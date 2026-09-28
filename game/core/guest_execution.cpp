#include "guest_execution.h"

#include "core.h"
#include "execution_exit.h"
#include "native_dispatch.h"

#include <cstdlib>
#include <lucent/log.h>
#include <optional>
#include <vector>

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
  // The link register at the instant of each resume, classified against the ONE owner of this
  // title's image extent. Measured 2026-09-29: the fault is a guest call resumed into a leaf that
  // ends `jr $ra`, and a `jr $ra` at a resume point does NOT consult the `returnPc` boundary — it
  // uses `r[31]` as it stands. So this is the register that can turn a resume into a jump to a
  // non-address, and the faulting value 0x0113D7D0 is in no active code image at all.
  std::uint64_t raInCodeImage = 0;
  std::uint64_t raInRamOutsideCode = 0;
  std::uint64_t raOutsideRam = 0;
};

CallCensus census;

// The distinct out-of-text link registers, capped so a long run cannot turn a diagnostic into a log
// flood. The cap is stated and the TOTAL is always reported, so a capped report is still a
// denominator rather than a sample.
constexpr std::size_t kMaxReportedOutOfText = 8u;

struct OutOfTextRa {
  std::uint32_t ra = 0;
  std::uint32_t resumePoint = 0;
  std::uint32_t entry = 0;
  std::uint32_t returnPc = 0;
};
std::vector<OutOfTextRa> outOfTextRas;
// Classification against `measuredProgramImage`, NOT against a constant written here. The image
// extent comes from the PS-X EXE header's `t_addr`/`t_size`, and 2026-09-29 is the day this file's
// author classified 0x800E0000..0x80100000 as "BIOS" and built an account on it: that range is
// INSIDE this image's text (0x80010000..0x8012F800), so every address involved was the game's own
// code. One owner, derived from the image, or the next reader repeats the mistake.
enum class RaClass {
  CodeImage,
  RamOutsideCode,
  OutsideRam,
};

// KSEG0/KSEG1 to physical, and the PSX's 2 MiB of RAM. The CODE test deliberately delegates to
// `Core::currentImageIdentity` rather than re-deriving an extent: that is the framework's own rule
// for "does this address resolve to a code image", it is what `keyFor` above already uses, and it is
// literally the criterion the fault message quotes ("resolves to zero or multiple active code
// images"). An overlay module's text is a code image too, so a resident-text test would have
// misfiled a valid address from one.
inline constexpr std::uint32_t kGuestPhysicalMask = 0x1FFFFFFFu;
inline constexpr std::uint32_t kGuestRamPhysicalBytes = 2u * 1024u * 1024u;

RaClass classifyRa(const Core &core, std::uint32_t ra) {
  if (core.currentImageIdentity(ra)) {
    return RaClass::CodeImage;
  }
  return (ra & kGuestPhysicalMask) < kGuestRamPhysicalBytes ? RaClass::RamOutsideCode : RaClass::OutsideRam;
}

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
               "deepest {} turn(s). Link register at the resume point: {} in a code image, {} in RAM "
               "outside one, {} outside RAM",
               entry,
               returnPc,
               turns,
               cycles,
               census.resumed,
               census.completed,
               census.deepestTurns,
               census.raInCodeImage,
               census.raInRamOutsideCode,
               census.raOutsideRam);
  for (const OutOfTextRa &sample : outOfTextRas) {
    lucent::error("x4-guest",
                  "resume of call 0x{:08X} (return 0x{:08X}) at 0x{:08X} carried link register "
                  "0x{:08X}, which is NOT in any code image: a `jr $ra` at that resume point would "
                  "dispatch straight to it and never reach the return boundary",
                  sample.entry,
                  sample.returnPc,
                  sample.resumePoint,
                  sample.ra);
  }
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
    // CLASSIFIED BEFORE THE RESUME, because that is the instant whose `r[31]` the resumed code will
    // use. `result.guestPc` re-enters guest code mid-function; if the instruction there is a
    // `jr $ra` — and 0x800EA0F4, the resume point this fault followed, IS such a leaf — it
    // dispatches to `r[31]` and never reaches the `returnPc` boundary. Reading it after the resume
    // would read the NEXT segment's link register and classify the wrong value.
    switch (classifyRa(core, core.r[31])) {
    case RaClass::CodeImage:
      ++census.raInCodeImage;
      break;
    case RaClass::RamOutsideCode:
      ++census.raInRamOutsideCode;
      if (outOfTextRas.size() < kMaxReportedOutOfText) {
        outOfTextRas.push_back({core.r[31], result.guestPc, entry, returnPc});
      }
      break;
    case RaClass::OutsideRam:
      ++census.raOutsideRam;
      if (outOfTextRas.size() < kMaxReportedOutOfText) {
        outOfTextRas.push_back({core.r[31], result.guestPc, entry, returnPc});
      }
      break;
    }
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
