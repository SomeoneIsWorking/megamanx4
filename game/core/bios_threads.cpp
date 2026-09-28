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
//
// This cap is a REPORTING BOUND, stated policy, and it is not a fix for anything. Its only job is to
// turn "this task has not ended a turn in a very long time" into one line naming where, instead of a
// silent spin. Two measurements set it, and they pull in opposite directions:
//
//   * the movie path, which is the one that works, needed 2: retail `DecDCTvlc` (0x800ED574) measures
//     610,746 cycles = 1.082 fields, and the movie's own task ended a turn on a field boundary in
//     11,860 of its 13,128 turns. So the bound is nowhere near a field wait.
//   * the POST-MOVIE path needs more than 8. At 8 the bound fired at display field ~13,121 and hid
//     the whole post-movie phase; at 512 the same task runs to display field 47,762 before the line
//     prints, which is the measured end of every run at this bound.
//
// 512 is therefore "long enough that reporting it means something happened", not "long enough".
//
// WHAT THE POST-MOVIE TURN IS DOING, measured 2026-09-27, because the previous version of this
// comment asserted a mechanism the image does not contain, now retired (see docs/issues/0028). The
// task is NOT parked in a wait: it burns exactly one host turn of guest CPU per turn and its
// budget-exhaustion PC keeps moving, which is the signature of work rather than of a wait.
// Histogrammed over a 16,000-present run (tools/probe_post_movie_motion.py and scratch/motion/), the
// resume PC is:
//     turns 1..1,200       inside `DecDCTvlc` 0x800ED574..0x800ED8D8 — the stage's MDEC decode
//     turns 1,200..1,765   the object-update set 0x800216EC / 0x80021858 / 0x80023F7C..0x80027704
// and 0x80021858 is `update_misc_objects` in the matching decomp's config/symbols.us.txt. Its walk
// cursor is SCRATCHPAD 0x1F800064 — `lui $1,0x1f80` builds 0x1F800000, so the `sw`/`lw 0x64($1)` pair
// is scratchpad+0x64, NOT a peripheral at 0x1F801064 — and it walks `misc_objects` 0x80173CA0, which
// is the decomp's own `misc_objects = 0x80173CA0; // size:0x1800`: 96 records of 0x60 bytes, each
// dispatched through the handler table at 0x800F2980. No DMA is involved.
// The byte it tests, 0x801721D7, is `engine_obj_17`: offset 0x17 of the engine-object struct the
// decomp names `engine_obj = 0x801721C0; // size:0x64`. It has FOUR store sites in the whole text
// image (0x800311B8, 0x80035B20, 0x80035BCC, 0x800C03F8), one load site (0x80021898), and no code in
// this product writes it. The host neither owns that byte nor is missing it.
//
// So the defect this line REPORTS is NOT an undelivered DMA completion. It is that the post-movie
// guest stops ending its turns at a field boundary at all — turn 11,860 is the last that does — while
// the game's own state machine sits at game state 1 / sub-state 2 (0x80173C70 = 0x00000201) waiting
// for a CD read transaction to finish. See docs/issues/0028.
constexpr uint32_t kMaxTurnFields = 512u;
// The measured libetc VBlank counter, so a report of "how far did it get" is a guest address and a
// field number rather than a PC alone. game/core/vsync_sync.h owns the boundary this word counts.
constexpr uint32_t kVblankCounter = 0x8011DC50u;

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

// WHAT A FIBER IS RESUMED WITH, and why this census exists.
//
// `Service::change` loads a task's SAVED register file straight into the Core:
//
//     mainRegs_ = static_cast<R3000 &>(core_);
//     static_cast<R3000 &>(core_) = thread.regs;
//
// and `Service::open` builds that saved file as `Thread{}` (zero-initialised) with only `r[29]`
// (sp), `r[28]` (gp) and `pc` (entry) written. **`r[31]` is never initialised.** So every value a
// task is resumed with is either something the guest itself wrote before yielding, or zero - and the
// product run on 2026-09-29 faults at 0x0113D7D0, 0 cycles into a dispatch of the retail task
// scheduler 0x80012600, which is this path.
//
// The two registers that decide whether that resume is sound are `pc` (where the task will execute)
// and `r[31]` (where a `jr $ra` with no frame of its own will go). Both are classified here against
// `Core::currentImageIdentity` - the framework's own rule, and the criterion the fault message quotes
// ("resolves to zero or multiple active code images") - so a resume that is already wrong is caught
// at the switch, with the slot and the entry named, rather than 13,000 fields later as a bare fault
// address.
struct SwitchCensus {
  std::uint64_t resumes = 0;
  std::uint64_t pcInCodeImage = 0;
  std::uint64_t pcNotInCodeImage = 0;
  std::uint64_t raZero = 0;
  std::uint64_t raInCodeImage = 0;
  std::uint64_t raNotInCodeImage = 0;
};

