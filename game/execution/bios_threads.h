#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <string_view>

#include "r3000.h"

class Coro;
class Game;
class Core;

namespace x4::bios_threads {
// SLUS_005.61 links the three BIOS-thread thunks contiguously; the half-open window is the HLE range.
constexpr uint32_t kOpenThread = 0x800EDD9Cu;
constexpr uint32_t kCloseThread = 0x800EDDACu;
constexpr uint32_t kChangeThread = 0x800EDDBCu;
constexpr uint32_t kThreadWindowEnd = 0x800EDDCCu;

// SYSTEM.CNF TCB=4: slot 0 is main, slots 1-3 are scheduler tasks (created at 0x80012740).
// Handles carry the slot in the low byte; the game switches back to 0xFF000000 after each task slice.
constexpr uint32_t kMainThreadHandle = 0xFF000000u;
constexpr int kThreadCount = 4;

// Over-budget turns a task may take in one frame before the run reports a guest loop.
constexpr uint32_t kMaxTurnFields = 512u;

using EntryRunner = std::function<void(Core &, uint32_t)>;

// Per-Core BIOS-thread service under retail func_80012600, which still picks the task and calls ChangeTh.

// The guest passes a2 = 0 to OpenTh and its code is $gp-relative, so a zero request inherits the creator's gp.
// An explicit gp wins; a zero creator stays zero and shows up in the switch census.
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

  // Park the running task without dispatching the guest ChangeTh thunk; must be inside a non-main TCB.
  void yieldToMain();

  // Counts one over-budget turn of the running task; true once it has gone kMaxTurnFields without
  // yielding through ChangeTh or reaching a field wait.
  [[nodiscard]] bool spendBudgetTurn();

  // A task parked on an exhausted turn budget is still inside its guest frame: retail's UpdateTasks has not
  // returned, so the draw prefix and tail must not run for it.
  [[nodiscard]] bool frameInProgress() const;

  // Whether a field wait has a fiber to park; the main TCB never has one.
  [[nodiscard]] bool inTaskFiber() const {
    return activeSlot_ > 0 && activeSlot_ < kThreadCount;
  }

  [[nodiscard]] bool isOpen(uint32_t handle) const;
  [[nodiscard]] bool isDone(uint32_t handle) const;

  // Run-end task census; not a destructor line because the product never deletes its Game.
  void reportCensus(std::string_view phase) const;

  static constexpr uint32_t handleForSlot(int slot) {
    return kMainThreadHandle | static_cast<uint32_t>(slot);
  }

private:
  struct Thread {
    bool open = false;
    bool closePending = false;
    uint32_t entry = 0;
    // Stack top from OpenTh; the stack grows down, so a resumed sp above it is foreign.
    uint32_t stackTop = 0;
    R3000 regs{};
    // Consecutive over-budget turns since the task last finished a frame or reached a field wait.
    uint32_t budgetTurns = 0;
    std::unique_ptr<Coro> fiber;
  };

  // `retirements` counts activations that reached their own return address.
  struct TurnCensus {
    std::uint64_t turns = 0;
    std::uint64_t fieldResumes = 0;
    std::uint64_t budgetResumes = 0;
    std::uint64_t budgetCycles = 0;
    std::uint64_t retirements = 0;
  };

  // `open` leaves r[31] zero, so pc and r[31] are classified against the code images at each switch.
  struct SwitchCensus {
    std::uint64_t resumes = 0;
    std::uint64_t pcInCodeImage = 0;
    std::uint64_t pcNotInCodeImage = 0;
    std::uint64_t raZero = 0;
    std::uint64_t raInCodeImage = 0;
    std::uint64_t raNotInCodeImage = 0;
    // A valid pc and r[31] can still sit on a foreign stack.
    std::uint64_t spAboveDeclaredStack = 0;
    std::uint64_t spZero = 0;
  };

  Core &core_;
  EntryRunner entryRunner_;
  std::array<Thread, kThreadCount> threads_{};
  R3000 mainRegs_{};
  int activeSlot_ = 0;
  TurnCensus turnCensus_{};
  SwitchCensus switchCensus_{};

  [[nodiscard]] static int slotForHandle(uint32_t handle);
  // Host owner of one task body: dispatch, park on each field boundary, resume at the typed exit PC.
  void runGuestEntry(Core &core, uint32_t entry);
  void startFiber(int slot);
  void finishDeferredClose(int slot);
  void reportSwitchCensus() const;
};

void install(Game &game);
Service &from(Core &core);

} // namespace x4::bios_threads
