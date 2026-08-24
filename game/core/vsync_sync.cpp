// vsync_sync.cpp — restore the retail VBlank producer at libetc's measured wait boundary.
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
// A static recomp has no asynchronous IRQ-0 producer, so the unmodified helper can never observe its
// condition changing. Own ONLY the helper: run the retail handler, commit/present and pace the
// guest-owned field, then let the original VSync body re-check and finish its own logic.
// This is not vsyncTrap (the guest owns its loop), and it does not invent a host tick or reproduce
// VSync in C++. tools/verify_vsync.py re-derives every address and edge above from the retail bytes.
#include "vsync_sync.h"

#include "core.h"
#include "game.h"
#include "platform_hle.h"
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

void deliver_field(Core *c) {
  const uint32_t before = c->mem_r32(kVblankCounter);

  // IRQ delivery preserves the interrupted CPU context. Deliver the class-0 slot's CURRENT
  // occupant — see the table comment for why it must be read and not hardcoded — then restore the
  // wait helper's live register file.
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
  // and the SPU mixes exactly one field of samples in real time. The guest owns its loop here —
  // there is no PC-driven frame body to host these services the way Tomba!2's frame hook does — so
  // they run at this seam, after the retail handler and before the commit below. SBS feeds both
  // cores' masks itself and shares the one output device, so its audio advances logic-only.
  c->game->pad.serviceFrame();
  if (c->game->diff_mode) {
    c->game->spu_audio.frameLogic();
  } else {
    c->game->spu_audio.frame();
  }

  // The guest owns drawing, so this wait is its frame boundary. The neutral presenter owns capture,
  // present, pacing and ledger rotation without constructing interpolation history. This game's
  // measured loop advances one display field per blocking VSync, so pass that cadence explicitly.
  snapshot_tick(c);
  c->game->presentation.commit(c, 1);
  lucent::debug("x4-vsync", "field {} -> {}, target={}", before, after, c->r[4]);
}

void wait_for_counter(Core *c) {
  const uint32_t target = c->r[4];
  c->r[5] <<= 15; // retail helper's first instruction; a1 is caller-saved but still observable
  bool waited = false;
  while ((int32_t)c->mem_r32(kVblankCounter) < (int32_t)target) {
    waited = true;
    deliver_field(c);
  }
  if (waited) {
    c->r[3] = UINT32_MAX; // retail loop sentinel
  }
  c->r[2] = 0; // the final signed comparison is false when the target has been reached
}

} // namespace

void install(Game *game) {
  game->platform_hle.register_(kWait, wait_for_counter);
  lucent::info("x4-vsync",
               "retail VBlank wait installed at 0x{:08X}; IRQ-0 handler 0x{:08X} owns counter "
               "0x{:08X}",
               kWait,
               kVblankHandler,
               kVblankCounter);
}

} // namespace x4::vsync
