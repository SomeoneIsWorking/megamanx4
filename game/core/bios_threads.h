#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <memory>

#include "r3000.h"

class Coro;
class Game;
class Core;

namespace x4::bios_threads {

// Retail SLUS_005.61 links the three BIOS-thread thunks contiguously. The half-open window is also
// the exact PlatformHle ownership range declared by the title's measured compatibility facts.
constexpr uint32_t kOpenThread = 0x800EDD9Cu;
constexpr uint32_t kCloseThread = 0x800EDDACu;
constexpr uint32_t kChangeThread = 0x800EDDBCu;
constexpr uint32_t kThreadWindowEnd = 0x800EDDCCu;

// SYSTEM.CNF declares TCB=4: slot zero is the boot/main thread and the remaining three are the task
// threads created by the retail scheduler at 0x80012740. Handles encode the TCB slot in their low
// byte; the game explicitly switches back to 0xFF000000 after each cooperative task slice.
constexpr uint32_t kMainThreadHandle = 0xFF000000u;
constexpr int kThreadCount = 4;

using EntryRunner = std::function<void(Core &, uint32_t)>;

// Per-Core BIOS-thread execution service. This is not a replacement for X4's scheduler: untouched
// retail func_80012600 still chooses a task and calls ChangeTh. This class owns only the missing BIOS
// context contract underneath it: OpenTh captures entry/SP/GP, ChangeTh ping-pongs between main and a
// task without destroying either C stack, and CloseTh releases the selected TCB.

// WHICH GLOBAL POINTER A NEW THREAD RUNS WITH, and why it is a named policy rather than an
// expression buried in a dispatch thunk.
//
// MEASURED 2026-09-29 over five OpenTh calls in one product run: SLUS_005.61 passes
// `a2 = 0x00000000` on every single call. It does not use the BIOS's third argument. The first two
// of those calls show the creating context's `gp` as 0x8012F418 - the real global base, read from
// the loaded EXE - and the last three show 0x00000000, because the contexts making them had
// already been resumed with a null gp by this same defect.
//
// So this game relies on a thread inheriting the creating context's global base. Taking the
// guest's 0 at face value resumed every task with `$gp = 0`, and MMX4's code is `$gp`-relative
// throughout, so such a task takes every global access to address 0 - reading and writing the low
// 16 KB of RAM in place of its own statics.
//
// A caller that DOES pass an explicit gp still wins, because that is a deliberate choice by the
// guest. Only the zero case inherits, and a zero caller with a zero request stays zero: the port
// does not invent a global base, and a thread opened from a context that has already lost its gp
// is reported by the switch census rather than silently repaired.
[[nodiscard]] inline constexpr uint32_t resolveThreadGlobalPointer(uint32_t requested,
                                                                   uint32_t callerGlobalPointer) noexcept {
  return requested != 0 ? requested : callerGlobalPointer;
}

class Service {
public:
  explicit Service(Core &core, EntryRunner entryRunner = {});
  ~Service();

  Service(const Service &) = delete;
  Service &operator=(const Service &) = delete;

  uint32_t open(uint32_t entry, uint32_t stackPointer, uint32_t globalPointer);
  bool close(uint32_t handle);
  bool change(uint32_t handle);

  // Title-owned finite boundaries may park the currently running retail task without dispatching
  // the guest ChangeTh thunk. The preserved Coro stack resumes on the next retail scheduler turn;
  // callers must already be executing inside one of the measured non-main TCBs.
  void yieldToMain();

  // Whether a field wait has a fiber to park. `yieldToMain` aborts when it does not, so an owner
  // that must decide BEFORE parking — because that decision is a guest-behaviour claim and belongs
  // in its own refusal message — asks this first. The main TCB (slot 0) is the boot/main thread and
  // never has a fiber: its field cadence is the frame driver's, not a parkable task's.
  [[nodiscard]] bool inTaskFiber() const {
    return activeSlot_ > 0 && activeSlot_ < kThreadCount;
  }

  [[nodiscard]] bool isOpen(uint32_t handle) const;
  [[nodiscard]] bool isDone(uint32_t handle) const;

  static constexpr uint32_t handleForSlot(int slot) {
    return kMainThreadHandle | static_cast<uint32_t>(slot);
  }

private:
  struct Thread {
    bool open = false;
    bool closePending = false;
    uint32_t entry = 0;
    R3000 regs{};
    std::unique_ptr<Coro> fiber;
  };

  Core &core_;
  EntryRunner entryRunner_;
  std::array<Thread, kThreadCount> threads_{};
  R3000 mainRegs_{};
  int activeSlot_ = 0;

  [[nodiscard]] static int slotForHandle(uint32_t handle);
  void startFiber(int slot);
  void finishDeferredClose(int slot);
};

void install(Game &game);
Service &from(Core &core);

} // namespace x4::bios_threads
