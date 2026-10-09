// SPDX-License-Identifier: AGPL-3.0-or-later
// background_tiles.h - the SLUS_005.61 background tile layers, drawn past the 4:3 window at wide aspects.
// Retail draws 21 x 16 tile sprites per layer from a 32 x 32 cell ring; this owner adds the columns the margin shows.
#pragma once

#include "guest_widescreen_projection.h"

#include <cstdint>

class Core;

namespace x4::background {

// One layer's tile sprites, $a0 = layer (the loops end at 0x80026C98 / 0x80026CB0).
inline constexpr std::uint32_t kDrawLayer = 0x80026AA0u;
// The per-frame ring strips of the three layers (the caller loop ends at 0x80027318).
inline constexpr std::uint32_t kRefillRing = 0x8002728Cu;

struct RetailWindow {
  static constexpr int kTile = 16;
  static constexpr int kColumns = 21;
  static constexpr int kRows = 16;
  static constexpr int kRing = 32;
  // Ring columns not used by the retail window; the margins share them.
  static constexpr int kSpareColumns = kRing - kColumns;
  static constexpr int kMaxSideColumns = kSpareColumns / 2;
  // Retail stops linking tile sprites at 1000 per frame (slti 0x3E8 @ 0x80026BB0); its arena holds 1024.
  static constexpr std::uint32_t kSpriteCap = 1000;
};

// Ring cell (row & 31) * 32 + (col & 31) of layer l, u16, at 0x801441C8 + l * 0x800 (@ 0x80026B3C, 0x80026B44).
inline constexpr std::uint32_t kRingBase = 0x801441C8u;
inline constexpr std::uint32_t kRingLayerStride = 0x800u;
inline constexpr std::uint32_t kRingRowStride = 64u;

// Scratchpad words the layer pass reads and advances.
inline constexpr std::uint32_t kFrameIndex = 0x1F800000u;
inline constexpr std::uint32_t kMapBase = 0x1F800004u;
inline constexpr std::uint32_t kTilePool = 0x1F800008u;
inline constexpr std::uint32_t kTileAttributes = 0x1F80000Cu;
inline constexpr std::uint32_t kSpriteCursor = 0x1F800108u;
inline constexpr std::uint32_t kSpriteCount = 0x1F80011Cu;

// Map geometry (lhu @ 0x80026518, lbu @ 0x80026538): bytes of one layer's block map, and blocks per map row.
inline constexpr std::uint32_t kLayerMapBytes = 0x8013BD48u;
inline constexpr std::uint32_t kMapRowBlocks = 0x80172224u;
// Per frame, three groups of eight OT bucket tails per layer, each frame 0xC0 bytes (@ 0x80026B7C).
inline constexpr std::uint32_t kBucketBase = 0x8013BD50u;
inline constexpr std::uint32_t kBucketFrameStride = 0xC0u;
inline constexpr std::uint32_t kBucketGroupStride = 0x20u;
inline constexpr std::uint32_t kForegroundGroupOffset = 3u;

// Tile cell bits: tile index, semi-transparent, foreground group.
inline constexpr std::uint16_t kCellTileMask = 0x3FFFu;
inline constexpr std::uint16_t kCellSemiTransparent = 0x4000u;
inline constexpr std::uint16_t kCellForeground = 0x8000u;

// Columns drawn on each side of the retail window.
struct MarginColumns {
  int left;
  int right;
  int total() const {
    return left + right;
  }
};

// Columns whose sprites reach [-margin, 320 + margin) for this scroll, each side capped to the ring's spare columns.
MarginColumns marginColumns(int scrollX, int marginPixels);

class WideBackground {
public:
  explicit WideBackground(const GuestProjectionPlan &plan) : margin_(plan.presentationHorizontalMargin) {}

  int margin() const {
    return margin_ > 0 ? margin_ : 0;
  }

  // Writes the margin columns of the three layers' rings from their block maps (0 outside the map).
  void refillRing(Core &core) const;
  // Links the margin columns' sprites after the retail window of `layer` has been drawn.
  void drawLayer(Core &core, int layer) const;

private:
  int margin_;
};

} // namespace x4::background
