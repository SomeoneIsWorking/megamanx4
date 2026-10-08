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
#include <string_view>
#include <utility>

namespace x4::bios_threads {
namespace {

// A task turn past this many display fields without a guest field boundary is a guest loop.
constexpr uint32_t kMaxTurnFields = 512u;
// libetc VBlank counter; game/frame/vsync_sync.h owns the boundary it counts.
constexpr uint32_t kVblankCounter = 0x8011DC50u;

// A pc outside every code image reports at once; otherwise every Nth resume does.
constexpr std::uint64_t kSwitchCensusReportStride = 1000u;

} // namespace

void Service::reportSwitchCensus() const {
  lucent::info("x4-thread",
               "fiber-switch census: {} task resume(s) scanned; {} resumed with a pc inside a code "
               "image, {} with one outside EVERY code image; of their link registers, {} were zero "
               "(`Service::open` never initialises r[31]), {} were in a code image and {} were not; "
               "of their stack pointers, {} were ABOVE the stack top the guest handed OpenTh and {} "
               "were zero",
               switchCensus_.resumes,
               switchCensus_.pcInCodeImage,
               switchCensus_.pcNotInCodeImage,
               switchCensus_.raZero,
               switchCensus_.raInCodeImage,
               switchCensus_.raNotInCodeImage,
               switchCensus_.spAboveDeclaredStack,
               switchCensus_.spZero);
}

void Service::reportCensus(std::string_view phase) const {
  lucent::info("x4-thread",
               "task-turn census ({}): {} task turn(s) dispatched; {} ended at a guest field boundary "
               "and {} ended BudgetExhausted over {} guest cycle(s); {} activation(s) reached their "
               "own return address and RETIRED. Denominator: {} of {} turn(s) needed a budget resume",
               phase,
               turnCensus_.turns,
               turnCensus_.fieldResumes,
               turnCensus_.budgetResumes,
               turnCensus_.budgetCycles,
               turnCensus_.retirements,
               turnCensus_.budgetResumes,
               turnCensus_.turns);
  reportSwitchCensus();
}

void Service::runGuestEntry(Core &core, uint32_t entry) {
  // Captured once: OpenTh gets no return address, and a field boundary resumes after the guest `jal`.
  // Real task returns (`jr $ra` at 0x800182E0, 0x800185F0) land on this address.
  const std::uint32_t taskReturnAddress = core.r[31];

  std::uint32_t resumeAddress = entry;
  bool suspended = false;
  uint32_t budgetTurns = 0u;
  for (;;) {
    // First turn dispatches the entry; later turns resume mid-function but stay attributed to `entry`.
    const psx::cpu::ExecutionResult result =
        suspended ? psx::cpu::resumeGuestToReturnFrom(
                        core, entry, resumeAddress, taskReturnAddress, psx::cpu::ExecutionBudget::currentTurn(core))
                  : guest::dispatch(core, resumeAddress);
    ++turnCensus_.turns;
    if (result.returned()) {
      ++turnCensus_.retirements;
      lucent::info("x4-thread",
                   "retail task entry 0x{:08X} reached its activation's return address 0x{:08X} and "
                   "RETIRED after {} turn(s) ({} guest field-boundary resume(s), {} host-turn budget "
                   "resume(s), {} guest cycles over those budget resumes). It is no longer scheduled. "
                   "Fiber-switch census: {} task resume(s), {} resumed with a pc inside a code image "
                   "and {} with one outside every code image; of their link registers, {} were zero, "
                   "{} were in a code image and {} were not; {} resumed with sp ABOVE the stack top "
                   "the guest handed OpenTh, and {} with sp zero",
                   entry,
                   result.guestPc,
                   turnCensus_.turns,
                   turnCensus_.fieldResumes,
                   turnCensus_.budgetResumes,
                   turnCensus_.budgetCycles,
                   switchCensus_.resumes,
                   switchCensus_.pcInCodeImage,
                   switchCensus_.pcNotInCodeImage,
                   switchCensus_.raZero,
                   switchCensus_.raInCodeImage,
                   switchCensus_.raNotInCodeImage,
                   switchCensus_.spAboveDeclaredStack,
                   switchCensus_.spZero);
      return;
    }
    if (result.reason == psx::cpu::ExecutionExitReason::BudgetExhausted) {
      // Budget exhaustion is an ordinary bounded exit; resume unless the turn made no progress.
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
                      "boundary and is still at 0x{:08X} at display field {} (the measured libetc "
                      "VBlank counter at 0x{:08X}). Retail delivers a field every field, so this is a "
                      "guest loop: reported rather than spun on",
                      budgetTurns,
                      result.guestPc,
                      core.mem_r32(kVblankCounter),
                      kVblankCounter);
        std::abort();
      }
      ++turnCensus_.budgetResumes;
      turnCensus_.budgetCycles += result.cycles;
      lucent::info("x4-thread",
                   "retail task entry 0x{:08X} needed more than one display field of guest CPU and was "
                   "RESUMED at 0x{:08X} after {} cycle(s) in that turn: the executor contract makes "
                   "budget exhaustion an ordinary bounded exit, not a failure. Denominator: {} of {} "
                   "task turn(s) have needed a budget resume, {} guest cycle(s) over them; the other "
                   "{} reached a guest field boundary",
                   entry,
                   result.guestPc,
                   result.cycles,
                   turnCensus_.budgetResumes,
                   turnCensus_.turns,
                   turnCensus_.budgetCycles,
                   turnCensus_.turns - turnCensus_.budgetResumes);
      resumeAddress = result.guestPc;
      suspended = true;
      // The field clock is owed, so park like a guest-authored field wait.
      from(core).yieldToMain();
      continue;
    }
    if (result.reason != psx::cpu::ExecutionExitReason::FrameBoundary) {
      // guestPc is the branch target, not the branching instruction; dump every register.
      lucent::error("x4-thread",
                    "guest task 0x{:08X} faulted: pc=0x{:08X} r31=0x{:08X} vblank=0x{:08X} — the r31 "
                    "value is the guest's OWN link register, so it names the branch site that reached "
                    "this address; it is read from the committed task state, not reconstructed",
                    entry,
                    core.pc,
                    core.r[31],
                    core.mem_r32(kVblankCounter));
      lucent::error("x4-thread",
                    "guest task 0x{:08X} register file at the fault: r0=0x{:08X} r1=0x{:08X} r2=0x{:08X} "
                    "r3=0x{:08X} r4=0x{:08X} r5=0x{:08X} r6=0x{:08X} r7=0x{:08X}",
                    entry,
                    core.r[0],
                    core.r[1],
                    core.r[2],
                    core.r[3],
                    core.r[4],
                    core.r[5],
                    core.r[6],
                    core.r[7]);
      lucent::error("x4-thread",
                    "guest task 0x{:08X} register file at the fault: r8=0x{:08X} r9=0x{:08X} "
                    "r10=0x{:08X} r11=0x{:08X} r12=0x{:08X} r13=0x{:08X} r14=0x{:08X} r15=0x{:08X}",
                    entry,
                    core.r[8],
                    core.r[9],
                    core.r[10],
                    core.r[11],
                    core.r[12],
                    core.r[13],
                    core.r[14],
                    core.r[15]);
      lucent::error("x4-thread",
                    "guest task 0x{:08X} register file at the fault: r16=0x{:08X} r17=0x{:08X} "
                    "r18=0x{:08X} r19=0x{:08X} r20=0x{:08X} r21=0x{:08X} r22=0x{:08X} r23=0x{:08X}",
                    entry,
                    core.r[16],
                    core.r[17],
                    core.r[18],
                    core.r[19],
                    core.r[20],
                    core.r[21],
                    core.r[22],
                    core.r[23]);
      lucent::error("x4-thread",
                    "guest task 0x{:08X} register file at the fault: r24=0x{:08X} r25=0x{:08X} "
                    "r26=0x{:08X} r27=0x{:08X} r28=0x{:08X} r29=0x{:08X} r30=0x{:08X} hi=0x{:08X} "
                    "lo=0x{:08X}",
                    entry,
                    core.r[24],
                    core.r[25],
                    core.r[26],
                    core.r[27],
                    core.r[28],
                    core.r[29],
                    core.r[30],
                    core.hi,
                    core.lo);
      // Print $a0 in bytes as well as words; a single wrong byte in a record is invisible in a word dump.
      lucent::error("x4-thread",
                    "guest task 0x{:08X} argument record at a0=0x{:08X}, first 0x10 byte(s) as words: "
                    "w0=0x{:08X} w1=0x{:08X} w2=0x{:08X} w3=0x{:08X} | bytes: "
                    "{:02X} {:02X} {:02X} {:02X} {:02X} {:02X} {:02X} {:02X} "
                    "{:02X} {:02X} {:02X} {:02X} {:02X} {:02X} {:02X} {:02X}",
                    entry,
                    core.r[4],
                    core.mem_r32(core.r[4]),
                    core.mem_r32(core.r[4] + 4u),
                    core.mem_r32(core.r[4] + 8u),
                    core.mem_r32(core.r[4] + 12u),
                    core.mem_r8(core.r[4] + 0u),
                    core.mem_r8(core.r[4] + 1u),
                    core.mem_r8(core.r[4] + 2u),
                    core.mem_r8(core.r[4] + 3u),
                    core.mem_r8(core.r[4] + 4u),
                    core.mem_r8(core.r[4] + 5u),
                    core.mem_r8(core.r[4] + 6u),
                    core.mem_r8(core.r[4] + 7u),
                    core.mem_r8(core.r[4] + 8u),
                    core.mem_r8(core.r[4] + 9u),
                    core.mem_r8(core.r[4] + 10u),
                    core.mem_r8(core.r[4] + 11u),
                    core.mem_r8(core.r[4] + 12u),
                    core.mem_r8(core.r[4] + 13u),
                    core.mem_r8(core.r[4] + 14u),
                    core.mem_r8(core.r[4] + 15u));
      lucent::error("x4-thread",
                    "guest task stopped at 0x{:08X} with unexpected {} boundary: {}",
                    result.guestPc,
                    psx::cpu::executionExitName(result.reason),
                    result.detail);
      std::abort();
    }

