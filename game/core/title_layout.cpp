// SPDX-License-Identifier: AGPL-3.0-or-later
// Derived from external/mmx4/src/main/BBE34.c; retail addresses and layout are independently
// re-measured by tools/verify_title_composition.py from SLUS_005.61.
#include "title_layout.h"

#include "core.h"
#include "enhancements.h"
#include "guest_execution.h"
#include "x4_context.h"

#include <lucent/log.h>

namespace x4::title_layout {

std::int32_t centeredX(std::int32_t retailX, const GuestProjectionPlan &plan) {
  if (!plan.widescreen() || plan.presentationHorizontalMargin <= 0) {
    return retailX;
  }
  return retailX + (plan.presentationHorizontalMargin << 16);
}

void initializeMenuItem(Core *core) {
  guest::callOriginal(core, kInitializeMenuItem, "title::initializeMenuItem original");

  if (!enh(cv_widescreen)) {
    return;
  }
  const GuestProjectionPlan &plan = context(*core).widescreen.plan();
  const std::uint32_t object = core->r[4];
  const std::int32_t retailX = static_cast<std::int32_t>(core->mem_r32(object + kXPositionFixed));
  core->mem_w32(object + kXPositionFixed, static_cast<std::uint32_t>(centeredX(retailX, plan)));
}

void registerOverride(Core &core) {
  guest::install(core, kInitializeMenuItem, "title::initializeMenuItem", initializeMenuItem);
}

} // namespace x4::title_layout
