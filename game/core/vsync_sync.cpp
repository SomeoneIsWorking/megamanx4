// vsync_sync.cpp — Mega Man X4's display-field service and the libetc VSync entry owner.
//
// The retail contract comes entirely from SLUS_005.61, not from the matching decomp's labels:
//
//   * VSync 0x800E4DB0 calls the counter-wait helper 0x800E4EF8 twice and otherwise keeps its own
//     return-value, GPU-status and last-sync bookkeeping.
//   * the helper spins only on the VBlank counter 0x8011DC50 reaching a0; its a1 argument is a SPIN
//     BUDGET (0x800E4EFC shifts it left 15, 0x800E4F38 aborts at -1), never a second field count.
//   * init 0x800E56A4 zeroes that counter, clears eight words at 0x8011DC30, and registers
//     0x800E56FC as IRQ-0's handler.
//   * handler 0x800E56FC increments the counter once, then calls each non-null entry in that exact
//     eight-slot table.
//
// The native frame driver owns the host field boundary. It advances the current handler once at that
// boundary, then services host peripherals and presentation. Guest code owns neither host waits nor
// presentation cadence — and, measured here, the host also owns what a guest VSync WAIT is: a guest
// call that asked the framework for a `FrameBoundary` typed exit would be aborted by
// `x4::guest::call`, which resumes only budget exhaustion (game/core/guest_execution.cpp:101,137),
// and would additionally leave `X4FrameDriver::stepFrame` having committed no field, which the
// framework's frame contract refuses outright. So a field wait is expressed the way this title's
// other two owners already express it: park the running retail task fiber across host fields with
// `bios_threads::Service::yieldToMain()`.
#include "vsync_sync.h"

#include "bios_threads.h"
#include "core.h"
#include "execution_control.h"
#include "game.h"
#include "guest_execution.h"
#include "input_path.h"
#include "snapshot.h"
#include <cstdlib>
#include <lucent/log.h>

