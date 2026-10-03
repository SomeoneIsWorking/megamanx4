#pragma once

#include "execution_exit.h"

#include <cstdint>

class Core;

namespace x4::guest {

// The guest-call entry points that are THIS TITLE'S FACTS; the resume loop, the boundary latch, the
// turn cap, the refusals and the override install are `psx::cpu::ResumableGuestCall`,
// `callGuestToReturnResuming`, `callOriginalResumingToReturn` and `installNativeOverride`.
//
// Every measured fact that justifies them lives in those four titles' own history and in
// `psxport/docs/codemap.md`; what is left here is the evidence ONE title owns and the framework
// cannot: which of its entries has a known return address, and which registers must be checked.

// Call a guest entry WITHOUT a known return point. Honest only while the call is PROVEN to finish
// inside one host turn, because a turn that ends BudgetExhausted is exactly the case where the
// boundary is consulted — and with no boundary there is none to consult. So this form MEASURES
// rather than assumes: if the call outlives its first host turn it refuses, naming the entry and the
// registers that already hold the exit address, instead of resuming against a stale `r[31]`.
void callWithoutKnownReturn(Core *core, std::uint32_t address);

// Call a guest entry whose caller has ALREADY set `core->r[31]` to the return address — which is
// what emulating a `jal` means, and what the owners that pass this as a function pointer do in their
// own helpers before dispatching.
//
// The link register is VERIFIED to resolve in a code image before it is used as a boundary, so an
// owner that forgot to set it is refused and named instead of silently corrupting the run. A
// verified register is a stated contract; a guessed one is not.
void callWithRegisterReturn(Core *core, std::uint32_t address);

// Enter guest code while preserving a typed execution boundary for the host owner to handle. This
// entry point does NOT resume: its owner decides what a turn boundary means (x4::bios_threads takes
// FrameBoundary and yields the task). It reports BudgetExhausted unchanged.
psx::cpu::ExecutionResult dispatch(Core &core, std::uint32_t address);

} // namespace x4::guest