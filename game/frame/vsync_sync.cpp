// Display-field service and libetc VSync entry owner.
// A field wait parks the task fiber via `yieldToMain()`, because `x4::guest::call` aborts on a FrameBoundary exit.
#include "vsync_sync.h"

#include "bios_threads.h"
#include "core.h"
#include "execution_control.h"
#include "game.h"
#include "guest_execution.h"
#include "native_dispatch.h"

#include "image_identity.h"
#include "input_path.h"
#include "snapshot.h"
#include <cstdlib>
#include <lucent/log.h>

namespace x4::vsync {
namespace {

constexpr uint32_t kVblankHandler = 0x800E56FCu;

// libsnd SsStart replaces the class-0 slot with 0x800DD7FC, which chains to the previous handler, so
// deliver the current occupant.
constexpr uint32_t kSetInterruptTable = 0x8011CB98u;
constexpr uint32_t kIrqClassVblank = 0u;

// GPUSTAT bit 6 arms a retail spin at 0x800E4EA0; the host reader never sets it, so it is only counted.
constexpr uint32_t kGpuStatRetraceGate = 0x40u;

// Times the gate above was seen set.
uint32_t g_retraceGateHits = 0u;

[[noreturn]] void refuse(const char *reason, uint32_t returnAddress, std::int32_t mode) {
  lucent::error("x4-vsync",
                "libetc VSync 0x{:08X} was reached from 0x{:08X} with mode {}, which this owner "
                "cannot serve: {}. The measured contract is in game/frame/vsync_sync.h and every "
                "address in it comes from SLUS_005.61.",
                kVSync,
                returnAddress,
                mode,
                reason);
  std::abort();
}

} // namespace

// Scan every IRQ class slot on a stride, not only the delivered one, and report non-code handler words.
constexpr uint32_t kIrqClassCount = 16u;
constexpr uint32_t kIrqCensusStride = 64u;

void censusIrqTable(Core *c, uint32_t field) {
  if ((field % kIrqCensusStride) != 0u) {
    return;
  }
  uint32_t populated = 0;
  uint32_t outside = 0;
  for (uint32_t cls = 0; cls < kIrqClassCount; ++cls) {
    const uint32_t handler = c->mem_r32(kSetInterruptTable + 4u * cls);
    if (handler == 0) {
      continue;
    }
    ++populated;
    const bool executable = c->currentImageIdentity(handler).has_value();
    if (!executable) {
      ++outside;
      // A non-code handler word never becomes code, so report it at once with its class.
      lucent::error("x4-vsync",
                    "IRQ class {} handler at [0x{:08X}] is 0x{:08X}, which is in NO loaded code "
                    "image (the image is 0x80010000..0x8012F800). Delivering this class would fault. "
                    "field {}",
                    cls,
                    kSetInterruptTable + 4u * cls,
                    handler,
                    field);
    } else {
      lucent::debug("x4-vsync",
                    "IRQ class {} handler 0x{:08X} is executable; {} of {} classes populated, {} "
                    "outside a code image",
                    cls,
                    handler,
                    populated,
                    kIrqClassCount,
                    outside);
    }
  }
  lucent::info("x4-vsync",
               "IRQ table census at field {}: scanned {} of {} classes, {} populated, {} outside "
               "every code image (stride {})",
               field,
               kIrqClassCount,
               kIrqClassCount,
               populated,
               outside,
               kIrqCensusStride);
}

void deliverField(Core &core) {
  Core *const c = &core;
  const uint32_t before = c->mem_r32(kVblankCounter);

  // Deliver the class-0 slot's current occupant, then restore the interrupted register file.
  const uint32_t vblankHandler = c->mem_r32(kSetInterruptTable + 4 * kIrqClassVblank);
  if (vblankHandler == 0) {
    lucent::error("x4-vsync",
                  "no class-0 handler registered at [0x{:08X}]; refusing a field with no "
                  "interrupt to deliver it (kVblankHandler 0x{:08X} was the boot registrant)",
                  kSetInterruptTable,
                  kVblankHandler);
    std::abort();
  }
  censusIrqTable(c, before);

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

  // One delivered field is one NTSC VBlank: libpad fills the InitPAD buffers (0x80166D68 / 0x8012F46C)
  // and the SPU mixes one field of samples. The input-path observer only reads.
  input_path::observeField(*c, "pre-service");
  c->game->pad.serviceFrame();
  input_path::observeField(*c, "post-service");
  c->game->spu_audio.frame();

  // The neutral presenter owns capture and pacing; pass the one-field-per-step cadence explicitly.
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
  // The park hands the field to the frame driver; `serveVSync` overwrites the zero after its last park.
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
  // r[31] is the continuation for both `jal` and tail-call `j` entries (epilogue `jr ra` at 0x800E4EE0).
  const std::uint32_t returnAddress = c.r[31];

  // Entry sample (0x800E4DD0..0x800E4DEC): 16-bit delta of RCNT1 against the previous sample.
  const std::uint32_t gpuStat = c.mem_r32(c.mem_r32(kRegisterCell0));
  const std::uint32_t elapsed = (c.mem_r32(c.mem_r32(kRegisterCell1)) - c.mem_r32(kLastSample)) & 0xFFFFu;

  if (mode < 0) {
    // mode < 0 (0x800E4DE8) skips both waits and returns the counter; the display-mode init 0x800E68F4 calls VSync(-1).
    c.r[2] = c.mem_r32(kVblankCounter);
    lucent::debug("x4-vsync", "VSync({}) query -> field {} (ra=0x{:08X})", mode, c.r[2], returnAddress);
    return;
  }

  const bool retraceGateArmed = (gpuStat & kGpuStatRetraceGate) != 0u;
  if (retraceGateArmed) {
    ++g_retraceGateHits;
  }

  if (mode != 1) {
    // The last field is a typed FrameBoundary exit, not a park; earlier fields park and resume at r[31].
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
    // Post-wait bookkeeping in retail order: last-sync (0x800E4ECC), then the RCNT1 sample (0x800E4EDC).
    c.mem_w32(kLastSync, c.mem_r32(kVblankCounter));
    c.mem_w32(kLastSample, c.mem_r32(c.mem_r32(kRegisterCell1)));
  }
  // mode == 1 returns at 0x800E4E04 before the waits and stores, so the result is the entry sample.
  c.r[2] = elapsed;
  lucent::debug("x4-vsync",
                "VSync({}) -> {} field(s), result {}, ra=0x{:08X}, GPUSTAT=0x{:08X} retrace gate {} ({} of {} "
                "call(s) have armed it; the host GPUSTAT cannot set bit 6, so the retail spin at "
                "0x800E4EA0 is not entered)",
                mode,
                fieldsForMode(mode),
                elapsed,
                returnAddress,
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
  psx::cpu::installNativeOverride(core, kVSync, "vsync::serveVSync", serveVSync);
}

} // namespace x4::vsync
