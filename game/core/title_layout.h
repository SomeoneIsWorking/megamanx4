// SPDX-License-Identifier: AGPL-3.0-or-later
// Title-owned fixed-screen menu placement for Mega Man X4's front end.
#pragma once

#include "guest_widescreen_projection.h"

#include <cstdint>

class Core;

namespace x4::title_layout {

inline constexpr std::uint32_t kInitializeMenuItem = 0x800CB634u;
inline constexpr std::uint32_t kXPositionFixed = 0x08u;

// Translate one authored 16.16 title coordinate into the current title-wide presentation plan.
// The plan supplies the margin; this owner never encodes a display-specific pixel offset.
std::int32_t centeredX(std::int32_t retailX, const GuestProjectionPlan &plan);

// Retained-super override for the title-only state-0 menu/logo initializer. The retail body writes
// every field and runs its normal visibility setup; this owner changes only its fixed-screen x
// coordinate after the body has established the object.
void initializeMenuItem(Core *core);

void registerOverride(Core &core);

} // namespace x4::title_layout
