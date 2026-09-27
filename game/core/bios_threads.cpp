#include "bios_threads.h"

#include "core.h"
#include "coro.h"
#include "execution_exit.h"
#include "game.h"
#include "guest_execution.h"
#include "native_dispatch.h"
#include "platform_hle.h"
#include "x4_context.h"

#include <cstdlib>
#include <lucent/log.h>
#include <utility>

namespace x4::bios_threads {
namespace {

// One task turn is one display field of guest CPU between two of the task's own field boundaries.
// Retail `DecDCTvlc` (0x800ED574) measures 610,746 cycles, 1.082 fields, so the measured maximum is
// 2. This cap is stated policy, not a measurement, and exists so the budget-resume path above can
// report a guest loop instead of spinning on one.
constexpr uint32_t kMaxTurnFields = 8u;

// Run-lifetime diagnostic tally, NOT execution state: nothing in the execution path reads or writes
// a Core through it, and the loop keeps no cross-turn suspend record. It exists so the lines that DO
// fire carry a denominator, because a run whose task retired at field 14 and a run that played a
// 200-field movie look identical from outside the product.
struct TaskCensus {
  uint64_t turns = 0;
  uint64_t fieldResumes = 0;
  uint64_t budgetResumes = 0;
  uint64_t budgetCycles = 0;
};

TaskCensus census;

void run_guest_entry(Core &core, uint32_t entry) {
  // THE TASK ACTIVATION'S RETURN ADDRESS, captured ONCE, before anything has run.
  //
  // It is a property of the activation `OpenTh` created, not of the turn, and it must never be
  // re-read from the guest. A title field boundary is reached through a guest `jal` to a host
  // service, so the continuation the guest expects IS `r[31]` by construction: measured
  // 0x80018BBC `jal VSync` with delay slot 0x80018BC0 resumes at 0x80018BC4, and
  // `x4::movie::fieldBoundary` correctly requests exactly that address. `x4::guest::dispatch` asks
  // the executor to stop at `core.r[31]`, and `LightrecExecutor::blockBoundary` classifies
  // `guestPc == returnAddress` as `GuestReturn` — so a resume that re-derives the return address
  // from `r[31]` is indistinguishable from the guest returning, and the fiber retires at the FIRST
  // field wait. That is what this function did.
  //
  // MEASURED on SLUS_005.61 before the fix (scratch/d2/fiber_retire.gdb, 40 host fields): turn 1
  // dispatched 0x8001D064 with `r[31]`=0x00000000 and exited frame-boundary at 0x80018BC4; turn 2
  // dispatched 0x80018BC4 with `r[31]`=0x80018BC4, received `guest-return` instead of executing
  // the retry increment at 0x80018BC4, and the task was never entered again. The guest's STR frame
  // pull therefore never advanced past its first field wait.
  //
  // WHY 0 IS THE HONEST VALUE HERE, not an invented sentinel. The guest supplies OpenTh with three
  // arguments and no return address. Measured, per call site: at 0x800126F8 a1 is `lw $5,0x10($2)`
  // (task descriptor +0x10) and a2 is `lw $6,0x44($2)` (+0x44), with a0 loaded from the global
  // 0x8013F490; at 0x80012788 a0 is the creator's own `entry` argument in the delay slot, a1 is
  // `lw $5,-0x7ef0($1)` and a2 is `lw $6,-0x7ebc($1)`, both from a per-slot table based at 0x8020.
  // Neither sequence stores a return address, and no task-descriptor word or task-stack word carries
  // one, so the activation has no guest return address and `Service::open`'s zero-initialised
  // register file says so. A task body that really ends — measured `jr $ra` at 0x800182E0 and
  // 0x800185F0 — therefore lands on the activation's own return address and is still reported as the
  // guest return that it is.
  const std::uint32_t taskReturnAddress = core.r[31];

  std::uint32_t resumeAddress = entry;
  bool suspended = false;
  uint32_t budgetTurns = 0u;
  for (;;) {
    // The first turn is a dispatch of the task entry, so it goes through the title's dispatcher. Every
    // later turn is a resume of a body already suspended mid-function, which is what the framework's
    // named resume primitive exists for — and it takes the call's ENTRY separately, because the resume
    // point is mid-function and cannot stand in for it. The task body PC never changes, so `entry` is
    // both the first dispatch's address and the entry every resume must be attributed to, which is what
    // a fresh `dispatchGuest` would have produced (runtime/psx/ot_attr.cpp reads that attribution).
    const psx::cpu::ExecutionResult result =
        suspended ? psx::cpu::resumeGuestToReturnFrom(
                        core, entry, resumeAddress, taskReturnAddress, psx::cpu::ExecutionBudget::currentTurn(core))
                  : guest::dispatch(core, resumeAddress);
    ++census.turns;
    if (result.returned()) {
      lucent::info("x4-thread",
                   "retail task entry 0x{:08X} reached its activation's return address 0x{:08X} and "
                   "RETIRED after {} turn(s) ({} guest field-boundary resume(s), {} host-turn budget "
                   "resume(s), {} guest cycles over those budget resumes). It is no longer scheduled",
                   entry,
                   result.guestPc,
                   census.turns,
                   census.fieldResumes,
                   census.budgetResumes,
                   census.budgetCycles);
      return;
    }
    if (result.reason == psx::cpu::ExecutionExitReason::BudgetExhausted) {
      // BUDGET EXHAUSTION IS AN ORDINARY BOUNDED EXIT, not a failure. The executor contract says
      // host code "commits and handles that state, then resumes deliberately", and a retail task
      // body can need more than one display field of guest CPU between two of its own field waits —
      // the measured one is `DecDCTvlc` (0x800ED574) at 610,746 cycles, 1.082 fields, which the
      // title's `x4::guest::call` path already resumes. Treating it as fatal retired the task at the
      // first long decode instead of resuming it.
      //
      // A resume must not become a spin, so it is fenced by what it can MEASURE, not by a count it
      // guesses:
      //   1. a turn that exhausts its budget having consumed no guest cycles made no progress, so
      //      resuming it could only repeat that segment — a fact about the exit, not a policy;
      //   2. one turn spending kMaxTurnFields display fields of guest CPU WITHOUT reaching a guest
      //      field boundary. That one IS a policy: retail delivers a field every field, so a task
      //      that never reaches its own wait inside that many is a guest loop. It is stated here,
      //      set far above anything measured, and reported when it fires.
      if (result.cycles == 0u || result.guestPc == 0u) {
        lucent::error("x4-thread",
                      "guest task exhausted the host turn at 0x{:08X} having consumed no guest "
                      "cycles ({}), so resuming it could only repeat the same segment: {}",
                      result.guestPc,
                      result.detail,
                      psx::cpu::executionExitName(result.reason));
        std::abort();
      }
      if (++budgetTurns >= kMaxTurnFields) {
        lucent::error("x4-thread",
                      "guest task spent {} display field(s) of guest CPU without reaching a field "
                      "boundary and is still at 0x{:08X}. Retail delivers a field every field, so "
                      "this is a guest loop: reported rather than spun on",
                      budgetTurns,
                      result.guestPc);
        std::abort();
      }
      ++census.budgetResumes;
      census.budgetCycles += result.cycles;
      lucent::info("x4-thread",
                   "retail task entry 0x{:08X} needed more than one display field of guest CPU and was "
                   "RESUMED at 0x{:08X} after {} cycle(s) in that turn: the executor contract makes "
                   "budget exhaustion an ordinary bounded exit, not a failure. Denominator: {} of {} "
                   "task turn(s) have needed a budget resume, {} guest cycle(s) over them; the other "
                   "{} reached a guest field boundary",
                   entry,
                   result.guestPc,
                   result.cycles,
                   census.budgetResumes,
                   census.turns,
                   census.budgetCycles,
                   census.turns - census.budgetResumes);
      resumeAddress = result.guestPc;
      suspended = true;
      // The field clock is already owed this turn, so the host field loop must run before the
      // resume; the fiber parks exactly as it does for a guest-authored field wait.
      from(core).yieldToMain();
      continue;
    }
    if (result.reason != psx::cpu::ExecutionExitReason::FrameBoundary) {
      lucent::error("x4-thread",
                    "guest task stopped at 0x{:08X} with unexpected {} boundary: {}",
                    result.guestPc,
                    psx::cpu::executionExitName(result.reason),
                    result.detail);
      std::abort();
    }

    // Frame boundaries preserve this task's host and guest stacks. The frame driver explicitly
    // resumes at the typed guest PC on the next scheduler turn.
    budgetTurns = 0u;
    ++census.fieldResumes;
    resumeAddress = result.guestPc;
    suspended = true;
    from(core).yieldToMain();
  }
}

void open_thread(Core *core) {
  const uint32_t handle = from(*core).open(core->r[4], core->r[5], core->r[6]);
  core->r[2] = handle;
  if (handle == UINT32_MAX) {
    lucent::error("x4-thread", "OpenTh exhausted the four TCBs declared by SYSTEM.CNF");
    std::abort();
  }
}

void close_thread(Core *core) {
  const uint32_t handle = core->r[4];
  if (!from(*core).close(handle)) {
    lucent::error("x4-thread", "CloseTh refused unknown or already-closed handle 0x{:08X}", handle);
    std::abort();
  }
  core->r[2] = 1;
}

void change_thread(Core *core) {
  const uint32_t handle = core->r[4];
  core->r[2] = handle;
  if (!from(*core).change(handle)) {
    lucent::error("x4-thread", "ChangeTh refused invalid transfer to handle 0x{:08X}", handle);
    std::abort();
  }
}

} // namespace

Service::Service(Core &core, EntryRunner entryRunner)
    : core_(core), entryRunner_(entryRunner ? std::move(entryRunner) : EntryRunner{run_guest_entry}) {
  threads_[0].open = true;
}

// The census is reported from the two state changes that can end or reshape a task's life — a budget
// resume and the retirement — rather than from teardown, because the product owns its Game for the
// whole process (game/core/main.cpp never deletes it) and a destructor line would never print.
Service::~Service() = default;

int Service::slotForHandle(uint32_t handle) {
  if ((handle & 0xFFFFFF00u) != kMainThreadHandle) {
    return -1;
  }
  const int slot = static_cast<int>(handle & 0xFFu);
  return slot < kThreadCount ? slot : -1;
}

uint32_t Service::open(uint32_t entry, uint32_t stackPointer, uint32_t globalPointer) {
  for (int slot = 1; slot < kThreadCount; ++slot) {
    Thread &thread = threads_[slot];
    // A self-closing task remains on its Coro stack until it yields back to main. Reusing that TCB
    // here would destroy the fiber that is executing this call. Deferred close makes the slot
    // available only after Service::change has regained the main stack.
    if (thread.open || slot == activeSlot_) {
      continue;
    }
    thread = Thread{};
    thread.open = true;
    thread.entry = entry;
    thread.regs.r[29] = stackPointer;
    thread.regs.r[28] = globalPointer;
    thread.regs.pc = entry;
    lucent::debug("x4-thread",
                  "OpenTh handle=0x{:08X} entry=0x{:08X} sp=0x{:08X} gp=0x{:08X}",
                  handleForSlot(slot),
                  entry,
                  stackPointer,
                  globalPointer);
    return handleForSlot(slot);
  }
  return UINT32_MAX;
}

bool Service::close(uint32_t handle) {
  const int slot = slotForHandle(handle);
  if (slot <= 0 || !threads_[slot].open) {
    return false;
  }
  Thread &thread = threads_[slot];
  thread.open = false;
  if (activeSlot_ == slot) {
    thread.closePending = true;
  } else {
    thread = Thread{};
  }
  return true;
}

void Service::startFiber(int slot) {
  Thread &thread = threads_[slot];
  thread.fiber = std::make_unique<Coro>();
  thread.fiber->start([this, slot] {
    Thread &running = threads_[slot];
    entryRunner_(core_, running.entry);
  });
}

void Service::finishDeferredClose(int slot) {
  Thread &thread = threads_[slot];
  if (!thread.closePending) {
    return;
  }
  thread = Thread{};
}

bool Service::change(uint32_t handle) {
  const int target = slotForHandle(handle);
  if (target < 0 || !threads_[target].open) {
    return false;
  }

  if (activeSlot_ != 0) {
    // X4's measured contract is task -> main. Supporting task -> task here without retail evidence
    // would invent nested scheduling semantics and permit two fibers to own one Core.
    if (target != 0) {
      return false;
    }
    Thread &running = threads_[activeSlot_];
    running.regs = static_cast<R3000 &>(core_);
    running.fiber->yield();
    return true;
  }

  if (target == 0) {
    return true;
  }

  Thread &thread = threads_[target];
  mainRegs_ = static_cast<R3000 &>(core_);
  static_cast<R3000 &>(core_) = thread.regs;
  activeSlot_ = target;
  if (!thread.fiber) {
    startFiber(target);
  }
  lucent::debug("x4-thread", "ChangeTh main -> 0x{:08X} entry=0x{:08X} sp=0x{:08X}", handle, thread.entry, core_.r[29]);
  thread.fiber->resume();
  thread.regs = static_cast<R3000 &>(core_);
  activeSlot_ = 0;
  static_cast<R3000 &>(core_) = mainRegs_;
  finishDeferredClose(target);
  return true;
}

void Service::yieldToMain() {
  if (activeSlot_ <= 0 || activeSlot_ >= kThreadCount) {
    lucent::error("x4-thread", "title field yield ran outside a retail task fiber");
    std::abort();
  }
  Thread &running = threads_[activeSlot_];
  if (!running.open || !running.fiber || running.fiber->done()) {
    lucent::error("x4-thread", "title field yield has no live retail task fiber");
    std::abort();
  }
  running.regs = static_cast<R3000 &>(core_);
  running.fiber->yield();
}

bool Service::isOpen(uint32_t handle) const {
  const int slot = slotForHandle(handle);
  return slot >= 0 && threads_[slot].open;
}

bool Service::isDone(uint32_t handle) const {
  const int slot = slotForHandle(handle);
  return slot > 0 && threads_[slot].fiber && threads_[slot].fiber->done();
}

Service &from(Core &core) {
  return x4::context(core).biosThreads;
}

void install(Game &game) {
  game.platform_hle.register_(kOpenThread, open_thread);
  game.platform_hle.register_(kCloseThread, close_thread);
  game.platform_hle.register_(kChangeThread, change_thread);
  lucent::info("x4-thread",
               "retail BIOS thread services installed at OpenTh=0x{:08X}, CloseTh=0x{:08X}, "
               "ChangeTh=0x{:08X}",
               kOpenThread,
               kCloseThread,
               kChangeThread);
}

} // namespace x4::bios_threads
