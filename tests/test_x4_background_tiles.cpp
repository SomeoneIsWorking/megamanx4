// Hermetic gate for game/render/background_tiles.{h,cpp}: the margin columns of the tile layers, against hand-written
// RAM.
#include "background_tiles.h"

#include "core.h"
#include "game.h"
#include "player_object.h"

#include <cstdio>
#include <memory>

namespace {

using x4::background::kBucketBase;
using x4::background::kBucketFrameStride;
using x4::background::kBucketGroupStride;
using x4::background::kCellForeground;
using x4::background::kCellSemiTransparent;
using x4::background::kFrameIndex;
using x4::background::kLayerMapBytes;
using x4::background::kMapBase;
using x4::background::kMapRowBlocks;
using x4::background::kRingBase;
using x4::background::kRingLayerStride;
using x4::background::kRingRowStride;
using x4::background::kSpriteCount;
using x4::background::kSpriteCursor;
using x4::background::kTileAttributes;
using x4::background::kTilePool;
using x4::background::MarginColumns;
using x4::background::marginColumns;
using x4::background::RetailWindow;
using x4::background::WideBackground;
using x4::guest::CameraLayerOffsets;
using x4::guest::kCameraLayersAddress;
using x4::guest::kCameraLayerStride;

#define CHECK(cond)                                                                                                    \
  do {                                                                                                                 \
    if (!(cond)) {                                                                                                     \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                                             \
      return false;                                                                                                    \
    }                                                                                                                  \
  } while (0)

// 16:9 on the 320-wide guest buffer: (428 - 320) / 2.
constexpr int kMargin = 54;

GuestProjectionPlan planWithMargin(int margin) {
  GuestProjectionPlan plan;
  plan.presentationHorizontalMargin = margin;
  return plan;
}

// Where the sprites of `columns` land for a scroll: the first starts at -(scroll & 15), one tile each.
int firstSpriteLeft(const MarginColumns &columns, int scrollX) {
  return -(scrollX & 15) - columns.left * RetailWindow::kTile;
}

int lastSpriteRight(const MarginColumns &columns, int scrollX) {
  return -(scrollX & 15) + (RetailWindow::kColumns + columns.right) * RetailWindow::kTile;
}

// The margin columns reach the plan margin at every fraction, and no column beyond the first one that does.
bool verifyColumnsReachTheMargin() {
  for (int scrollX = 0; scrollX < 4 * RetailWindow::kTile; ++scrollX) {
    const MarginColumns columns = marginColumns(scrollX, kMargin);
    CHECK(firstSpriteLeft(columns, scrollX) <= -kMargin);
    CHECK(lastSpriteRight(columns, scrollX) >= 320 + kMargin);
    CHECK(firstSpriteLeft(columns, scrollX) + RetailWindow::kTile > -kMargin);
    CHECK(lastSpriteRight(columns, scrollX) - RetailWindow::kTile < 320 + kMargin);
  }
  // 54 pixels at a whole-tile scroll: four columns left, three right (the retail window already ends at 336).
  CHECK(marginColumns(0, kMargin).left == 4);
  CHECK(marginColumns(0, kMargin).right == 3);
  CHECK(marginColumns(15, kMargin).left == 3);
  CHECK(marginColumns(15, kMargin).right == 4);
  return true;
}

bool verifyColumnsAreBoundedByTheRing() {
  // 21:9 asks for 120 pixels; the ring has 11 spare columns, so each side stops at five.
  const MarginColumns ultra = marginColumns(0, 120);
  CHECK(ultra.left == RetailWindow::kMaxSideColumns);
  CHECK(ultra.right == RetailWindow::kMaxSideColumns);
  CHECK(RetailWindow::kColumns + ultra.total() <= RetailWindow::kRing);
  // 4:3 and a negative scroll add nothing.
  CHECK(marginColumns(0, 0).total() == 0);
  CHECK(marginColumns(0, -8).total() == 0);
  CHECK(marginColumns(-1, kMargin).total() == 0);
  return true;
}

struct Fixture {
  std::unique_ptr<Game> game;
  Core *core;

