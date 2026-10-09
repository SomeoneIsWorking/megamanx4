// SPDX-License-Identifier: AGPL-3.0-or-later
// visibility_cull.cpp - the recovered SLUS_005.61 cull predicate; knows nothing of the guest ABI.
#include "visibility_cull.h"

#include "core.h"

namespace x4::cull {
namespace {

// The background byte is an s8 (`lb` @ 0x8002B28C); negative means screen space.
std::int32_t signExtendByte(std::uint8_t value) {
  return static_cast<std::int8_t>(value);
}

} // namespace

ScreenWindow ScreenWindow::horizontal(int half, int margin) {
  const int shifted = half + margin;
  return {shifted, 2 * shifted + RetailScreen::kWidth};
}

ScreenWindow ScreenWindow::vertical(int half) {
  return {half, 2 * half + RetailScreen::kHeight};
}

bool ScreenWindow::contains(int value) const {
  // Add in 32 bits, mask both to 16, compare unsigned (`sltiu` @ 0x8002B2F0, `sltu` @ 0x8002B38C).
  const std::uint32_t shifted = static_cast<std::uint32_t>(value) + static_cast<std::uint32_t>(offset_);
  return static_cast<std::uint16_t>(shifted) < static_cast<std::uint16_t>(bound_);
}

LayoutOffsets VisibilityCull::offsetsFor(ObjectLayout layout) {
  switch (layout) {
  case ObjectLayout::BaseObject:
    return {kBaseObjectBackgroundOffset, kPositionIntegerX, kPositionIntegerY};
  case ObjectLayout::QuadObject:
    return {kQuadObjectBackgroundOffset, kPositionIntegerX, kPositionIntegerY};
  }
  return {kBaseObjectBackgroundOffset, kPositionIntegerX, kPositionIntegerY};
}

int VisibilityCull::layerFor(Core &core, std::uint32_t object, ObjectLayout layout) const {
  const LayoutOffsets offsets = offsetsFor(layout);
  const int layer = signExtendByte(core.mem_r8(object + offsets.backgroundOffset));
  return layer < 0 ? -1 : layer;
}

std::uint32_t VisibilityCull::scrollBits(Core &core, int layer, std::uint32_t field) const {
  const std::uint32_t address =
      guest::kCameraLayersAddress + static_cast<std::uint32_t>(layer) * guest::kCameraLayerStride + field;
  return core.mem_r16(address);
}

ScreenCoordinate VisibilityCull::screenX(Core &core, std::uint32_t object, ObjectLayout layout) const {
  const LayoutOffsets offsets = offsetsFor(layout);
  const std::uint32_t position = core.mem_r16(object + offsets.xInteger);
  const int layer = layerFor(core, object, layout);
  if (layer < 0) {
    return {static_cast<std::int32_t>(position), static_cast<std::int16_t>(position)};
  }
  // `subu` wraps in 32 bits; only the low 16 are consumed.
  const std::uint32_t raw = position - scrollBits(core, layer, guest::CameraLayerOffsets::kScrollX);
  return {static_cast<std::int32_t>(raw), static_cast<std::int16_t>(raw)};
}

ScreenCoordinate VisibilityCull::screenY(Core &core, std::uint32_t object, ObjectLayout layout) const {
  const LayoutOffsets offsets = offsetsFor(layout);
  const std::uint32_t position = core.mem_r16(object + offsets.yInteger);
  const int layer = layerFor(core, object, layout);
  if (layer < 0) {
    return {static_cast<std::int32_t>(position), static_cast<std::int16_t>(position)};
  }
  const std::uint32_t raw = position - scrollBits(core, layer, guest::CameraLayerOffsets::kScrollY);
  return {static_cast<std::int32_t>(raw), static_cast<std::int16_t>(raw)};
}

bool VisibilityCull::inside(int screenX, int screenY, int halfWidth, int halfHeight) const {
  return ScreenWindow::horizontal(halfWidth, horizontalMargin()).contains(screenX) &&
         ScreenWindow::vertical(halfHeight).contains(screenY);
}

bool VisibilityCull::quadOnScreen(Core &core, std::uint32_t object) const {
  const LayoutOffsets offsets = offsetsFor(ObjectLayout::QuadObject);
  const int layer = layerFor(core, object, ObjectLayout::QuadObject);
  const std::uint32_t positionX = core.mem_r16(object + offsets.xInteger);
  const std::uint32_t positionY = core.mem_r16(object + offsets.yInteger);
  const std::uint32_t scrollX = layer < 0 ? 0u : scrollBits(core, layer, guest::CameraLayerOffsets::kScrollX);
  const std::uint32_t scrollY = layer < 0 ? 0u : scrollBits(core, layer, guest::CameraLayerOffsets::kScrollY);

  // First corner inside wins; the zero slack is retail.
  const ScreenWindow windowX = ScreenWindow::horizontal(0, horizontalMargin());
  const ScreenWindow windowY = ScreenWindow::vertical(0);
  for (std::uint32_t corner = 0; corner < 4; ++corner) {
    const std::uint32_t extentX = core.mem_r16(object + kQuadCornerX[corner]);
    const std::uint32_t extentY = core.mem_r16(object + kQuadCornerY[corner]);
    const std::uint32_t x = extentX + positionX - scrollX;
    const std::uint32_t y = extentY + positionY - scrollY;
    if (windowX.contains(static_cast<std::int16_t>(x)) && windowY.contains(static_cast<std::int16_t>(y))) {
      return true;
    }
  }
  return false;
}

void VisibilityCull::publishOnScreen(Core &core, std::uint32_t object, bool onScreen) const {
  core.mem_w8(object + kOnScreenOffset, onScreen ? 1u : 0u);
}

} // namespace x4::cull