namespace x4::vsync {
namespace {

constexpr uint32_t kVblankHandler = 0x800E56FCu;

// Retail SetInterrupt table (FUN_800E53F0 measured: it stores its callback at 0x8011CB98 +
// 4*class and toggles the class's I_MASK enable bit). IRQ class 0 is VBlank. The boot-time
// registrant is the IRQ-0 handler 0x800E56FC (whose own body walks the eight-slot callback chain
// at 0x8011DC30), but it is NOT a constant: libsnd's SsStart reads the current class-0 handler
// (FUN_800E4FC4(0,0) returns it) and REPLACES the slot with its own 0x800DD7FC, which calls the
// saved previous handler first and THEN runs the SS sequencer tick (SsSetTickMode downgraded to
// SS_TICKVSYNC = 5 at runtime; tick-rate global 0x80173C88 = 0x3C). Delivering the slot's CURRENT
// occupant is therefore what makes the whole chain advance — counter, registered VBlank callbacks
// and music sequencer together — while hardcoding the boot handler silently drops everything that
// chained after it (measured: 26.4M rendered stereo frames at peak 0 because the tick never ran).
constexpr uint32_t kSetInterruptTable = 0x8011CB98u;
constexpr uint32_t kIrqClassVblank = 0u;

// The retail GPUSTAT gate at 0x800E4E70 (`and v0,s0,v0` with 0x0040 built at 0x800E4E6C). It arms
// a spin on GPUSTAT's sign bit (0x800E4EA0..0x800E4EB4), which is the fence for work the GPU was
// still holding when VSync was entered.
//
// IT IS NEVER ARMED ON THIS PORT, and that is measured rather than assumed: the host GPUSTAT reader
// returns `0x1C000000 | toggle` (psxport/runtime/psx/mem.cpp, io_read), so bits 26/27/28/31 are the
// only ones it can ever set and bit 6 is always clear. The arm is therefore counted and reported if
// it is ever set, rather than being silently assumed away — and it is not spun on, because the
// register it would poll cannot make that transition on demand here and the host consumes GP0/DMA
// work synchronously (which is the same fact GameConfig's `.drawSync` binding already encodes).
constexpr uint32_t kGpuStatRetraceGate = 0x40u;

// Run-lifetime tally of the one condition above, so a claim that the retail fence is unreachable
// carries its own denominator instead of asserting it.
uint32_t g_retraceGateHits = 0u;

[[noreturn]] void refuse(const char *reason, uint32_t returnAddress, std::int32_t mode) {
  lucent::error("x4-vsync",
                "libetc VSync 0x{:08X} was reached from 0x{:08X} with mode {}, which this owner "
                "cannot serve: {}. The measured contract is in game/core/vsync_sync.h and every "
                "address in it comes from SLUS_005.61.",
                kVSync,
                returnAddress,
                mode,
                reason);
  std::abort();
}

} // namespace

void deliverField(Core &core) {
  Core *const c = &core;
  const uint32_t before = c->mem_r32(kVblankCounter);

  // IRQ delivery preserves the interrupted CPU context. Deliver the class-0 slot's CURRENT
  // occupant — see the table comment for why it must be read and not hardcoded — then restore the
  // interrupted frame-loop register file.
  const uint32_t vblankHandler = c->mem_r32(kSetInterruptTable + 4 * kIrqClassVblank);
  if (vblankHandler == 0) {
    lucent::error("x4-vsync",
                  "no class-0 handler registered at [0x{:08X}]; refusing a field with no "
                  "interrupt to deliver it (kVblankHandler 0x{:08X} was the boot registrant)",
                  kSetInterruptTable,
                  kVblankHandler);
    std::abort();
  }
  const R3000 saved = *static_cast<R3000 *>(c);
  guest::callWithoutKnownReturn(c, vblankHandler);
  *static_cast<R3000 *>(c) = saved;

  const uint32_t after = c->mem_r32(kVblankCounter);
  if (after == before) {
    lucent::error("x4-vsync",
                  "IRQ-0 handler 0x{:08X} failed to advance [0x{:08X}] ({} -> {}); refusing a "
                  "wait that can never complete",
                  vblankHandler,
                  kVblankCounter,
                  before,
                  after);
    std::abort();
  }

  // One delivered field = one NTSC VBlank at the retail cadence RE-11 measured, and on hardware a
  // VBlank drives the per-field peripheral work alongside the IRQ-0 callbacks: libpad's SIO read
  // fills the InitPAD packet buffers (RE-06 measured them: 0x80166D68 / 0x8012F46C, capacity 0x22),
  // and the SPU mixes exactly one field of samples in real time. The native X4FrameDriver owns this
  // seam and calls it once before the preserved retail frame body.
  // The input-path observer brackets the pad service, so every stage of an input edge is sampled
  // at the resolution the edge happens at. It reads and never writes: see game/core/input_path.h.
  input_path::observeField(*c, "pre-service");
  c->game->pad.serviceFrame();
  input_path::observeField(*c, "post-service");
  c->game->spu_audio.frame();

  // The neutral presenter owns capture, present, pacing and ledger rotation without constructing
  // interpolation history. The measured loop advances one display field per native step, so pass
  // that cadence explicitly.
  snapshot_tick(c);
  c->game->presentation.commit(c, 1);
  lucent::debug("x4-vsync", "native field {} -> {}", before, after);
}

void yieldField(Core &core, std::uint32_t returnAddress, bios_threads::Service &threads) {
  if (core.r[31] != returnAddress) {
    lucent::error("x4-vsync",
                  "a field wait was asked for from 0x{:08X} while the guest's own return address is "
                  "0x{:08X}; a `jal`ed leaf resumes at r[31], so one of the two is wrong",
                  returnAddress,
                  core.r[31]);
    std::abort();
  }
  // The park hands the field back to the host frame driver, which advances one field and only then
  // re-enters this retail task through the guest scheduler. VSync(0)'s zero result is written here
  // because a caller that only wanted the fence leaves it unconsumed; `serveVSync` overwrites it
  // with the retail elapsed sample after its last park.
  threads.yieldToMain();
  core.r[2] = 0u;
}

void serveVSync(Core *core) {
  if (!core) {
    lucent::error("x4-vsync", "libetc VSync 0x{:08X} owner received a null Core", kVSync);
    std::abort();
  }
  Core &c = *core;
  const std::int32_t mode = static_cast<std::int32_t>(c.r[4]);
  // r[31] is where the guest continues after this entry for BOTH call forms the image uses: the
  // `jal` sites set it themselves, and the `j` (tail-call) sites do not — but libetc VSync's own
  // epilogue is `lw ra / ... / jr ra` (0x800E4EE0..0x800E4EEF4), so a tail caller expects to return
  // to ITS caller, which is exactly r[31].
  const std::uint32_t returnAddress = c.r[31];

  // The retail return value, sampled at ENTRY (0x800E4DD0..0x800E4DEC): the 16-bit difference
  // between the HBlank-clocked root counter the image names and VSync's own previous sample of it.
  // The two register addresses are read out of the guest's own cells rather than hardcoded, because
  // nothing in the resident text ever stores them (tools/verify_vsync.py pins that).
  const std::uint32_t gpuStat = c.mem_r32(c.mem_r32(kRegisterCell0));
  const std::uint32_t elapsed = (c.mem_r32(c.mem_r32(kRegisterCell1)) - c.mem_r32(kLastSample)) & 0xFFFFu;

  if (mode < 0) {
    // 0x800E4DE8 bgez skips both waits; 0x800E4DF0 returns the VBlank counter verbatim. No state
    // change, no field. This is the arm the completed boot's first non-movie caller needs: the
    // display-mode init at 0x800E68C8 tail-calls VSync(-1) at 0x800E68F4 right after the guest's
    // own GP1(08) 15-bit 320x240 switch.
    c.r[2] = c.mem_r32(kVblankCounter);
    lucent::debug("x4-vsync", "VSync({}) query -> field {} (ra=0x{:08X})", mode, c.r[2], returnAddress);
    return;
  }

  const bool retraceGateArmed = (gpuStat & kGpuStatRetraceGate) != 0u;
  if (retraceGateArmed) {
    ++g_retraceGateHits;
  }

  if (mode != 1) {
    // Both counter waits, as host fields. The LAST field is a typed `FrameBoundary` exit rather than
    // a park, and that is not a choice — it is what makes the turn END here.
    //
    // MEASURED on the working movie run (scratch/strloop/probe_str_loop.log): the retail movie task
    // 0x8001D064 reported "1 of 8 task turn(s) have needed a budget resume ... the other 7 reached a
    // guest field boundary", i.e. its per-field pull's VSync(0) at 0x80018BBC ended almost every
    // turn. A park-only wait does not: the fiber suspends and resumes INSIDE this function, so the
    // executor segment that entered it keeps running and the turn is only ever a budget exhaustion.
    // `bios_threads::run_guest_entry` counts consecutive budget exhaustions and aborts at 8
    // ("guest task spent 8 display field(s) of guest CPU without reaching a field boundary"),
    // because a task that never ends a turn is indistinguishable from a guest loop. Measured: that
    // is exactly what a park-only owner produces, at display field 8.
    //
    // So `fields - 1` parks pay the earlier fields and the exit pays the last one, resuming at r[31]
    // — the address 9bd4e9a8 made correct. One field for VSync(0), two for VSync(2), three for
    // VSync(3), which is what `fieldsForMode` says the retail body asks for.
    const std::uint32_t fields = fieldsForMode(mode);
    bios_threads::Service &threads = bios_threads::from(c);
    if (!threads.inTaskFiber()) {
      refuse("a positive VSync mode is a field wait, and this port expresses a field wait as a "
             "typed FrameBoundary exit that only a retail task's own turn loop can consume. The "
             "caller is not inside one, so there is nothing to consume it: the main thread's field "
             "cadence is X4FrameDriver's, and the retail main loop's own VSync(0) at 0x80012048 is "
             "replaced by that driver rather than executed",
             returnAddress,
             mode);
    }
    for (std::uint32_t field = 1u; field < fields; ++field) {
      yieldField(c, returnAddress, threads);
    }
    // The retail post-wait bookkeeping, in the retail order: last-sync first (0x800E4ECC), then the
    // previous RCNT1 sample (0x800E4EDC). Both are sampled one field before the exit above, and the
    // only thing that reads either of them is THIS function's own next call, so the guest-visible
    // consequence is confined to the elapsed sample below — and no one of the 42 call sites in
    // SLUS_005.61 reads this leaf's result (tools/verify_vsync.py census).
    c.mem_w32(kLastSync, c.mem_r32(kVblankCounter));
    c.mem_w32(kLastSample, c.mem_r32(c.mem_r32(kRegisterCell1)));
  }
  // mode == 1 returns at 0x800E4E04 straight to the epilogue, skipping both waits AND the two
  // stores, so its result is the entry sample alone.
  c.r[2] = elapsed;
  lucent::debug("x4-vsync",
                "VSync({}) -> {} field(s), result {}, GPUSTAT=0x{:08X} retrace gate {} ({} of {} "
                "call(s) have armed it; the host GPUSTAT cannot set bit 6, so the retail spin at "
                "0x800E4EA0 is not entered)",
                mode,
                fieldsForMode(mode),
                elapsed,
                gpuStat,
                retraceGateArmed ? "ARMED" : "clear",
                g_retraceGateHits,
                g_retraceGateHits);
  if (mode != 1) {
    psx::cpu::requestExecutionExit(
        c,
        {psx::cpu::ExecutionExitReason::FrameBoundary, returnAddress, 0u, "Mega Man X4 libetc VSync field boundary"});
  }
}

void registerOverrides(Core &core) {
  guest::install(core, kVSync, "vsync::serveVSync", serveVSync);
}

} // namespace x4::vsync
