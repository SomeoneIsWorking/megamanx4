#include "x4_catalog.h"

#include "single_title_catalog.h"
#include "x4_runtime.h"

namespace x4 {
namespace {

// The executable SYSTEM.CNF boots, measured from the retail SLUS_005.61.
constexpr psx::host::TitleIdentity kTitleIdentity{
    .displayName = "Mega Man X4",
    .serial = "SLUS_005.61",
    .slug = "megamanx4",
    .fileSize = 1179648,
    .sha256 = "dae43d44a9f3176208830ddbba0607bb627ebcd7faf9b36fc03dd0ffda34d2e8",
    .entry = 0x800DAE8Cu,
    .globalPointer = 0u,
    .textAddress = 0x80010000u,
    .textSize = 0x11F800u,
    .stackAddress = 0x801FFFF0u,
    .stackOffset = 0u,
    .discEnvVar = "PSXPORT_X4_DISC",
    .discExecutablePath = "SLUS_005.61",
};

} // namespace

std::unique_ptr<psx::host::TitleCatalog> createCatalog() {
  return std::make_unique<psx::host::SingleTitleCatalog>(kTitleIdentity, "scratch/bin", std::make_unique<X4Runtime>());
}

} // namespace x4
