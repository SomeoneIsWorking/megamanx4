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
void call(Core *core, std::uint32_t address);

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
