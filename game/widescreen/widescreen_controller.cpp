#include "widescreen_controller.h"

#include "core.h"
#include "enhancements.h"
#include "game.h"
#include "gpu_vk.h"
#include "x4_context.h"

#include <cstdlib>
#include <limits>
#include <lucent/log.h>

namespace x4 {
namespace {

// The single SetGeomOffset/SetGeomScreen publication: 320x240, H=512.
constexpr GuestProjectionGeometry kRetailProjection{{320, 240}, 320};
constexpr uint32_t kDrawEnvironmentWidthOffset = 4u;

} // namespace

PresentationAspect WidescreenPolicy::presentationAspect(const Core &core) const {
  // STR movies are 320x240 pictures without the widened GTE projection, so they stay 4:3 while streaming.
  if (core.game && (core.game->cd.stream_active != 0 || context(core).movieCleanup.pending())) {
    return PresentationAspect::Standard4x3;
  }
  return enh(widescreenCvar()) ? PresentationAspect::Wide16x9 : PresentationAspect::Standard4x3;
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

  // Only OFX comes from the plan (retail on the record path); OFY (a1) and H stay retail.
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

  // Only RECT.w is replaced; the retail body owns every other field.
  core.mem_w16(environment + kDrawEnvironmentWidthOffset, static_cast<uint16_t>(plan_.guestDrawWidth));
}

void WidescreenController::synchronizePresentation(Core &core) {
  if (!projectionPublished_) {
    lucent::error("x4-wide", "frame presentation ran before the title published its projection");
    std::abort();
  }

  // Re-latch so the cull margin follows the policy: 4:3 during movies, wide again after.
  plan_ = latch_(&core, kRetailProjection);
}

} // namespace x4