    // Frame boundaries keep this task's stacks; the frame driver resumes at the typed guest PC.
    budgetTurns = 0u;
    ++turnCensus_.fieldResumes;
    resumeAddress = result.guestPc;
    suspended = true;
    from(core).yieldToMain();
  }
}

namespace {

void open_thread(Core *core) {
  // OpenTh gets a2 = 0 and the game is $gp-relative, so the thread inherits the creator's gp.
  const uint32_t requestedGlobalPointer = core->r[6];
  const uint32_t inheritedGlobalPointer = core->r[28];
  const uint32_t globalPointer = resolveThreadGlobalPointer(requestedGlobalPointer, inheritedGlobalPointer);
  lucent::info("x4-thread",
               "OpenTh entry=0x{:08X} sp=0x{:08X} gp=0x{:08X} (requested 0x{:08X}, inherited 0x{:08X})",
               core->r[4],
               core->r[5],
               globalPointer,
               requestedGlobalPointer,
               inheritedGlobalPointer);
  const uint32_t handle = from(*core).open(core->r[4], core->r[5], globalPointer);
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
    : core_(core), entryRunner_(entryRunner ? std::move(entryRunner)
                                            // The default runner is this owner so the census counts its own turns.
                                            : EntryRunner{[this](Core &c, uint32_t entry) {
                                                runGuestEntry(c, entry);
                                              }}) {
  threads_[0].open = true;
}

// Not reported from here: the product never deletes its Game; see `reportCensus`.
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
    // A self-closing task still runs on its Coro stack; close the slot after change() regains main.
    if (thread.open || slot == activeSlot_) {
      continue;
    }
    thread = Thread{};
    thread.open = true;
    thread.entry = entry;
    thread.regs.r[29] = stackPointer;
    thread.stackTop = stackPointer;
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
    // task -> task is refused: two fibers would own one Core.
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
  // Census before the load, so it reports what the task is resumed with.
  ++switchCensus_.resumes;
  const bool pcIsCode = core_.currentImageIdentity(thread.regs.pc).has_value();
  const std::uint32_t savedRa = thread.regs.r[31];
  const bool raIsCode = core_.currentImageIdentity(savedRa).has_value();
  (pcIsCode ? switchCensus_.pcInCodeImage : switchCensus_.pcNotInCodeImage) += 1u;
  if (savedRa == 0u) {
    ++switchCensus_.raZero;
  } else {
    (raIsCode ? switchCensus_.raInCodeImage : switchCensus_.raNotInCodeImage) += 1u;
  }
  // Stack grows down from the OpenTh top; a sp above it is foreign and corrupts the next push.
  const std::uint32_t savedSp = thread.regs.r[29];
  const bool spAboveStack = thread.stackTop != 0u && savedSp > thread.stackTop;
  if (savedSp == 0u) {
    ++switchCensus_.spZero;
  } else if (spAboveStack) {
    ++switchCensus_.spAboveDeclaredStack;
  }
  if (spAboveStack) {
    lucent::error("x4-thread",
                  "resuming task slot {} (entry 0x{:08X}) with sp 0x{:08X}, which is ABOVE the "
                  "0x{:08X} stack top the guest handed OpenTh - {:+d} byte(s) outside the stack this "
                  "task was given, while its pc 0x{:08X} ({}) and r[31] 0x{:08X} ({}) both classify "
                  "as valid. A task whose stack pointer is outside its own stack pushes frames over "
                  "something else's. Denominator so far: {} resume(s), {} with sp above the declared "
                  "stack, {} with sp zero",
                  target,
                  thread.entry,
                  savedSp,
                  thread.stackTop,
                  static_cast<std::int64_t>(savedSp) - static_cast<std::int64_t>(thread.stackTop),
                  thread.regs.pc,
                  pcIsCode ? "in a code image" : "NOT in a code image",
                  savedRa,
                  savedRa == 0u ? "zero" : (raIsCode ? "in a code image" : "NOT in a code image"),
                  switchCensus_.resumes,
                  switchCensus_.spAboveDeclaredStack,
                  switchCensus_.spZero);
  }
  if (!pcIsCode) {
    lucent::error("x4-thread",
                  "resuming task slot {} (entry 0x{:08X}) with pc 0x{:08X}, which is NOT in any code "
                  "image, and r[31] 0x{:08X} ({}). `Service::open` writes r[29], r[28] and pc and "
                  "never initialises r[31], so this is a saved register file the guest did not "
                  "establish. Denominator so far: {} resume(s), {} with a pc outside every code "
                  "image",
                  target,
                  thread.entry,
                  thread.regs.pc,
                  savedRa,
                  savedRa == 0u ? "zero" : (raIsCode ? "in a code image" : "NOT in a code image"),
                  switchCensus_.resumes,
                  switchCensus_.pcNotInCodeImage);
  } else if (switchCensus_.resumes % kSwitchCensusReportStride == 0u) {
    reportSwitchCensus();
  }
  static_cast<R3000 &>(core_) = thread.regs;
  activeSlot_ = target;
  if (!thread.fiber) {
    startFiber(target);
  }
  lucent::debug("x4-thread",
                "ChangeTh main -> 0x{:08X} entry=0x{:08X} sp=0x{:08X} pc=0x{:08X} r31=0x{:08X}",
                handle,
                thread.entry,
                core_.r[29],
                core_.pc,
                core_.r[31]);
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