SwitchCensus switchCensus;

// HOW OFTEN THE SOUND CASE IS REPORTED. The interesting case (a resume whose pc is outside every
// code image) reports IMMEDIATELY and always. The sound case is reported on a fixed stride, because
// a run that switches tasks 1,000 times must not print 1,000 identical lines - and because a
// census that only prints when it is worried is indistinguishable from a census that is not
// running. The stride is what turns "nothing printed" into "scanned N, matched 0".
constexpr std::uint64_t kSwitchCensusReportStride = 1000u;

void reportSwitchCensus() {
  lucent::info("x4-thread",
               "fiber-switch census: {} task resume(s) scanned; {} resumed with a pc inside a code "
               "image, {} with one outside EVERY code image; of their link registers, {} were zero "
               "(`Service::open` never initialises r[31]), {} were in a code image and {} were not",
               switchCensus.resumes,
               switchCensus.pcInCodeImage,
               switchCensus.pcNotInCodeImage,
               switchCensus.raZero,
               switchCensus.raInCodeImage,
               switchCensus.raNotInCodeImage);
}

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
                   "resume(s), {} guest cycles over those budget resumes). It is no longer scheduled. "
                   "Fiber-switch census: {} task resume(s), {} resumed with a pc inside a code image "
                   "and {} with one outside every code image; of their link registers, {} were zero, "
                   "{} were in a code image and {} were not",
                   entry,
                   result.guestPc,
                   census.turns,
                   census.fieldResumes,
                   census.budgetResumes,
                   census.budgetCycles,
                   switchCensus.resumes,
                   switchCensus.pcInCodeImage,
                   switchCensus.pcNotInCodeImage,
                   switchCensus.raZero,
                   switchCensus.raInCodeImage,
                   switchCensus.raNotInCodeImage);
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
                      "boundary and is still at 0x{:08X} at display field {} (the measured libetc "
                      "VBlank counter at 0x{:08X}). Retail delivers a field every field, so this is a "
                      "guest loop: reported rather than spun on",
                      budgetTurns,
                      result.guestPc,
                      core.mem_r32(kVblankCounter),
                      kVblankCounter);
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
      // WHY THE REGISTER FILE IS IN THIS REPORT. `result.guestPc` is where the executor stopped, and
      // for a bad indirect branch that is the BRANCH TARGET, not the instruction that branched — so the
      // existing one line named a data value and said nothing about which instruction produced it or
      // what the guest's own `r[31]` was. Two things follow from that and neither is a guess: `r[31]`
      // is the caller's own return address, so it names the `jalr`/`j` site the guest came from, and a
      // register holding the stop address names the pointer that was followed. The whole file is
      // printed because a partial file cannot distinguish "the pointer was in a callee-saved
      // register" from "the pointer was in a caller-saved one and the callee is the caller".
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
      // The guest reached this stop through an indirect call, so the only state that can say WHY is
      // the record it was called with. `$a0` is printed as the guest's own argument, in BYTES as well
      // as words: the byte lanes are what a sub-type/index field is, and a word-only print hides a
      // single wrong byte inside an otherwise plausible record — which is the whole shape of an
      // out-of-range table index.
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
  // CENSUS BEFORE THE LOAD, so it reports what the task is about to be resumed WITH rather than what
  // it left behind afterwards.
  ++switchCensus.resumes;
  const bool pcIsCode = core_.currentImageIdentity(thread.regs.pc).has_value();
  const std::uint32_t savedRa = thread.regs.r[31];
  const bool raIsCode = core_.currentImageIdentity(savedRa).has_value();
  (pcIsCode ? switchCensus.pcInCodeImage : switchCensus.pcNotInCodeImage) += 1u;
  if (savedRa == 0u) {
    ++switchCensus.raZero;
  } else {
    (raIsCode ? switchCensus.raInCodeImage : switchCensus.raNotInCodeImage) += 1u;
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
                  switchCensus.resumes,
                  switchCensus.pcNotInCodeImage);
  } else if (switchCensus.resumes % kSwitchCensusReportStride == 0u) {
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
