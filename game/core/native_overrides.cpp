#include "native_overrides.h"

#include "cd_control.h"
#include "cd_control_boundary.h"
#include "cd_controller.h"
#include "core.h"
#include "fast_wait.h"
#include "guest_execution.h"
#include "stream_interrupt.h"
#include "x4_context.h"

#include <cstdint>

namespace x4::native_overrides {
namespace {

constexpr std::uint32_t kSetGeomOffset = 0x800E90C8u;
constexpr std::uint32_t kSetDefDrawEnv = 0x800E9354u;
constexpr std::uint32_t kIssueLocation = 0x800E61BCu;
constexpr std::uint32_t kQueryArchiveStatus = 0x8001385Cu;
constexpr std::uint32_t kPublishDirectReady = 0x80013650u;

void call(std::uint32_t address, Core *core) {
  guest::call(core, address);
}

void original(std::uint32_t address, const char *owner, Core *core) {
  guest::callOriginal(core, address, owner);
}

void originalSetGeomOffset(Core *core) {
  original(kSetGeomOffset, "projection::SetGeomOffset original", core);
}

void originalSetDefDrawEnv(Core *core) {
  original(kSetDefDrawEnv, "projection::SetDefDrawEnv original", core);
}

void publishProjection(Core *core) {
  context(*core).widescreen.publishProjection(*core, originalSetGeomOffset);
}

void publishDrawEnvironment(Core *core) {
  context(*core).widescreen.publishDrawEnvironment(*core, originalSetDefDrawEnv);
}

void originalDirectRequest(Core *core) {
  original(fast_wait::kDirectRequest, "fast_wait::directRequest original", core);
}

void directReadyCallback(Core *core) {
  call(fast_wait::kDirectReadyCallback, core);
}

void runDirectRequest(Core *core) {
  fast_wait::load_synchronously(core,
                                originalDirectRequest,
                                directReadyCallback,
                                nullptr,
                                fast_wait::kDirectReadyCallback,
                                "direct CD request 0x80013890");
}

void originalDirectCdSetup(Core *core) {
  original(fast_wait::kDirectCdSetup, "fast_wait::directCdSetup original", core);
}

void issueLocation(Core *core) {
  call(kIssueLocation, core);
}

void cdReady(Core *core) {
  call(fast_wait::kCdReady, core);
}

void cdControl(Core *core) {
  call(fast_wait::kCdControl, core);
}

void publishDirectReady(Core *core) {
  call(kPublishDirectReady, core);
}

void runDirectCdSetup(Core *core) {
  fast_wait::direct_cd_setup(core, originalDirectCdSetup, issueLocation, cdReady, cdControl, publishDirectReady);
}

void originalArchiveRequest(Core *core) {
  original(fast_wait::kArchiveRequest, "fast_wait::archiveRequest original", core);
}

void archiveReadyCallback(Core *core) {
  call(fast_wait::kArchiveReadyCallback, core);
}

void archivePostprocess(Core *core) {
  call(fast_wait::kArchivePostprocess, core);
}

void runArchiveRequest(Core *core) {
  fast_wait::load_synchronously(core,
                                originalArchiveRequest,
                                archiveReadyCallback,
                                archivePostprocess,
                                fast_wait::kArchiveReadyCallback,
                                "archive CD request 0x80013AD8");
}

void originalArchiveCdSetup(Core *core) {
  original(fast_wait::kArchiveCdSetup, "fast_wait::archiveCdSetup original", core);
}

void runArchiveCdSetup(Core *core) {
  const auto queryStatus = [](Core *active) {
    call(kQueryArchiveStatus, active);
  };
  fast_wait::archive_cd_setup(core, originalArchiveCdSetup, issueLocation, queryStatus, cdReady, cdControl);
}

void originalLoadingWait(Core *core) {
  original(fast_wait::kLoadingPresentationWait, "fast_wait::loadingPresentation original", core);
}

void removeLoadingPresentationWait(Core *core) {
  fast_wait::loading_presentation_wait(core, originalLoadingWait);
}

void originalCdReady(Core *core) {
  original(fast_wait::kCdReady, "fast_wait::CdReady original", core);
}

void synchronousCdReady(Core *core) {
  if (!stream_interrupt::consumeCompletedCallback(*core)) {
    fast_wait::cd_ready(core, originalCdReady);
  }
}

void originalCdControl(Core *core) {
  original(fast_wait::kCdControl, "fast_wait::CdControl original", core);
}

void synchronousCdControl(Core *core) {
  cd_control_boundary::control(core, originalCdControl, fast_wait::cd_control, cd_controller::setMode);
}

void originalCdControlBlocking(Core *core) {
  original(fast_wait::kCdControlBlocking, "fast_wait::CdControlB original", core);
}

void synchronousCdControlBlocking(Core *core) {
  cd_control_boundary::blocking(core, originalCdControlBlocking, cd_control_sync, fast_wait::cd_control);
}

void originalCdGetSector(Core *core) {
  original(fast_wait::kCdGetSector, "fast_wait::CdGetSector original", core);
}

void synchronousCdGetSector(Core *core) {
  fast_wait::cd_get_sector(core, originalCdGetSector);
}

} // namespace

void install(Core &core) {
  guest::install(core, kSetGeomOffset, "projection::SetGeomOffset", publishProjection);
  guest::install(core, kSetDefDrawEnv, "projection::SetDefDrawEnv", publishDrawEnvironment);
  guest::install(core, fast_wait::kDirectRequest, "fast_wait::directRequest", runDirectRequest);
  guest::install(core, fast_wait::kDirectCdSetup, "fast_wait::directCdSetup", runDirectCdSetup);
  guest::install(core, fast_wait::kArchiveRequest, "fast_wait::archiveRequest", runArchiveRequest);
  guest::install(core, fast_wait::kArchiveCdSetup, "fast_wait::archiveCdSetup", runArchiveCdSetup);
  guest::install(
      core, fast_wait::kLoadingPresentationWait, "fast_wait::loadingPresentation", removeLoadingPresentationWait);
  guest::install(core, fast_wait::kCdReady, "fast_wait::CdReady", synchronousCdReady);
  guest::install(core, fast_wait::kCdControl, "fast_wait::CdControl", synchronousCdControl);
  guest::install(core, fast_wait::kCdControlBlocking, "fast_wait::CdControlB", synchronousCdControlBlocking);
  guest::install(core, fast_wait::kCdGetSector, "fast_wait::CdGetSector", synchronousCdGetSector);
}

} // namespace x4::native_overrides
