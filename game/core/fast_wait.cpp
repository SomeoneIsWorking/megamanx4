#include "fast_wait.h"

#include "core.h"
#include "disc.h"
#include "enhancements.h"
#include "execution_services.h"
#include "game.h"
#include "r3000.h"
#include "x4_context.h"

#include <cstdlib>
#include <lucent/log.h>

namespace x4::fast_wait {
namespace {

constexpr uint32_t kRequestTable = 0x800F0E18u;
constexpr uint32_t kRequestStride = 12u;
// The retail body at 0x800E5D78 materializes (32786 << 16) - 8928 before storing the
// CdReady callback. Keep the decoded instruction operands here so a high-word
// transcription error cannot silently redirect the validation.
constexpr uint32_t kReadyCallbackSlot = (32786u << 16u) - 8928u;
static_assert(kReadyCallbackSlot == 0x8011DD20u);
constexpr uint32_t kLoadState = 0x801406ACu;
constexpr uint32_t kArchivePostprocessPending = 0x8013BD40u;
constexpr uint32_t kArchiveProcessedCount = 0x80137CF0u;
constexpr uint32_t kArchiveEnqueuedCount = 0x80137CF4u;
constexpr uint32_t kSectorPayloadBytes = 2048u;
constexpr size_t kRawDataOffset = 12u;
constexpr uint32_t kArchiveRingSlots = 16u;

[[noreturn]] void refuse(const char *what, const char *reason, const State &state) {
  lucent::error("x4-fastwait",
                "{} refused: {} (request={} LBA={} bytes={} sectors={} phase={})",
                what,
                reason,
                state.requestId,
                state.requestLba,
                state.requestBytes,
                state.sectorsDelivered,
                static_cast<unsigned>(state.phase));
  std::abort();
}

State &state(Core &core) {
  return x4::context(core).fastWait;
}

void require_body(GuestBody body, const char *what, State &load) {
  if (!body) {
    refuse(what, "original guest-body dispatcher is absent", load);
  }
}

void restore_registers(Core &core, const R3000 &registers) {
  static_cast<R3000 &>(core) = registers;
}

void dispatch_preserving_registers(Core &core, GuestBody body, const R3000 &registers) {
  body(&core);
  restore_registers(core, registers);
}

void read_request_entry(Core &core, State &load) {
  const uint32_t request = core.r[4];
  if (request > UINT8_MAX) {
    refuse("synchronous request", "request id is not an 8-bit retail table index", load);
  }
  load.requestId = request;
  const uint32_t entry = kRequestTable + request * kRequestStride;
  load.requestLba = core.mem_r32(entry);
  load.requestBytes = core.mem_r32(entry + 4u);
  if (load.requestBytes == 0) {
    refuse("synchronous request", "retail request table reports zero bytes", load);
  }
  if (load.requestBytes > UINT32_MAX - (kSectorPayloadBytes - 1u)) {
    refuse("synchronous request", "retail request byte count overflows sector rounding", load);
  }
}

bool scoped(const State &load) {
  return load.phase != Phase::Inactive;
}

void drain_archive_postprocess(
    Core &core, GuestBody postprocess, const R3000 &issuerRegisters, const char *what, State &load) {
  if (!postprocess) {
    return;
  }

  uint32_t passes = 0;
  while (core.mem_r8(kArchivePostprocessPending) != 0u && passes < kArchiveRingSlots) {
    dispatch_preserving_registers(core, postprocess, issuerRegisters);
    ++passes;
  }
  if (core.mem_r8(kArchivePostprocessPending) != 0u) {
    refuse(what, "archive postprocess ring did not drain within its 16-slot bound", load);
  }
  if (core.mem_r8(kArchiveProcessedCount) != core.mem_r8(kArchiveEnqueuedCount)) {
    refuse(what, "archive postprocess producer and consumer counts diverged", load);
  }
}

} // namespace

void load_synchronously(Core *core,
                        GuestBody retailIssuer,
                        GuestBody readyCallback,
                        GuestBody postprocess,
                        uint32_t expectedCallbackVa,
                        const char *what) {
  if (!core || !core->game) {
    lucent::error("x4-fastwait", "{} requires a bound Core/Game", what);
    std::abort();
  }
  State &load = state(*core);
  require_body(retailIssuer, what, load);
  require_body(readyCallback, what, load);
  if (!enh(cv_fastwait)) {
    retailIssuer(core);
    return;
  }
  if (scoped(load)) {
    refuse(what, "nested synchronous request", load);
  }

  read_request_entry(*core, load);
  load.sectorsDelivered = 0;
  load.phase = Phase::Preparing;
  retailIssuer(core);

  if (core->mem_r32(kReadyCallbackSlot) != expectedCallbackVa) {
    refuse(what, "issuer registered an unexpected ready callback", load);
  }
  if (core->mem_r8(kLoadState) != 1u) {
    refuse(what, "issuer did not enter retail state 1", load);
  }

  const R3000 issuerRegisters = static_cast<R3000 &>(*core);
  const uint32_t sectorCount = (load.requestBytes + kSectorPayloadBytes - 1u) / kSectorPayloadBytes;
  if (load.requestLba > UINT32_MAX - (sectorCount - 1u)) {
    refuse(what, "retail request LBA range overflows", load);
  }
  load.phase = Phase::Delivering;
  for (uint32_t sector = 0; sector < sectorCount; ++sector) {
    if (!disc_read_raw(&core->game->disc, load.requestLba + sector, load.rawSector.data(), load.rawSector.size())) {
      refuse(what, "disc backend could not read a required raw sector", load);
    }
    load.sectorCursor = kRawDataOffset;
    dispatch_preserving_registers(*core, readyCallback, issuerRegisters);
    ++load.sectorsDelivered;
    // Retail calls 0x80014780 once per main-loop pass. The producing handlers reject seven
    // outstanding records, so a synchronous owner must consume after each ready callback rather
    // than deferring the bounded ring until the whole archive has arrived.
    drain_archive_postprocess(*core, postprocess, issuerRegisters, what, load);

    const bool last = sector + 1u == sectorCount;
    const uint8_t guestState = core->mem_r8(kLoadState);
    if (!last && guestState == 2u) {
      refuse(what, "guest callback completed before the table-derived byte length", load);
    }
  }

  if (core->mem_r8(kLoadState) != 2u) {
    refuse(what, "guest callback did not publish terminal state 2 at the table-derived bound", load);
  }

  load.phase = Phase::Inactive;
  ++load.loadsCompleted;
  lucent::info("x4-fastwait",
               "{} completed synchronously: request {} LBA {} bytes {} sectors {}",
               what,
               load.requestId,
               load.requestLba,
               load.requestBytes,
               load.sectorsDelivered);
}

void archive_cd_setup(Core *core,
                      GuestBody retailBody,
                      GuestBody issueLocation,
                      GuestBody queryStatus,
                      GuestBody cdReadyBody,
                      GuestBody cdControlBody) {
  if (!core || !core->game) {
    lucent::error("x4-fastwait", "archive CD setup requires a bound Core/Game");
    std::abort();
  }
  State &load = state(*core);
  require_body(retailBody, "archive CD setup", load);
  if (!enh(cv_fastwait) || !scoped(load)) {
    retailBody(core);
    return;
  }
  require_body(issueLocation, "archive CD setup issue-location", load);
  require_body(queryStatus, "archive CD setup status", load);
  require_body(cdReadyBody, "archive CD setup CdReady", load);
  require_body(cdControlBody, "archive CD setup CdControl", load);

  // Exact finite body of SLUS_005.61 0x80013DA8, except for its VSync(3). The scoped libcd leaves
  // below complete immediately, so advancing three emulated fields here would invent time inside a
  // host-owned synchronous transition.
  core->r[29] -= 32u;
  core->r[5] = 0x80137CF8u;
  core->r[4] = core->mem_r32(0x80137CCCu);
  core->r[2] = 0xA0u;
  core->mem_w32(core->r[29] + 24u, core->r[31]);
  core->mem_w8(core->r[29] + 16u, static_cast<uint8_t>(core->r[2]));
  core->mem_w32(0x80137CECu, 0u);
  core->r[31] = 0x80013DD8u;
  psx::cpu::accountGuestInstructions(*core, 12u);
  issueLocation(core);

  do {
    core->r[31] = 0x80013DE0u;
    psx::cpu::accountGuestInstructions(*core, 2u);
    queryStatus(core);
    core->r[2] &= 64u;
    core->r[4] = 1u;
    psx::cpu::accountGuestInstructions(*core, 3u);
  } while (core->r[2] != 0u);

  do {
    core->r[5] = 0u;
    core->r[31] = 0x80013DF4u;
    psx::cpu::accountGuestInstructions(*core, 2u);
    cdReadyBody(core);
    core->r[4] = 1u;
    psx::cpu::accountGuestInstructions(*core, 2u);
  } while (core->r[2] != 0u);

  core->r[4] = 14u;
  core->r[5] = core->r[29] + 16u;
  core->r[31] = 0x80013E0Cu;
  core->r[6] = 0u;
  psx::cpu::accountGuestInstructions(*core, 4u);
  cdControlBody(core);
  psx::cpu::accountGuestInstructions(*core, 2u);
  if (core->r[2] == 0u) {
    refuse("archive CD setup", "native Setmode did not complete synchronously", load);
  }

  // Retail's VSync(3) was only a fixed settling delay after the asynchronous Setmode command. The
  // native scoped command above has already completed; no game-owned field/query call is made.
  core->r[4] = 2u;
  core->r[5] = 0x80137CF8u;
  core->r[31] = 0x80013E30u;
  core->r[6] = 0u;
  psx::cpu::accountGuestInstructions(*core, 7u);
  cdControlBody(core);
  core->r[4] = 6u;
  psx::cpu::accountGuestInstructions(*core, 2u);
  if (core->r[2] == 0u) {
    refuse("archive CD setup", "native Setloc did not complete synchronously", load);
  }

  do {
    core->r[5] = 0u;
    core->r[31] = 0x80013E44u;
    core->r[6] = 0u;
    psx::cpu::accountGuestInstructions(*core, 3u);
    cdReadyBody(core);
    core->r[4] = 6u;
    psx::cpu::accountGuestInstructions(*core, 2u);
  } while (core->r[2] == 0u);

  core->r[2] = 1u;
  core->mem_w8(kLoadState, static_cast<uint8_t>(core->r[2]));
  core->r[31] = core->mem_r32(core->r[29] + 24u);
  core->r[29] += 32u;
  psx::cpu::accountGuestInstructions(*core, 7u);
}

void direct_cd_setup(Core *core,
                     GuestBody retailBody,
                     GuestBody issueLocation,
                     GuestBody cdReadyBody,
                     GuestBody cdControlBody,
                     GuestBody publishReadyCallback) {
  if (!core || !core->game) {
    lucent::error("x4-fastwait", "direct CD setup requires a bound Core/Game");
    std::abort();
  }
  State &load = state(*core);
  require_body(retailBody, "direct CD setup", load);
  if (!enh(cv_fastwait) || !scoped(load)) {
    retailBody(core);
    return;
  }
  require_body(issueLocation, "direct CD setup issue-location", load);
  require_body(cdReadyBody, "direct CD setup CdReady", load);
  require_body(cdControlBody, "direct CD setup CdControl", load);
  require_body(publishReadyCallback, "direct CD setup callback publication", load);

  // Exact finite body of SLUS_005.61 0x80013968 around the same synchronous Setmode/Setloc
  // transition as the archive path. Its fixed VSync(3) settling delay is deliberately absent.
  core->r[29] -= 32u;
  core->r[5] = 0x80137CF8u;
  core->r[4] = core->mem_r32(0x80137CCCu);
  core->r[2] = 0xA0u;
  core->mem_w32(core->r[29] + 24u, core->r[31]);
  core->mem_w8(core->r[29] + 16u, static_cast<uint8_t>(core->r[2]));
  core->mem_w8(kLoadState, 0u);
  core->mem_w32(0x80137CECu, 0u);
  core->r[31] = 0x800139A0u;
  psx::cpu::accountGuestInstructions(*core, 14u);
  issueLocation(core);
  core->mem_w32(0x80137CCCu, core->mem_r32(0x80137CCCu) - 1u);
  core->r[4] = 1u;
  psx::cpu::accountGuestInstructions(*core, 7u);

  do {
    core->r[5] = 0u;
    core->r[31] = 0x800139C4u;
    psx::cpu::accountGuestInstructions(*core, 2u);
    cdReadyBody(core);
    core->r[4] = 1u;
    psx::cpu::accountGuestInstructions(*core, 2u);
  } while (core->r[2] != 0u);

  core->r[4] = 14u;
  core->r[5] = core->r[29] + 16u;
  core->r[31] = 0x800139DCu;
  core->r[6] = 0u;
  psx::cpu::accountGuestInstructions(*core, 4u);
  cdControlBody(core);
  psx::cpu::accountGuestInstructions(*core, 2u);
  if (core->r[2] == 0u) {
    refuse("direct CD setup", "native Setmode did not complete synchronously", load);
  }

  core->r[4] = 2u;
  core->r[5] = 0x80137CF8u;
  core->r[31] = 0x80013A00u;
  core->r[6] = 0u;
  psx::cpu::accountGuestInstructions(*core, 7u);
  cdControlBody(core);
  psx::cpu::accountGuestInstructions(*core, 2u);
  if (core->r[2] == 0u) {
    refuse("direct CD setup", "native Setloc did not complete synchronously", load);
  }

  core->r[31] = 0x80013A10u;
  psx::cpu::accountGuestInstructions(*core, 2u);
  publishReadyCallback(core);
  core->r[31] = core->mem_r32(core->r[29] + 24u);
  core->r[29] += 32u;
  psx::cpu::accountGuestInstructions(*core, 4u);
}

void cd_ready(Core *core, GuestBody retailBody) {
  State &load = state(*core);
  if (!scoped(load)) {
    retailBody(core);
    return;
  }
  const uint32_t mode = core->r[4];
  if (mode == 1u) {
    core->r[2] = load.phase == Phase::Delivering ? 1u : 0u;
    return;
  }
  if (mode == 6u && load.phase == Phase::Preparing) {
    core->r[2] = 1u;
    return;
  }
  refuse("CdReady", "unexpected synchronous mode", load);
}

void cd_control(Core *core, GuestBody retailBody, bool blocking) {
  State &load = state(*core);
  if (!scoped(load)) {
    retailBody(core);
    return;
  }

  const uint32_t command = core->r[4] & UINT8_MAX;
  if (blocking) {
    if (command != 1u && command != 9u) {
      refuse("CdControlB", "unexpected command in synchronous loader scope", load);
    }
    if (core->r[6] != 0u) {
      core->mem_w8(core->r[6], 0x02u); // standby, and specifically no shell-open bit 0x40
    }
  } else if (command != 0x02u && command != 0x06u && command != 0x09u && command != 0x0Eu) {
    refuse("CdControl", "unexpected command in synchronous loader scope", load);
  }
  core->r[2] = 1u;
}

void cd_get_sector(Core *core, GuestBody retailBody) {
  State &load = state(*core);
  if (!scoped(load)) {
    retailBody(core);
    return;
  }
  if (load.phase != Phase::Delivering) {
    refuse("CdGetSector", "sector requested outside callback delivery", load);
  }

  const uint32_t destination = core->r[4];
  const uint32_t words = core->r[5];
  const size_t bytes = static_cast<size_t>(words) * 4u;
  if (words > load.rawSector.size() / 4u || load.sectorCursor > load.rawSector.size() - bytes) {
    refuse("CdGetSector", "guest callback read beyond the current raw sector", load);
  }
  for (size_t byte = 0; byte < bytes; ++byte) {
    core->mem_w8(destination + static_cast<uint32_t>(byte), load.rawSector[load.sectorCursor + byte]);
  }
  load.sectorCursor += bytes;
  core->r[2] = 1u;
}

void loading_presentation_wait(Core *core, GuestBody retailBody) {
  State &load = state(*core);
  if (!enh(cv_fastwait)) {
    retailBody(core);
    return;
  }
  ++load.loadingPresentationsRemoved;
  lucent::debug("x4-fastwait", "removed retail loading-presentation wait 0x80013530");
}

} // namespace x4::fast_wait
