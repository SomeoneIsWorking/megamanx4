// Title-owned synchronous loader for Mega Man X4's resident CD/archive system.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

class Core;

namespace x4::fast_wait {

using GuestBody = void (*)(Core *);

// Retail SLUS_005.61 entry points.
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

// Per-Core state; a second Core must never share a sector cursor or an active-scope bit.
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

// Run the issuer init, then feed its guest callback consecutive raw sectors.
// `postprocess` is the archive ring-drain, or null for a direct request.
void load_synchronously(Core *core,
                        GuestBody retailIssuer,
                        GuestBody readyCallback,
                        GuestBody postprocess,
                        uint32_t expectedCallbackVa,
                        const char *what);

// Archive issuer's CD setup: retail waits three guest fields between Setmode and Setloc; skipped here
// because the native controller completes both synchronously.
void archive_cd_setup(Core *core,
                      GuestBody retailBody,
                      GuestBody issueLocation,
                      GuestBody queryStatus,
                      GuestBody cdReady,
                      GuestBody cdControl);

// Direct-request counterpart; the two retail bodies differ in setup and completion state.
void direct_cd_setup(Core *core,
                     GuestBody retailBody,
                     GuestBody issueLocation,
                     GuestBody cdReady,
                     GuestBody cdControl,
                     GuestBody publishReadyCallback);

// Scoped SDK leaves; outside State::Preparing/Delivering they call the original guest body.
void cd_ready(Core *core, GuestBody retailBody);
void cd_control(Core *core, GuestBody retailBody, bool blocking);
void cd_get_sector(Core *core, GuestBody retailBody);

// 0x80013530 only runs the loading transition task; removed when fast loading is active.
void loading_presentation_wait(Core *core, GuestBody retailBody);

} // namespace x4::fast_wait
