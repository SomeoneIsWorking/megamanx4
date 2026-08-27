// vsync_sync.cpp — service one retail display field from the native-owned frame boundary.
//
// The retail contract comes entirely from SLUS_005.61, not the matching decomp's labels:
//
//   * VSync 0x800E4DB0 calls wait helper 0x800E4EF8 twice and otherwise keeps its own return-value,
//     hblank-delta, GPU-status and last-sync bookkeeping.
//   * the helper spins only on counter 0x8011DC50 reaching a0;
//   * init 0x800E56A4 zeroes that counter, clears eight words at 0x8011DC30, and registers
//     0x800E56FC as IRQ-0's handler;
//   * handler 0x800E56FC increments the counter once, then calls each non-null entry in that exact
//     eight-slot table.
//
// A static recomp has no asynchronous IRQ-0 producer. The native frame driver therefore advances the
// current handler once at the field boundary, then services host peripherals and presentation. Full
// libetc VSync is separately declared as a fail-fast trap: guest code owns neither waits nor queries.
#include "vsync_sync.h"

#include "core.h"
#include "game.h"
#include "snapshot.h"
#include <cstdlib>
#include <lucent/log.h>

namespace x4::vsync {
namespace {

constexpr uint32_t kVblankCounter = 0x8011DC50u;
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
  rec_dispatch(c, vblankHandler);
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
  // seam and calls it once before the preserved retail frame body. SBS feeds both cores' masks
  // itself and shares the one output device, so its audio advances logic-only.
  c->game->pad.serviceFrame();
  if (c->game->diff_mode) {
    c->game->spu_audio.frameLogic();
  } else {
    c->game->spu_audio.frame();
  }

  // The neutral presenter owns capture, present, pacing and ledger rotation without constructing
  // interpolation history. The measured loop advances one display field per native step, so pass
  // that cadence explicitly.
  snapshot_tick(c);
  c->game->presentation.commit(c, 1);
  lucent::debug("x4-vsync", "native field {} -> {}", before, after);
}

} // namespace x4::vsync