  static constexpr std::uint32_t kMap = 0x80100000u;
  static constexpr std::uint32_t kPool = 0x80110000u;
  static constexpr std::uint32_t kAttributes = 0x80120000u;
  static constexpr std::uint32_t kArena = 0x80130000u;
  static constexpr std::uint32_t kTails = 0x80138000u;
  static constexpr int kMapColumnsBlocks = 4;
  static constexpr int kMapRowsBlocks = 2;

  Fixture() : game(std::make_unique<Game>()), core(&game->core) {
    core->mem_w32(kMapBase, kMap);
    core->mem_w32(kTilePool, kPool);
    core->mem_w32(kTileAttributes, kAttributes);
    core->mem_w8(kMapRowBlocks, kMapColumnsBlocks);
    core->mem_w16(kLayerMapBytes, kMapColumnsBlocks * kMapRowsBlocks);
    core->mem_w32(kFrameIndex, 1);
    core->mem_w32(kSpriteCursor, kArena);
    core->mem_w32(kSpriteCount, 0);
    for (int layer = 0; layer < x4::guest::kCameraLayerCount; ++layer) {
      const std::uint32_t base = kCameraLayersAddress + static_cast<std::uint32_t>(layer) * kCameraLayerStride;
      core->mem_w8(base + CameraLayerOffsets::kEnabled, 1);
      core->mem_w8(base + CameraLayerOffsets::kMapRightBlock, kMapColumnsBlocks - 1);
      core->mem_w8(base + CameraLayerOffsets::kMapBottomBlock, kMapRowsBlocks - 1);
    }
  }

