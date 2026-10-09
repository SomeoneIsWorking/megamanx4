// SPDX-License-Identifier: AGPL-3.0-or-later
// background_tiles.cpp - margin columns of the SLUS_005.61 background tile layers; knows nothing of the guest ABI.
#include "background_tiles.h"

#include "core.h"
#include "player_object.h"

namespace x4::background {
namespace {

using guest::CameraLayerOffsets;

// Retail rounds a scroll toward zero before the shift (`bgez`/`addiu 0xF` @ 0x80026B00); margins need scroll >= 0.
constexpr int kTile = RetailWindow::kTile;
constexpr int kTileShift = 4;
constexpr int kTileMask = kTile - 1;
constexpr int kRingMask = RetailWindow::kRing - 1;

constexpr int ceilTiles(int pixels) {
  return pixels > 0 ? (pixels + kTileMask) >> kTileShift : 0;
}

std::uint32_t layerAddress(int layer) {
  return guest::kCameraLayersAddress + static_cast<std::uint32_t>(layer) * guest::kCameraLayerStride;
}

std::uint32_t ringCell(int layer, int row, int column) {
  return kRingBase + static_cast<std::uint32_t>(layer) * kRingLayerStride +
         static_cast<std::uint32_t>(row & kRingMask) * kRingRowStride +
         static_cast<std::uint32_t>(column & kRingMask) * 2u;
}

// A layer's view onto its map, in tiles.
struct LayerView {
  int scrollX;
  int scrollY;
  int columns; // tiles across the map
  int rows;    // tiles down the map
  int firstColumn() const {
    return scrollX >> kTileShift;
  }
  int firstRow() const {
    return scrollY >> kTileShift;
  }
  bool contains(int column, int row) const {
    return column >= 0 && column < columns && row >= 0 && row < rows;
  }
};

LayerView readLayer(Core &core, int layer) {
  const std::uint32_t base = layerAddress(layer);
  const int right = core.mem_r8(base + CameraLayerOffsets::kMapRightBlock);
  const int bottom = core.mem_r8(base + CameraLayerOffsets::kMapBottomBlock);
  return {static_cast<std::int16_t>(core.mem_r16(base + CameraLayerOffsets::kScrollX)),
          static_cast<std::int16_t>(core.mem_r16(base + CameraLayerOffsets::kScrollY)),
          (right + 1) * kTile,
          (bottom + 1) * kTile};
}

// block map byte, then the u16 cell of that block's 16 x 16 tile page (@ 0x80027518, 0x80027584).
std::uint16_t mapTile(Core &core, int layer, int column, int row) {
  const std::uint32_t rowBlocks = core.mem_r8(kMapRowBlocks);
  const std::uint32_t layerBytes = core.mem_r16(kLayerMapBytes);
  const std::uint32_t block = core.mem_r8(core.mem_r32(kMapBase) + static_cast<std::uint32_t>(layer) * layerBytes +
                                          static_cast<std::uint32_t>(row >> kTileShift) * rowBlocks +
                                          static_cast<std::uint32_t>(column >> kTileShift));
  return core.mem_r16(core.mem_r32(kTilePool) + (block << 9) + static_cast<std::uint32_t>(row & kTileMask) * 32u +
                      static_cast<std::uint32_t>(column & kTileMask) * 2u);
}

// A SPRT_16 of the arena (@ 0x80026BC0..0x80026C84), then appended to its bucket's chain.
void linkSprite(Core &core, std::uint32_t sprite, std::uint16_t cell, int layer, int x, int y) {
  const std::uint32_t attribute = core.mem_r32(core.mem_r32(kTileAttributes) + (cell & kCellTileMask) * 4u);
  core.mem_w16(sprite + 14u,
               static_cast<std::uint16_t>((((attribute & 0xF000u) >> 6) + 0x7900u) | ((attribute & 0xF00u) >> 8)));
  const std::uint8_t code = core.mem_r8(sprite + 7u);
  core.mem_w8(sprite + 7u, (cell & kCellSemiTransparent) != 0 ? (code | 2u) : (code & ~2u));
  core.mem_w8(sprite + 12u, static_cast<std::uint8_t>((attribute >> 12) & 0xF0u));
  core.mem_w8(sprite + 13u, static_cast<std::uint8_t>((attribute >> 16) & 0xF0u));
  core.mem_w16(sprite + 8u, static_cast<std::uint16_t>(x));
  core.mem_w16(sprite + 10u, static_cast<std::uint16_t>(y));

  const std::uint32_t group =
      static_cast<std::uint32_t>(layer) + ((cell & kCellForeground) != 0 ? kForegroundGroupOffset : 0u);
  const std::uint32_t bucket = kBucketBase + core.mem_r32(kFrameIndex) * kBucketFrameStride +
                               group * kBucketGroupStride + (attribute >> 24) * 4u;
  const std::uint32_t tail = core.mem_r32(bucket);
  core.mem_w32(tail, (core.mem_r32(tail) & 0xFF000000u) | (sprite & 0x00FFFFFFu));
  core.mem_w32(bucket, sprite);
}

// Sprites the later layers may still need for their own retail windows.
int reservedSprites(Core &core, int layer) {
  int reserved = 0;
  for (int later = layer + 1; later < guest::kCameraLayerCount; ++later) {
    if (core.mem_r8(layerAddress(later) + CameraLayerOffsets::kEnabled) != 0) {
      reserved += RetailWindow::kColumns * RetailWindow::kRows;
    }
  }
  return reserved;
}

} // namespace

MarginColumns marginColumns(int scrollX, int marginPixels) {
  if (marginPixels <= 0 || scrollX < 0) {
    return {0, 0};
  }
  const int fraction = scrollX & kTileMask;
  // Retail's first sprite starts at -fraction and the 21st ends at 336 - fraction.
  const int retailEnd = RetailWindow::kColumns * kTile - fraction;
  const int left = ceilTiles(marginPixels - fraction);
  const int right = ceilTiles(320 + marginPixels - retailEnd);
  const int cap = RetailWindow::kMaxSideColumns;
  return {left < cap ? left : cap, right < cap ? right : cap};
}

void WideBackground::refillRing(Core &core) const {
  for (int layer = 0; layer < guest::kCameraLayerCount; ++layer) {
    const LayerView view = readLayer(core, layer);
    const MarginColumns columns = marginColumns(view.scrollX, margin());
    if (columns.total() == 0 || view.scrollY < 0) {
      continue;
    }
    const int first = view.firstColumn();
    const int top = view.firstRow();
    for (int row = top; row < top + RetailWindow::kRows; ++row) {
      for (int offset = -columns.left; offset < columns.right + RetailWindow::kColumns; ++offset) {
        if (offset >= 0 && offset < RetailWindow::kColumns) {
          continue;
        }
        const int column = first + offset;
        const std::uint16_t cell = view.contains(column, row) ? mapTile(core, layer, column, row) : std::uint16_t{0};
        core.mem_w16(ringCell(layer, row, column), cell);
      }
    }
  }
}

void WideBackground::drawLayer(Core &core, int layer) const {
  const LayerView view = readLayer(core, layer);
  const MarginColumns columns = marginColumns(view.scrollX, margin());
  if (columns.total() == 0 || view.scrollY < 0) {
    return;
  }
  const std::uint32_t limit = RetailWindow::kSpriteCap - static_cast<std::uint32_t>(reservedSprites(core, layer));
  std::uint32_t sprite = core.mem_r32(kSpriteCursor);
  std::uint32_t count = core.mem_r32(kSpriteCount);
  const int first = view.firstColumn();
  const int top = view.firstRow();
  const int originX = -(view.scrollX & kTileMask);
  const int originY = -(view.scrollY & kTileMask);
  for (int row = 0; row < RetailWindow::kRows; ++row) {
    for (int offset = -columns.left; offset < columns.right + RetailWindow::kColumns; ++offset) {
      if (offset >= 0 && offset < RetailWindow::kColumns) {
        continue;
      }
      const std::uint16_t cell = core.mem_r16(ringCell(layer, top + row, first + offset));
      if (cell == 0) {
        continue;
      }
      if (count >= limit) {
        core.mem_w32(kSpriteCursor, sprite);
        core.mem_w32(kSpriteCount, count);
        return;
      }
      ++count;
      linkSprite(core, sprite, cell, layer, originX + offset * kTile, originY + row * kTile);
      sprite += 16u;
    }
  }
  core.mem_w32(kSpriteCursor, sprite);
  core.mem_w32(kSpriteCount, count);
}

} // namespace x4::background
