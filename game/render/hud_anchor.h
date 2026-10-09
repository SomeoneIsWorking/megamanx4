// SPDX-License-Identifier: AGPL-3.0-or-later
// hud_anchor.h - the SLUS_005.61 HUD packets, moved to the screen edges they hug at 4:3.
// The HUD pass (0x80024E70) draws the life, weapon and boss gauges into the packet arenas; at a wide aspect the
// left half keeps its distance from the left edge and the right half from the right edge.
#pragma once

#include "guest_widescreen_projection.h"

#include <array>
#include <cstdint>

class Core;

namespace x4::hud {

// The HUD pass, called once per frame from the object draw pass (@ 0x80023E60).
inline constexpr std::uint32_t kHudPass = 0x80024E70u;

// Scratchpad next-free pointers of the packet arenas, set @ 0x80023DF4..0x80023E5C: polygons (0x100, 0x104),
// sprites (0x108), draw modes (0x10C) and flat quads (0x110, the gauge bars @ 0x80025588).
inline constexpr std::array<std::uint32_t, 5> kArenaCursors = {
    0x1F800100u, 0x1F800104u, 0x1F800108u, 0x1F80010Cu, 0x1F800110u};

// Packets at x < kCentre belong to the left edge.
inline constexpr int kCentre = 160;

using ArenaPositions = std::array<std::uint32_t, kArenaCursors.size()>;

class HudAnchor {
public:
  explicit HudAnchor(const GuestProjectionPlan &plan) : margin_(plan.presentationHorizontalMargin) {}

  int margin() const {
    return margin_ > 0 ? margin_ : 0;
  }

  static ArenaPositions positions(Core &core);

  // Moves every packet an arena received since `before` towards its own edge.
  void anchor(Core &core, const ArenaPositions &before) const;

private:
  void shiftPacket(Core &core, std::uint32_t packet) const;

  int margin_;
};

} // namespace x4::hud
