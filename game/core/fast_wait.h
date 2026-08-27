// Title-owned synchronous loader for Mega Man X4's resident CD/archive system.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

class Core;

namespace x4::fast_wait {

using GuestBody = void (*)(Core *);

// Retail SLUS_005.61 entry points. The request issuers own the complete operation when the
// enhancement is active; the wait bodies then observe their normal terminal predicates immediately.
inline constexpr uint32_t kDirectRequest = 0x80013890u;
inline constexpr uint32_t kDirectCdSetup = 0x80013968u;
inline constexpr uint32_t kDirectReadyCallback = 0x80013A20u;
inline constexpr uint32_t kArchiveRequest = 0x80013AD8u;
inline constexpr uint32_t kArchiveCdSetup = 0x80013DA8u;
inline constexpr uint32_t kArchiveReadyCallback = 0x80013E68u;
inline constexpr uint32_t kArchivePostprocess = 0x80014780u;
inline constexpr uint32_t kLoadingPresentationWait = 0x80013530u;

// The only libcd/libetc leaves virtualized while a synchronous request is on the stack.
inline constexpr uint32_t kCdReady = 0x800E5D40u;
inline constexpr uint32_t kCdControl = 0x800E5D90u;
inline constexpr uint32_t kCdControlBlocking = 0x800E5FF4u;
inline constexpr uint32_t kCdGetSector = 0x800E6158u;

enum class Phase : uint8_t {
  Inactive,
  Preparing,
  Delivering,
};

// Per-Core state: SBS/oracle cores must never share a sector cursor or an active-scope bit.
struct State {
  Phase phase = Phase::Inactive;
  std::array<uint8_t, 2352> rawSector{};
  size_t sectorCursor = 0;
  uint32_t requestId = 0;
  uint32_t requestLba = 0;
  uint32_t requestBytes = 0;
  uint32_t sectorsDelivered = 0;
  uint64_t loadsCompleted = 0;
  uint64_t loadingPresentationsRemoved = 0;
};

// Execute the measured issuer initialization, then feed its measured guest callback consecutive raw
// sectors synchronously. `postprocess` is the archive ring-drain body, or null for a direct request.
void load_synchronously(Core *core,
                        GuestBody retailIssuer,
                        GuestBody readyCallback,
                        GuestBody postprocess,
                        uint32_t expectedCallbackVa,
                        const char *what);

// Own the archive issuer's finite CD setup while a synchronous request is active. Retail waits
// three guest fields between Setmode and Setloc; the native controller completes both operations
// synchronously, so this preserves the surrounding guest state without dispatching libetc VSync.
void archive_cd_setup(Core *core,
                      GuestBody retailBody,
                      GuestBody issueLocation,
                      GuestBody queryStatus,
                      GuestBody cdReady,
                      GuestBody cdControl);

// Direct-request counterpart of archive_cd_setup. The two retail bodies have different setup and
// completion state, so each remains title-local while sharing the same synchronous libcd leaves.
void direct_cd_setup(Core *core,
                     GuestBody retailBody,
                     GuestBody issueLocation,
                     GuestBody cdReady,
                     GuestBody cdControl,
                     GuestBody publishReadyCallback);

// Scoped SDK leaves. Outside State::Preparing/Delivering every function super-calls retail.
void cd_ready(Core *core, GuestBody retailBody);
void cd_control(Core *core, GuestBody retailBody, bool blocking);
void cd_get_sector(Core *core, GuestBody retailBody);

// 0x80013530 exists solely to run and draw the loading transition task. With fast loading active it
// is removed; with the enhancement neutralized the exact generated body remains the authority.
void loading_presentation_wait(Core *core, GuestBody retailBody);

} // namespace x4::fast_wait
