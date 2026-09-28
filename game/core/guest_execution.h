#pragma once

#include "execution_exit.h"

#include <cstdint>

class Core;

namespace x4::guest {

using NativeFunction = void (*)(Core *);

// Enter one authenticated guest function through the product Lightrec dispatcher and require its
// ordinary return. `ExecutionBudget::currentTurn` is ONE display field by construction, and the
// executor contract makes exhausting it an ordinary bounded exit that host code "commits and
// handles, then resumes deliberately" — so a turn that ends BudgetExhausted is RESUMED here
// through psx::cpu::resumeGuestToReturn, not treated as a failed call. Typed frame/yield/fault
// exits remain explicit at their owning boundaries.
//
// `returnPc` IS the boundary the call must reach to return, and it is NOT optional for a native
// owner. Measured 2026-09-29 (`docs/issues/0037`): a one-argument form that took the boundary from
// `core->r[31]` gave the RLE decompress call at 0x80016FF4 the boundary 0x80022060 — the return
// address of an UNRELATED `jal 0x80015ecc` at 0x80022058. The decompressor cannot return there, so
// it ran 757,804 cycles past its own end and faulted at a non-address. A `r[31]` is a return address
// only when GUEST code executed the `jal`, and no native owner can supply one that way.
//
// The return address is a property of the guest call this owner is standing in for, so it comes from
// the guest image: `tools/census_guest_call_sites.py` reports every `jal` that targets an entry, and
// the boundary is `jal + 8` (a `jal` links `$ra` to PC+8, because of the delay slot). Supply it
// explicitly rather than letting it be guessed.
void call(Core *core, std::uint32_t address, std::uint32_t returnPc);

// Call a guest entry WITHOUT a known return point. This is honest only while the call is PROVEN to
// finish inside one host turn, because a turn that ends BudgetExhausted is exactly the case where
// the boundary is consulted — and with no boundary there is none to consult. So this form measures
// rather than assumes: if the call outlives its first host turn it REFUSES, naming the entry and
// telling the owner to supply the return address, instead of resuming against a stale `r[31` and
// running off the end of the function. Measured 2026-09-29: 2 of 46,715 completed calls on this
// title outlive one host turn, so the refusal fires rarely and names a real gap when it does.
void callWithoutKnownReturn(Core *core, std::uint32_t address);

// Call a guest entry whose caller has ALREADY set `core->r[31]` to the return address — which is
// what emulating a `jal` means, and what `stream_startup` and `movie_cleanup` do in their own `call`
// helpers before dispatching.
//
// This exists because those owners take a `GuestDispatch` function pointer, so the boundary cannot be
// a third argument without widening that type across the whole title. The alternative — the old
// behaviour — read `r[31]` SILENTLY, and the decompress owner did not set it, so it inherited
// 0x80022060 (the return address of an unrelated `jal`) and ran 757,804 cycles off the end of its
// function. **The difference between the two is that this one CHECKS.** `r[31]` is verified to
// resolve in a code image before it is used as a boundary, so an owner that forgot to set it is
// refused and named instead of silently corrupting the run.
//
// A verified register is a stated contract; a guessed one is not. Measured 2026-09-29, the
// `stream_startup` call to DecDCTvlc would be refused here if its helper had not set `r[31` first,
// and the census confirms 0x80018AA0 is one of exactly TWO `jal` sites targeting 0x800ED574 in
// 294,400 scanned words.
void callWithRegisterReturn(Core *core, std::uint32_t address);

// Enter guest code while preserving a typed execution boundary for the host owner to handle. This
// entry point does NOT resume: its owner decides what a turn boundary means (x4::bios_threads
// takes FrameBoundary and yields the task). It reports BudgetExhausted unchanged.
psx::cpu::ExecutionResult dispatch(Core &core, std::uint32_t address);

// Enter the original guest body while suppressing only the currently selected native override,
// resuming a turn that ends BudgetExhausted exactly as call() does — through
// psx::cpu::resumeOriginal, which re-establishes that suppression scope for every resumed segment.
void callOriginal(Core *core, std::uint32_t address, const char *owner);

// Register a title-native function against the active authenticated image identity.
void install(Core &core, std::uint32_t address, const char *name, NativeFunction function);

// The run's guest-call census: calls completed, how many of those needed a resume, the deepest call
// in host turns, and the guest CPU the resumed calls spent. Printed by the title's run-end path so a
// run in which nothing was ever resumed says so, instead of the silence that a conditional report
// alone would leave behind.
void reportGuestCallCensus(const char *why);

} // namespace x4::guest
