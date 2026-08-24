#include "widescreen_controller.h"

#include "core.h"
#include "enhancements.h"
#include "gpu_vk.h"

#include <cstdlib>
#include <limits>
#include <lucent/log.h>

namespace x4 {
namespace {

// SLUS_005.61's sole SetGeomOffset/SetGeomScreen publication uses a 320x240 projection and H=512.
// tools/verify_projection.py derives the call site and arguments from the retail executable.
constexpr GuestProjectionGeometry kRetailProjection{{320, 240}, 320};
constexpr uint32_t kDrawEnvironmentWidthOffset = 4u;

} // namespace

PresentationAspect WidescreenPolicy::presentationAspect(const Core &) const {
  return enh(cv_widescreen) ? PresentationAspect::Wide16x9 : PresentationAspect::Standard4x3;
}

WidescreenController::WidescreenController() : WidescreenController(gpu_vk_latch_guest_projection) {}

WidescreenController::WidescreenController(ProjectionLatch latch) : latch_(latch) {
  if (!latch_) {
    lucent::error("x4-wide", "projection controller requires a plan latch");
    std::abort();
  }
}

void WidescreenController::publishProjection(Core &core, GuestBody retailBody) {
  if (!retailBody) {
    lucent::error("x4-wide", "SetGeomOffset publication requires the retail body");
    std::abort();
  }

  plan_ = latch_(&core, kRetailProjection);
  if (plan_.projectionCenterX <= 0 || plan_.guestDrawWidth <= 0 ||
      plan_.guestDrawWidth > std::numeric_limits<uint16_t>::max()) {
    lucent::error("x4-wide",
                  "framework returned an invalid guest projection (center={}, width={})",
                  plan_.projectionCenterX,
                  plan_.guestDrawWidth);
    std::abort();
  }
  projectionPublished_ = true;
  lucent::info("x4-wide",
               "guest projection {}x{} -> {}x{}, OFX={}, draw width={}",
               plan_.nativeProjectionExtent.width,
               plan_.nativeProjectionExtent.height,
               plan_.projectionExtent.width,
               plan_.projectionExtent.height,
               plan_.projectionCenterX,
               plan_.guestDrawWidth);

  // Replace only OFX. OFY remains the retail value in a1, and SetGeomScreen/H is not overridden.
  core.r[4] = static_cast<uint32_t>(plan_.projectionCenterX);
  retailBody(&core);
}

void WidescreenController::publishDrawEnvironment(Core &core, GuestBody retailBody) {
  if (!retailBody) {
    lucent::error("x4-wide", "SetDefDrawEnv publication requires the retail body");
    std::abort();
  }
  if (!projectionPublished_) {
    lucent::error("x4-wide",
                  "SetDefDrawEnv ran before SLUS_005.61 published its measured projection; refusing "
                  "an unpaired guest clip");
    std::abort();
  }

  const uint32_t environment = core.r[4];
  retailBody(&core);

  // The retail body remains the authority for x/y/h and every non-RECT field. Its RECT.w is the only
  // measured field replaced, matching the already-latched guest projection plan.
  core.mem_w16(environment + kDrawEnvironmentWidthOffset, static_cast<uint16_t>(plan_.guestDrawWidth));
}

} // namespace x4