  void scroll(int layer, int x, int y) {
    const std::uint32_t base = kCameraLayersAddress + static_cast<std::uint32_t>(layer) * kCameraLayerStride;
    core->mem_w16(base + CameraLayerOffsets::kScrollX, static_cast<std::uint16_t>(x));
    core->mem_w16(base + CameraLayerOffsets::kScrollY, static_cast<std::uint16_t>(y));
  }
  // The block id of map cell (blockColumn, blockRow) for `layer`.
  void setBlock(int layer, int blockColumn, int blockRow, std::uint8_t block) {
    core->mem_w8(kMap + static_cast<std::uint32_t>(layer * kMapColumnsBlocks * kMapRowsBlocks +
                                                   blockRow * kMapColumnsBlocks + blockColumn),
                 block);
  }
  // A tile's value is a function of its place, so a misplaced read is visible.
  static std::uint16_t poolTile(int block, int row, int column) {
    return static_cast<std::uint16_t>(0x100 * block + 0x10 * (row & 15) + (column & 15) + 1);
  }
  void fillPool(int blocks) {
    for (int block = 0; block < blocks; ++block) {
      for (int row = 0; row < 16; ++row) {
        for (int column = 0; column < 16; ++column) {
          core->mem_w16(kPool + static_cast<std::uint32_t>(block * 512 + row * 32 + column * 2),
                        poolTile(block, row, column));
        }
      }
    }
  }
  std::uint32_t ring(int layer, int row, int column) {
    return core->mem_r16(kRingBase + static_cast<std::uint32_t>(layer) * kRingLayerStride +
                         static_cast<std::uint32_t>(row & 31) * kRingRowStride +
                         static_cast<std::uint32_t>(column & 31) * 2u);
  }
  void setRing(int layer, int row, int column, std::uint16_t cell) {
    core->mem_w16(kRingBase + static_cast<std::uint32_t>(layer) * kRingLayerStride +
                      static_cast<std::uint32_t>(row & 31) * kRingRowStride +
                      static_cast<std::uint32_t>(column & 31) * 2u,
                  cell);
  }
};

bool verifyRingMarginsComeFromTheMap() {
  Fixture f;
  f.fillPool(4);
  // Layer 1: blocks 0..3 across, 2 down; block ids 1,2,3,0 on the first row.
  for (int column = 0; column < Fixture::kMapColumnsBlocks; ++column) {
    f.setBlock(1, column, 0, static_cast<std::uint8_t>(column == 3 ? 0 : column + 1));
    f.setBlock(1, column, 1, 2);
  }
  // Scroll 6 tiles in plus 9 pixels, 3 tiles down: columns 6..26 are the retail window.
  f.scroll(1, 6 * 16 + 9, 3 * 16 + 5);
  const MarginColumns columns = marginColumns(6 * 16 + 9, kMargin);
  // A sentinel in every retail cell: the refill must leave them alone.
  for (int row = 0; row < 32; ++row) {
    for (int column = 0; column < 32; ++column) {
      f.setRing(1, row, column, 0xBEEF);
    }
  }
  WideBackground{planWithMargin(kMargin)}.refillRing(*f.core);
  for (int row = 3; row < 3 + RetailWindow::kRows; ++row) {
    for (int offset = -columns.left; offset < RetailWindow::kColumns + columns.right; ++offset) {
      const int column = 6 + offset;
      const bool retail = offset >= 0 && offset < RetailWindow::kColumns;
      if (retail) {
        CHECK(f.ring(1, row, column) == 0xBEEF);
        continue;
      }
      const int blockColumn = column >> 4;
      const int blockRow = row >> 4;
      const bool inMap = column >= 0 && column < 4 * 16;
      std::uint16_t expected = 0;
      if (inMap) {
        const int block = blockRow == 0 ? (blockColumn == 3 ? 0 : blockColumn + 1) : 2;
        expected = Fixture::poolTile(block, row, column);
      }
      CHECK(f.ring(1, row, column) == expected);
    }
  }
  // Rows outside the window and the other layers are not touched.
  CHECK(f.ring(1, 2, 2) == 0xBEEF);
  CHECK(f.ring(0, 3, 2) == 0);
  CHECK(f.ring(2, 3, 2) == 0);
  return true;
}

// Left of column 0 and right of the last map column the margin is empty, never stale ring contents.
bool verifyRingMarginsAreEmptyOutsideTheMap() {
  Fixture f;
  f.fillPool(4);
  for (int column = 0; column < Fixture::kMapColumnsBlocks; ++column) {
    f.setBlock(0, column, 0, 1);
    f.setBlock(0, column, 1, 1);
  }
  for (int row = 0; row < 32; ++row) {
    for (int column = 0; column < 32; ++column) {
      f.setRing(0, row, column, 0xBEEF);
    }
  }
  // Scroll 0: columns -4..-1 are left of the map.
  f.scroll(0, 0, 0);
  WideBackground{planWithMargin(kMargin)}.refillRing(*f.core);
  for (int row = 0; row < RetailWindow::kRows; ++row) {
    for (int column = -4; column < 0; ++column) {
      CHECK(f.ring(0, row, column) == 0);
    }
    for (int column = 21; column < 24; ++column) {
      CHECK(f.ring(0, row, column) == Fixture::poolTile(1, row, column));
    }
  }
  // Scroll to the map's right end: its last column is 63, so 64.. is outside.
  f.scroll(0, 64 * 16 - 320, 0);
  WideBackground{planWithMargin(kMargin)}.refillRing(*f.core);
  const int first = (64 * 16 - 320) >> 4;
  for (int row = 0; row < RetailWindow::kRows; ++row) {
    CHECK(f.ring(0, row, first + 21) == 0);
    CHECK(f.ring(0, row, first + 22) == 0);
    CHECK(f.ring(0, row, first - 1) == Fixture::poolTile(1, row, first - 1));
  }
  return true;
}

bool verifyNoMarginChangesNothing() {
  Fixture f;
  f.fillPool(4);
  f.scroll(0, 40, 0);
  for (int column = 0; column < Fixture::kMapColumnsBlocks; ++column) {
    f.setBlock(0, column, 0, 1);
  }
  f.setRing(0, 0, 1, 0xBEEF);
  WideBackground{planWithMargin(0)}.refillRing(*f.core);
  WideBackground{planWithMargin(0)}.drawLayer(*f.core, 0);
  CHECK(f.ring(0, 0, 1) == 0xBEEF);
  CHECK(f.core->mem_r32(kSpriteCursor) == Fixture::kArena);
  CHECK(f.core->mem_r32(kSpriteCount) == 0);
  return true;
}

// Attribute: bucket in bits 24..31, v in 16..23, u in 8..15 (both high nibble), clut x in 12..15 and y in 8..11.
std::uint32_t attribute(int bucket, int u, int v, int clutX, int clutY) {
  return static_cast<std::uint32_t>(bucket) << 24 | static_cast<std::uint32_t>(v & 0xF0) << 16 |
         static_cast<std::uint32_t>(u & 0xF0) << 12 | static_cast<std::uint32_t>(clutX & 0xF) << 12 |
         static_cast<std::uint32_t>(clutY & 0xF) << 8;
}

std::uint32_t bucketAddress(int frame, int group, int bucket) {
  return kBucketBase + static_cast<std::uint32_t>(frame) * kBucketFrameStride +
         static_cast<std::uint32_t>(group) * kBucketGroupStride + static_cast<std::uint32_t>(bucket) * 4u;
}

bool verifySpritesAreLinkedLikeRetail() {
  Fixture f;
  f.scroll(2, 3 * 16 + 4, 2 * 16 + 7);
  const int firstColumn = 3;
  const int firstRow = 2;
  // Tile index 5: foreground, semi-transparent; 6: background. Attributes pick bucket 2 and 6.
  f.core->mem_w32(Fixture::kAttributes + 5 * 4, attribute(2, 0x30, 0x50, 0x1, 0x2));
  f.core->mem_w32(Fixture::kAttributes + 6 * 4, attribute(6, 0x70, 0x90, 0x3, 0x4));
  // One tile left of the retail window (column 3 - 1) and one right of it (3 + 21), the rest empty.
  f.setRing(2, firstRow + 4, firstColumn - 1, static_cast<std::uint16_t>(5 | kCellForeground | kCellSemiTransparent));
  f.setRing(2, firstRow + 4, firstColumn + 21, 6);
  // A retail-window cell is the retail pass's, so this pass must not draw it.
  f.setRing(2, firstRow + 4, firstColumn + 2, 5);
  // Bucket tails: each starts at a dummy sprite whose tag carries length 3.
  const std::uint32_t tailForeground = Fixture::kTails;
  const std::uint32_t tailBackground = Fixture::kTails + 16;
  f.core->mem_w32(tailForeground, 0x03000000u);
  f.core->mem_w32(tailBackground, 0x03000000u);
  f.core->mem_w32(bucketAddress(1, 2 + 3, 2), tailForeground);
  f.core->mem_w32(bucketAddress(1, 2, 6), tailBackground);
  // The arena holds initialised sprites: length 3 in the tag, a retail code byte.
  for (int slot = 0; slot < 4; ++slot) {
    f.core->mem_w32(Fixture::kArena + static_cast<std::uint32_t>(slot) * 16u, 0x03000000u);
    f.core->mem_w8(Fixture::kArena + static_cast<std::uint32_t>(slot) * 16u + 7u, 0x7D);
  }
  f.core->mem_w32(kSpriteCount, 7);

  WideBackground{planWithMargin(kMargin)}.drawLayer(*f.core, 2);

  // Row 4 of the window is y = 4 * 16 - 7; left column is offset -1: x = -4 - 16.
  const std::uint32_t left = Fixture::kArena;
  const std::uint32_t right = Fixture::kArena + 16;
  CHECK(f.core->mem_r16(left + 8) == static_cast<std::uint16_t>(-20));
  CHECK(f.core->mem_r16(left + 10) == static_cast<std::uint16_t>(4 * 16 - 7));
  CHECK(f.core->mem_r8(left + 12) == 0x30);
  CHECK(f.core->mem_r8(left + 13) == 0x50);
  CHECK(f.core->mem_r16(left + 14) == (0x7900 | (0x1 << 6) | 0x2));
  CHECK((f.core->mem_r8(left + 7) & 2) == 2);
  CHECK(f.core->mem_r16(right + 8) == static_cast<std::uint16_t>(-4 + 21 * 16));
  CHECK(f.core->mem_r16(right + 10) == static_cast<std::uint16_t>(4 * 16 - 7));
  CHECK(f.core->mem_r8(right + 12) == 0x70);
  CHECK(f.core->mem_r8(right + 13) == 0x90);
  CHECK((f.core->mem_r8(right + 7) & 2) == 0);
  // Appended to each bucket: the old tail points at the new sprite, which is the new tail.
  CHECK(f.core->mem_r32(tailForeground) == (0x03000000u | (left & 0x00FFFFFFu)));
  CHECK(f.core->mem_r32(tailBackground) == (0x03000000u | (right & 0x00FFFFFFu)));
  CHECK(f.core->mem_r32(bucketAddress(1, 5, 2)) == left);
  CHECK(f.core->mem_r32(bucketAddress(1, 2, 6)) == right);
  // The cursor and the frame's count advance by the two sprites linked; the retail cell was not drawn.
  CHECK(f.core->mem_r32(kSpriteCursor) == Fixture::kArena + 32);
  CHECK(f.core->mem_r32(kSpriteCount) == 9);
  return true;
}

// Layers drawn later still get their retail window: margin sprites stop where their reserve begins.
bool verifySpriteBudgetKeepsTheLaterLayers() {
  Fixture f;
  f.scroll(0, 3 * 16, 0);
  f.core->mem_w32(Fixture::kAttributes + 5 * 4, attribute(0, 0, 0, 0, 0));
  f.core->mem_w32(bucketAddress(1, 0, 0), Fixture::kTails);
  f.core->mem_w32(Fixture::kTails, 0x03000000u);
  for (int row = 0; row < RetailWindow::kRows; ++row) {
    f.setRing(0, row, 3 - 1, 5);
  }
  // Layers 1 and 2 are enabled, so 2 * 336 sprites are reserved: 1000 - 672 = 328 may be linked.
  f.core->mem_w32(kSpriteCount, 326);
  WideBackground{planWithMargin(kMargin)}.drawLayer(*f.core, 0);
  CHECK(f.core->mem_r32(kSpriteCount) == 328);
  CHECK(f.core->mem_r32(kSpriteCursor) == Fixture::kArena + 2 * 16);
  // With the later layers disabled the same layer may link all sixteen.
  Fixture g;
  g.scroll(0, 3 * 16, 0);
  g.core->mem_w8(kCameraLayersAddress + 1 * kCameraLayerStride + CameraLayerOffsets::kEnabled, 0);
  g.core->mem_w8(kCameraLayersAddress + 2 * kCameraLayerStride + CameraLayerOffsets::kEnabled, 0);
  g.core->mem_w32(Fixture::kAttributes + 5 * 4, attribute(0, 0, 0, 0, 0));
  g.core->mem_w32(bucketAddress(1, 0, 0), Fixture::kTails);
  g.core->mem_w32(Fixture::kTails, 0x03000000u);
  for (int row = 0; row < RetailWindow::kRows; ++row) {
    g.setRing(0, row, 3 - 1, 5);
  }
  g.core->mem_w32(kSpriteCount, 326);
  WideBackground{planWithMargin(kMargin)}.drawLayer(*g.core, 0);
  CHECK(g.core->mem_r32(kSpriteCount) == 326 + RetailWindow::kRows);
  return true;
}

} // namespace

int main() {
  struct Test {
    const char *name;
    bool (*run)();
  };
  const Test tests[] = {
      {"margin columns reach the plan margin", verifyColumnsReachTheMargin},
      {"margin columns are bounded by the ring", verifyColumnsAreBoundedByTheRing},
      {"ring margins come from the map", verifyRingMarginsComeFromTheMap},
      {"ring margins are empty outside the map", verifyRingMarginsAreEmptyOutsideTheMap},
      {"no margin changes nothing", verifyNoMarginChangesNothing},
      {"sprites are linked like retail", verifySpritesAreLinkedLikeRetail},
      {"the sprite budget keeps the later layers", verifySpriteBudgetKeepsTheLaterLayers},
  };
  int failures = 0;
  for (const Test &test : tests) {
    const bool passed = test.run();
    std::printf("%s: %s\n", passed ? "PASS" : "FAIL", test.name);
    failures += passed ? 0 : 1;
  }
  return failures == 0 ? 0 : 1;
}
