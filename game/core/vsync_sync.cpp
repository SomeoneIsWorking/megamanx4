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
#include <cstdlib>
#include <lucent/log.h>

namespace x4::vsync {
namespace {

constexpr uint32_t kVblankCounter = 0x8011DC50u;
constexpr uint32_t kVblankHandler = 0x800E56FCu;

void deliver_field(Core *c) {
  const uint32_t before = c->mem_r32(kVblankCounter);

  // IRQ delivery preserves the interrupted CPU context. Run the retail handler itself, rather than
  // reimplementing its callback walk, then restore the wait helper's live register file.
  const R3000 saved = *static_cast<R3000 *>(c);
  rec_dispatch(c, kVblankHandler);
  *static_cast<R3000 *>(c) = saved;

  const uint32_t after = c->mem_r32(kVblankCounter);
  if (after == before) {
    lucent::error("x4-vsync",
                  "IRQ-0 handler 0x{:08X} failed to advance [0x{:08X}] ({} -> {}); refusing a "
                  "wait that can never complete",
                  kVblankHandler,
                  kVblankCounter,
                  before,
                  after);
    std::abort();
  }

  // The guest owns drawing, so this wait is its frame boundary. A raw gpu_present() would show the
  // picture but would not rotate Fps60's captured queues: successive DrawOTag submissions would then
  // accumulate across fields until the 65,536-item fail-fast. frame_commit is the framework's single
  // authoritative present + capture-rotation + pacing fence. This game's measured loop advances one
  // display field per blocking VSync, so pass that cadence explicitly.
  c->game->fps60.frame_commit(c, 1);
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
