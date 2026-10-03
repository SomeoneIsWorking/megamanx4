

#include "core.h"
#include "execution_exit.h"
#include "native_dispatch.h"
#include "resumable_guest_call.h"

#include <cstdio>
#include <cstdlib>
#include <lucent/log.h>

namespace x4::guest {
namespace {

constexpr std::uint32_t kNumGpr = 32u; // R3000::r; r[0] is hardwired zero

void requireOwnedEntry(Core *core, std::uint32_t address, const char *owner) {
  if (core->currentImageIdentity(address)) {
    return;
  }
  lucent::error("x4-guest",
                "{} is dispatching guest entry 0x{:08X}, which is in NO loaded code image. Refused "
                "here rather than at the dispatcher, which could only have named the address.",
                owner,
                address);
  std::abort();
}

} // namespace

void callWithoutKnownReturn(Core *core, std::uint32_t address) {
  if (!core) {
    lucent::error("x4-guest", "guest call 0x{:08X} received a null Core", address);
    std::abort();
  }
  // The first segment, honestly bounded. If it returns, the boundary was never needed and the stale
  // `r[31]` was harmless. If it ends BudgetExhausted, the boundary WOULD be needed and there is none,
  // so this refuses instead of resuming against a guess.
  requireOwnedEntry(core, address, "x4::guest::callWithoutKnownReturn");
  const psx::cpu::ExecutionResult first =
      psx::cpu::dispatchGuest(*core, address, psx::cpu::ExecutionBudget::currentTurn(*core));
  if (first.reason != psx::cpu::ExecutionExitReason::BudgetExhausted) {
    if (first.returned()) {
      core->guestCallCensus().recordCompleted(address, first.guestPc, 1u, first.cycles);
      return;
    }
    // The entry is NAMED, and so are the registers that already hold the exit address: every
    // structural register this port owns has been measured sound at the point it hands control to
    // the guest, so the remaining question is whether the faulting address is COMPUTED IN A
    // REGISTER, and this is the one place that can answer it.
    std::uint32_t holders[kNumGpr] = {};
    std::uint32_t holderCount = 0u;
    for (std::uint32_t index = 0; index < kNumGpr; ++index) {
      if (core->r[index] == first.guestPc) {
        holders[holderCount++] = index;
      }
    }
    lucent::error("x4-guest",
                  "guest call 0x{:08X} exited {} at 0x{:08X} after {} cycles, and this owner has no "
                  "return point for it: {}. {} of the {} general registers already hold that "
                  "address{}",
                  address,
                  psx::cpu::executionExitName(first.reason),
                  first.guestPc,
                  first.cycles,
                  first.detail,
                  holderCount,
                  kNumGpr,
                  holderCount == 0u ? " - so it was NOT in a register at the fault, which puts its origin upstream "
                                      "of this Core entirely"
                                    : "");
    for (std::uint32_t index = 0; index < holderCount; ++index) {
      lucent::error("x4-guest",
                    "  guest call 0x{:08X}: r[{}] == 0x{:08X}, the faulting address itself",
                    address,
                    holders[index],
                    first.guestPc);
    }
    lucent::error("x4-guest",
                  "  guest call 0x{:08X} register file at the fault: r0=0x{:08X} r1=0x{:08X} "
                  "r2=0x{:08X} r3=0x{:08X} r4=0x{:08X} r5=0x{:08X} r6=0x{:08X} r7=0x{:08X} "
                  "r8=0x{:08X} r9=0x{:08X} r10=0x{:08X} r11=0x{:08X} r28=0x{:08X} r29=0x{:08X} "
                  "r30=0x{:08X} r31=0x{:08X}",
                  address,
                  core->r[0],
                  core->r[1],
                  core->r[2],
                  core->r[3],
                  core->r[4],
                  core->r[5],
                  core->r[6],
                  core->r[7],
                  core->r[8],
                  core->r[9],
                  core->r[10],
                  core->r[11],
                  core->r[28],
                  core->r[29],
                  core->r[30],
                  core->r[31]);
    std::abort();
  }
  lucent::error("x4-guest",
                "guest call 0x{:08X} outlived one host turn and this owner has NO return point for "
                "it, so there is no boundary to resume against: {} cycles at 0x{:08X}. Supply one - "
                "the return address is the `jal` that targets this entry, plus 8. Refusing rather "
                "than resuming against `core->r[31]`, which is a stale return address left by "
                "whatever the guest called last.",
                address,
                first.cycles,
                first.guestPc);
  std::abort();
}

void callWithRegisterReturn(Core *core, std::uint32_t address) {
  if (!core) {
    lucent::error("x4-guest", "guest call 0x{:08X} received a null Core", address);
    std::abort();
  }
  requireOwnedEntry(core, address, "x4::guest::callWithRegisterReturn");
  const std::uint32_t returnPc = core->r[31];
  if (!core->currentImageIdentity(returnPc)) {
    lucent::error("x4-guest",
                  "guest call 0x{:08X} is dispatching through a link register of 0x{:08X}, which is "
                  "not in any code image. Either this owner did not set `r[31]` to the return "
                  "address of the call it stands in for, or the guest left a stale value there.",
                  address,
                  returnPc);
    std::abort();
  }
  psx::cpu::callGuestToReturnResuming(*core, "Mega Man X4 guest call with a register return point", address, returnPc);
}

psx::cpu::ExecutionResult dispatch(Core &core, std::uint32_t address) {
  return psx::cpu::dispatchGuest(core, address, psx::cpu::ExecutionBudget::currentTurn(core));
}

} // namespace x4::guest