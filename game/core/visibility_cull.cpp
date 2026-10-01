// SPDX-License-Identifier: AGPL-3.0-or-later
// visibility_cull.cpp — the recovered SLUS_005.61 cull predicate.
//
// Every constant, address and comment in this file is a MEASURED fact of the extracted executable:
// the immediates were decoded from SLUS_005.61 itself. The matching AGPL decomp (external/mmx4)
// supplied the function names only.
//
// This file knows nothing about the guest ABI, the native seam, or which register a site reads its
// half-extent from. That is cull_overrides.cpp, and the separation is load-bearing rather than
// cosmetic: the identity contract below is provable over all 65,536 coordinates only because the
// predicate is reachable without linking the dispatcher, and a change to the seam cannot perturb it.
#include "visibility_cull.h"

#include "core.h"

namespace x4::cull {
namespace {

// The background byte is an `s8` in the guest (`lb $3,0x14($6)` @ 0x8002B28C), so its sign is what
// separates screen space from a camera layer. An unsigned read here would index the layer array with
// 255 and subtract an unrelated scroll.
std::int32_t signExtendByte(std::uint8_t value) {
  return static_cast<std::int8_t>(value);
}

} // namespace

// ── the recovered window ─────────────────────────────────────────────────────────────────────────
ScreenWindow ScreenWindow::horizontal(int half, int margin) {
  const int shifted = half + margin;
  return {shifted, 2 * shifted + RetailScreen::kWidth};
}

ScreenWindow ScreenWindow::vertical(int half) {
  return {half, 2 * half + RetailScreen::kHeight};
}

bool ScreenWindow::contains(int value) const {
  // The guest adds, masks to sixteen bits, then compares UNSIGNED (`sltiu` at 0x8002B2F0, `sltu` at
  // 0x8002B38C). Modelling the sum in 32 bits and masking both operands to sixteen reproduces the
  // wrap for a negative coordinate and for an overflowing one exactly. Nothing is clamped, and no
  // truncation the retail code did not have is introduced.
  const std::uint32_t shifted = static_cast<std::uint32_t>(value) + static_cast<std::uint32_t>(offset_);
  return static_cast<std::uint16_t>(shifted) < static_cast<std::uint16_t>(bound_);
}

// ── the owner ───────────────────────────────────────────────────────────────────────────────────
LayoutOffsets VisibilityCull::offsetsFor(ObjectLayout layout) {
  switch (layout) {
  case ObjectLayout::BaseObject:
    return {kBaseObjectBackgroundOffset, kPositionIntegerX, kPositionIntegerY};
  case ObjectLayout::QuadObject:
    return {kQuadObjectBackgroundOffset, kPositionIntegerX, kPositionIntegerY};
  }
  return {kBaseObjectBackgroundOffset, kPositionIntegerX, kPositionIntegerY};
}

int VisibilityCull::layerFor(Core &core, std::uint32_t object, ObjectLayout layout, BackgroundSource source) const {
  if (source == BackgroundSource::LayerZero) {
    return 0;
  }
  const LayoutOffsets offsets = offsetsFor(layout);
  const int layer = signExtendByte(core.mem_r8(object + offsets.backgroundOffset));
  return layer < 0 ? -1 : layer;
}

std::uint32_t VisibilityCull::scrollBits(Core &core, int layer, std::uint32_t field) const {
  const std::uint32_t address = kCameraLayersAddress + static_cast<std::uint32_t>(layer) * kCameraLayerStride + field;
  return core.mem_r16(address);
}

ScreenCoordinate
VisibilityCull::screenX(Core &core, std::uint32_t object, ObjectLayout layout, BackgroundSource source) const {
  const LayoutOffsets offsets = offsetsFor(layout);
  const std::uint32_t position = core.mem_r16(object + offsets.xInteger);
  const int layer = layerFor(core, object, layout, source);
  if (layer < 0) {
    return {static_cast<std::int32_t>(position), static_cast<std::int16_t>(position)};
  }
  // The guest's registers are 32-bit and its `subu` WRAPS; a signed subtraction here would be a
  // different function, and for a position just left of the scroll the two differ. Only the low
  // sixteen bits are ever consumed, and those are what `value` carries.
  const std::uint32_t raw = position - scrollBits(core, layer, kCameraScrollX);
  return {static_cast<std::int32_t>(raw), static_cast<std::int16_t>(raw)};
}

ScreenCoordinate
VisibilityCull::screenY(Core &core, std::uint32_t object, ObjectLayout layout, BackgroundSource source) const {
  const LayoutOffsets offsets = offsetsFor(layout);
  const std::uint32_t position = core.mem_r16(object + offsets.yInteger);
  const int layer = layerFor(core, object, layout, source);
  if (layer < 0) {
    return {static_cast<std::int32_t>(position), static_cast<std::int16_t>(position)};
  }
  const std::uint32_t raw = position - scrollBits(core, layer, kCameraScrollY);
  return {static_cast<std::int32_t>(raw), static_cast<std::int16_t>(raw)};
}

bool VisibilityCull::inside(int screenX, int screenY, int halfWidth, int halfHeight) const {
  return ScreenWindow::horizontal(halfWidth, horizontalMargin()).contains(screenX) &&
         ScreenWindow::vertical(halfHeight).contains(screenY);
}

bool VisibilityCull::quadOnScreen(Core &core, std::uint32_t object) const {
  const LayoutOffsets offsets = offsetsFor(ObjectLayout::QuadObject);
  const int layer = layerFor(core, object, ObjectLayout::QuadObject, BackgroundSource::ObjectByte);
  const std::uint32_t positionX = core.mem_r16(object + offsets.xInteger);
  const std::uint32_t positionY = core.mem_r16(object + offsets.yInteger);
  const std::uint32_t scrollX = layer < 0 ? 0u : scrollBits(core, layer, kCameraScrollX);
  const std::uint32_t scrollY = layer < 0 ? 0u : scrollBits(core, layer, kCameraScrollY);

  // The body tests four corners in address order and returns on the FIRST one inside, which is what
  // makes the result a plain OR. The zero slack is the site's, not a default: these corners carried no
  // margin at retail either, so a corner one pixel outside the band has always culled the whole quad,
  // and moving the band is the only change here.
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
