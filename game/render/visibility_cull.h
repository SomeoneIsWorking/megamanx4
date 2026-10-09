// SPDX-License-Identifier: AGPL-3.0-or-later
// visibility_cull.h - the SLUS_005.61 visibility cull predicate, independent of the guest dispatcher.
// Every retail cull is `(u16)(v + A) <u B`, the box [-A, B-A); at margin 0 it is the retail compare bit for bit.
#pragma once

#include "guest_widescreen_projection.h"
#include "player_object.h"

#include <cstdint>

class Core;

namespace x4::cull {

// Retail 4:3 extents.
struct RetailScreen {
  // sltiu 0x140 @ 0x800D4774 / 0x800D4804 / 0x800D4894 / 0x800D4924 (quad x corners)
  static constexpr int kWidth = 320;
  // sltiu 0x0F0 @ 0x800D4780 / 0x800D4810 / 0x800D48A0 / 0x800D4930 (quad y corners)
  static constexpr int kHeight = 240;
};

// Per-side slack in pixels kept outside the visible band; widening moves the band, not the slack.
struct RetailSlack {
  // addiu $2,$5,0x20 with sltiu 0x180 / 0x130 @ 0x8002B2E8 / 0x8002B300 — is_on_screen
  static constexpr int kTight = 32;
  // addiu 0x60 with sltiu 0x200, addiu 0x50 with sltiu 0x190 @ 0x8002B420 / 0x8002B430
  static constexpr int kWideX = 96;
  static constexpr int kWideY = 80;
  // addiu 0x40 with sltiu 0x1C0 / 0x170 @ 0x8002B1BC / 0x8002B1D0 and 0x800B84B0 / 0x800B84C4
  static constexpr int kLoose = 64;
};

// BaseObj: `lb 0x14` @ 0x8002B28C, `lhu 0xa/0xe` @ 0x8002B29C/0x8002B2A0.
// QuadObj: `lb 0x37` @ 0x800D46F8, `lhu 0xa/0xe` @ 0x800D470C/0x800D4714.
inline constexpr std::uint32_t kBaseObjectBackgroundOffset = 0x14u;
inline constexpr std::uint32_t kQuadObjectBackgroundOffset = 0x37u;
inline constexpr std::uint32_t kPositionIntegerX = 0x0Au;
inline constexpr std::uint32_t kPositionIntegerY = 0x0Eu;

// QuadObj repeats the header flat, so its background byte is at +0x37, not +0x14.
enum class ObjectLayout {
  BaseObject,
  QuadObject,
};

struct LayoutOffsets {
  std::uint32_t backgroundOffset;
  std::uint32_t xInteger; // integer half of the s16.16 position
  std::uint32_t yInteger;
};

// quad_is_on_screen corner extents, in the order its blocks read them.
inline constexpr std::uint32_t kQuadCornerX[4] = {0x16u, 0x1Eu, 0x26u, 0x2Eu};
inline constexpr std::uint32_t kQuadCornerY[4] = {0x1Au, 0x22u, 0x2Au, 0x32u};

// on_screen byte, +3 in both layouts (`sb 0x3` @ 0x8002B298, 0x800D4704).
inline constexpr std::uint32_t kOnScreenOffset = 0x03u;

// `(u16)(value + offset) <u bound`. Past 15 bits of bound this is a cyclic arc rather than a box (the
// parametric sites take an int half-extent); contains() implements the wrapped form.
class ScreenWindow {
public:
  static ScreenWindow horizontal(int half, int margin);
  // No margin parameter: widening is horizontal only.
  static ScreenWindow vertical(int half);

  bool contains(int value) const;
  int offset() const {
    return offset_;
  }
  int bound() const {
    return bound_;
  }

private:
  ScreenWindow(int offset, int bound) : offset_(offset), bound_(bound) {}

  int offset_;
  int bound_;
};

// `raw` is the 32-bit register, `value` its low 16 bits as the s16 the window tests.
struct ScreenCoordinate {
  std::int32_t raw;
  int value;
};

// Recovers an object screen position, decides the cull and publishes the flag.
class VisibilityCull {
public:
  explicit VisibilityCull(const GuestProjectionPlan &plan) : margin_(plan.presentationHorizontalMargin) {}
  // The retail box: what gameplay reads.
  static VisibilityCull retail() {
    return VisibilityCull{0};
  }

  // Already 0 at 4:3 and with widescreen off; the plan resolves both.
  int horizontalMargin() const {
    return margin_ > 0 ? margin_ : 0;
  }

  static LayoutOffsets offsetsFor(ObjectLayout layout);

  // A negative background byte means screen space; otherwise the layer scroll is subtracted.
  ScreenCoordinate screenX(Core &core, std::uint32_t object, ObjectLayout layout) const;
  ScreenCoordinate screenY(Core &core, std::uint32_t object, ObjectLayout layout) const;

  // Halves are per-side slack in pixels.
  bool inside(int screenX, int screenY, int halfWidth, int halfHeight) const;

  // Admitted when any of the four corners is inside the zero-slack box.
  bool quadOnScreen(Core &core, std::uint32_t object) const;

  void publishOnScreen(Core &core, std::uint32_t object, bool onScreen) const;

private:
  explicit VisibilityCull(int margin) : margin_(margin) {}

  int layerFor(Core &core, std::uint32_t object, ObjectLayout layout) const;
  std::uint32_t scrollBits(Core &core, int layer, std::uint32_t field) const;

  int margin_;
};

// One row per flag-writing cull owner; the adapters take slack from here. The sites that return an
// off-screen verdict to gameplay (0x8002B160, 0x8002B1E8, 0x800B8490) stay retail and have no row.
struct MeasuredSite {
  std::uint32_t address;
  int halfWidth;  // per-side slack; -1 when taken from a guest register
  int halfHeight; // not always equal to halfWidth
};

// is_on_screen (1A5BC.c:601): 32/32, publishes the flag.
inline constexpr MeasuredSite kBaseOnScreenTight{0x8002B288u, RetailSlack::kTight, RetailSlack::kTight};
// func_8002B318 (1A5BC.c:620): parametric, publishes the flag.
inline constexpr MeasuredSite kBaseOnScreenParametric{0x8002B318u, -1, -1};
// func_8002B3C0 (1A5BC.c:622): asymmetric 96/80.
inline constexpr MeasuredSite kBaseOnScreenWide{0x8002B3C0u, RetailSlack::kWideX, RetailSlack::kWideY};
// quad_is_on_screen (C49B0.c:19): four corners, zero slack.
inline constexpr MeasuredSite kQuadOnScreen{0x800D46F4u, 0, 0};

inline constexpr MeasuredSite kMeasuredSites[] = {
    kBaseOnScreenTight,
    kBaseOnScreenWide,
    kBaseOnScreenParametric,
    kQuadOnScreen,
};

} // namespace x4::cull
