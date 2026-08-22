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
class Service {
public:
  explicit Service(Core &core, EntryRunner entryRunner = {});
  ~Service();

  Service(const Service &) = delete;
  Service &operator=(const Service &) = delete;

  uint32_t open(uint32_t entry, uint32_t stackPointer, uint32_t globalPointer);
  bool close(uint32_t handle);
  bool change(uint32_t handle);

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
