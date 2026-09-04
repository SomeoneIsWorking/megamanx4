#include "bios_threads.h"

#include "core.h"
#include "coro.h"
#include "game.h"
#include "guest_execution.h"
#include "platform_hle.h"
#include "x4_context.h"

#include <cstdlib>
#include <lucent/log.h>
#include <utility>

namespace x4::bios_threads {
namespace {

void run_guest_entry(Core &core, uint32_t entry) {
  std::uint32_t resumeAddress = entry;
  for (;;) {
    const psx::cpu::ExecutionResult result = guest::dispatch(core, resumeAddress);
    if (result.returned()) {
      return;
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
    resumeAddress = result.guestPc;
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
