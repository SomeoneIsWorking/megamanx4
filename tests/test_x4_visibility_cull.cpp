// Hermetic gate for game/render/visibility_cull.{h,cpp}: exhaustive 4:3 identity against the disassembly,
// and widening that admits only the margin bands.
#include "visibility_cull.h"

#include "core.h"
#include "game.h"

#include <cstdio>
#include <memory>

namespace {

using x4::cull::BackgroundSource;
using x4::cull::kBaseOffScreenLayerZero;
using x4::cull::kBaseOffScreenLoose;
using x4::cull::kBaseOffScreenParametric;
using x4::cull::kBaseOnScreenParametric;
using x4::cull::kBaseOnScreenTight;
using x4::cull::kBaseOnScreenWide;
using x4::cull::kCameraLayersAddress;
using x4::cull::kCameraLayerStride;
using x4::cull::kCameraScrollX;
using x4::cull::kCameraScrollY;
using x4::cull::kMeasuredSites;
using x4::cull::kOnScreenOffset;
using x4::cull::kQuadCornerX;
using x4::cull::kQuadCornerY;
using x4::cull::kQuadOnScreen;
using x4::cull::MeasuredSite;
using x4::cull::ObjectLayout;
using x4::cull::RetailScreen;
using x4::cull::RetailSlack;
using x4::cull::ScreenCoordinate;
using x4::cull::ScreenWindow;
using x4::cull::VisibilityCull;

int g_checks = 0;
int g_windows = 0;
int g_differences = 0;

#define CHECK(cond)                                                                                                    \
  do {                                                                                                                 \
    ++g_checks;                                                                                                        \
    if (!(cond)) {                                                                                                     \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                                             \
      return false;                                                                                                    \
    }                                                                                                                  \
  } while (0)

// Only presentationHorizontalMargin is consumed; kExpectedMargin is the 320 -> 428 widening, (428 - 320) / 2.
constexpr int kExpectedMargin = 54;

GuestProjectionPlan retailPlan() {
  GuestProjectionPlan plan;
  plan.nativeExtent = {RetailScreen::kWidth, RetailScreen::kHeight};
  plan.presentationExtent = {RetailScreen::kWidth, RetailScreen::kHeight};
  plan.presentationHorizontalMargin = 0;
  return plan;
}

GuestProjectionPlan widePlan(int margin) {
  GuestProjectionPlan plan = retailPlan();
  plan.presentationExtent = {RetailScreen::kWidth + 2 * margin, RetailScreen::kHeight};
  plan.presentationHorizontalMargin = margin;
  return plan;
}

// Retail compare from the disassembly: addiu t,v,A / andi t,t,0xFFFF / sltiu c,t,B at 0x8002B2E8..0x8002B2F0
// (also 0x8002B1BC, 0x8002B420, 0x800B84B0). The sltu form at 0x8002B38C is the same predicate.
bool retailWindow(int value, int addend, int bound) {
  const unsigned int shifted = static_cast<unsigned int>(static_cast<int>(static_cast<short>(value)) +
                                                         static_cast<int>(static_cast<short>(addend)));
  return static_cast<unsigned short>(shifted) < static_cast<unsigned short>(bound);
}

// Per window shape: per-side slack and the retail addiu/sltiu immediates, transcribed from the image.
struct Shape {
  const char *name;
  int halfX;
  int halfY;
  int retailAddendX;
  int retailBoundX;
  int retailAddendY;
  int retailBoundY;
};

// One row per measured shape; halfX/halfY are the recovered per-side slack.
constexpr Shape kShapes[] = {
    // is_on_screen 0x8002B288: addiu 0x20 / sltiu 0x180, addiu 0x20 / sltiu 0x130
    {"is_on_screen tight", RetailSlack::kTight, RetailSlack::kTight, 0x20, 0x180, 0x20, 0x130},
    // func_8002B3C0 0x8002B3C0: addiu 0x60 / sltiu 0x200, addiu 0x50 / sltiu 0x190 (asymmetric, 96 x 80)
    {"on_screen wide", RetailSlack::kWideX, RetailSlack::kWideY, 0x60, 0x200, 0x50, 0x190},
    // func_8002B160 0x8002B160 and 0x800B8490: addiu 0x40 / sltiu 0x1C0, addiu 0x40 / sltiu 0x170
    {"off_screen loose", RetailSlack::kLoose, RetailSlack::kLoose, 0x40, 0x1C0, 0x40, 0x170},
    // quad_is_on_screen 0x800D46F4: no addend at all, sltiu 0x140 / sltiu 0x0F0
    {"quad corner", 0, 0, 0x00, 0x140, 0x00, 0x0F0},
    // func_8002B318 / 0x8002B1E8 take the half-extent in $5/$6, so the bound is a register. Decomp call sites:
    // 0x20/0x20 (visual_objs.c:26), 0x80/0x30 (select_a_character.c:332), 0xA0/0xA0 (395D0.c:3634);
    // this row is 0x20/0x20: 2*0x20 + 320 and 2*0x20 + 240.
    {"parametric 0x20/0x20", 0x20, 0x20, 0x20, 0x40 + 0x140, 0x20, 0x40 + 0xF0},
    // Plus an asymmetric parametric instance, 0x80/0x30.
    {"parametric 0x80/0x30", 0x80, 0x30, 0x80, 0x100 + 0x140, 0x30, 0x60 + 0xF0},
};

// 1. Identity at 4:3, exhaustive; also pins each window's edges.
bool verify_4x3_identity_exhaustive() {
  // One sweep covers both axes.
  for (const Shape &shape : kShapes) {
    const ScreenWindow windowX = ScreenWindow::horizontal(shape.halfX, 0);
    const ScreenWindow windowY = ScreenWindow::vertical(shape.halfY);
    CHECK(windowX.offset() == shape.retailAddendX);
    CHECK(windowX.bound() == shape.retailBoundX);
    CHECK(windowY.offset() == shape.retailAddendY);
    CHECK(windowY.bound() == shape.retailBoundY);
    for (int coordinate = -32768; coordinate < 32768; ++coordinate) {
      ++g_windows;
      const bool mineX = windowX.contains(coordinate);
      const bool retailX = retailWindow(coordinate, shape.retailAddendX, shape.retailBoundX);
      const bool mineY = windowY.contains(coordinate);
      const bool retailY = retailWindow(coordinate, shape.retailAddendY, shape.retailBoundY);
      if (mineX != retailX || mineY != retailY) {
        ++g_differences;
        std::fprintf(stderr,
                     "FAIL 4:3 identity %s x=%d owner=(%d,%d) retail=(%d,%d)\n",
                     shape.name,
                     coordinate,
                     mineX ? 1 : 0,
                     mineY ? 1 : 0,
                     retailX ? 1 : 0,
                     retailY ? 1 : 0);
        return false;
      }
    }
  }
  return true;
}

// Same sweep at the plan margin, against the box derived from the widened frame: guest x lands at x + margin
// in [0, 320 + 2*margin), so a guest coordinate can land over [-margin, 320 + margin) plus `half` slack each side.
bool verify_widened_bands(int margin) {
  for (const Shape &shape : kShapes) {
    const VisibilityCull cull{widePlan(margin)};
    CHECK(cull.horizontalMargin() == margin);
    const int lo = -(shape.halfX + margin);
    const int hi = RetailScreen::kWidth + shape.halfX + margin;
    // The band edges themselves, and the pixels just outside them, on both sides.
    CHECK(cull.inside(lo, 0, shape.halfX, shape.halfY));
    CHECK(cull.inside(hi - 1, 0, shape.halfX, shape.halfY));
    CHECK(!cull.inside(lo - 1, 0, shape.halfX, shape.halfY));
    CHECK(!cull.inside(hi, 0, shape.halfX, shape.halfY));
    // The 16-bit mask must still wrap: a far-below coordinate sums to a large unsigned value and is rejected.
    CHECK(!cull.inside(-32768, 0, shape.halfX, shape.halfY));
    CHECK(!cull.inside(-32768 + shape.halfX + margin, 0, shape.halfX, shape.halfY));
    // Vertical is untouched: the band stays [-halfY, 240 + halfY).
    CHECK(cull.inside(0, -shape.halfY, shape.halfX, shape.halfY));
    CHECK(cull.inside(0, RetailScreen::kHeight + shape.halfY - 1, shape.halfX, shape.halfY));
    CHECK(!cull.inside(0, -shape.halfY - 1, shape.halfX, shape.halfY));
    CHECK(!cull.inside(0, RetailScreen::kHeight + shape.halfY, shape.halfX, shape.halfY));
    // Exhaustive agreement with the widened box.
    for (int coordinate = -32768; coordinate < 32768; ++coordinate) {
      ++g_windows;
      const bool expected = coordinate >= lo && coordinate < hi;
      if (cull.inside(coordinate, 0, shape.halfX, shape.halfY) != expected) {
        ++g_differences;
        std::fprintf(stderr, "FAIL widened %s x=%d expected=%d\n", shape.name, coordinate, expected ? 1 : 0);
        return false;
      }
    }
  }
  return true;
}

// 1b. Each measured site is bound to the slack its own disassembly carries; parametric rows are marked as such.
bool verify_measured_site_table() {
  // Seven sites, no duplicate addresses, all inside the text section.
  for (std::size_t i = 0; i < std::size(kMeasuredSites); ++i) {
    const MeasuredSite &site = kMeasuredSites[i];
    for (std::size_t j = 0; j < i; ++j) {
      CHECK(kMeasuredSites[j].address != site.address);
    }
    CHECK(site.address >= 0x80010000u && site.address < 0x80130000u);
  }
  CHECK(kBaseOnScreenTight.address == 0x8002B288u);
  CHECK(kBaseOnScreenParametric.address == 0x8002B318u);
  CHECK(kBaseOnScreenWide.address == 0x8002B3C0u);
  CHECK(kBaseOffScreenParametric.address == 0x8002B1E8u);
  CHECK(kBaseOffScreenLoose.address == 0x8002B160u);
  CHECK(kBaseOffScreenLayerZero.address == 0x800B8490u);
  CHECK(kQuadOnScreen.address == 0x800D46F4u);

  // A site's slack must be covered by the sweep; parametric rows (-1) are exempt, their slack arrives in a register.
  const MeasuredSite *pinned[] = {
      &kBaseOnScreenTight, &kBaseOnScreenWide, &kBaseOffScreenLoose, &kBaseOffScreenLayerZero, &kQuadOnScreen};
  for (const MeasuredSite *site : pinned) {
    bool covered = false;
    for (const Shape &shape : kShapes) {
      if (shape.halfX == site->halfWidth && shape.halfY == site->halfHeight) {
        covered = true;
      }
    }
    CHECK(covered);
  }
  // The asymmetric row is 0x60/0x200 horizontal and 0x50/0x190 vertical: 96/80, not 96/96.
  CHECK(kBaseOnScreenWide.halfWidth == 0x60);
  CHECK(kBaseOnScreenWide.halfHeight == 0x50);
  CHECK(kBaseOnScreenWide.halfWidth != kBaseOnScreenWide.halfHeight);
  // Layer-0 is the only row ignoring the background byte; the zero-slack row is the only publishing one with no slack.
  CHECK(kBaseOffScreenLayerZero.layerZeroScroll);
  for (const MeasuredSite &site : kMeasuredSites) {
    if (site.address != kBaseOffScreenLayerZero.address) {
      CHECK(!site.layerZeroScroll);
    }
  }
  CHECK(kQuadOnScreen.halfWidth == 0 && kQuadOnScreen.halfHeight == 0);
  CHECK(kQuadOnScreen.writesFlag);
  // The flag polarity: the two off-screen sites return the inverse, the four writers do not.
  CHECK(kBaseOffScreenLoose.returnsOffScreen && !kBaseOffScreenLoose.writesFlag);
  CHECK(kBaseOffScreenParametric.returnsOffScreen && !kBaseOffScreenParametric.writesFlag);
  CHECK(kBaseOffScreenLayerZero.returnsOffScreen && !kBaseOffScreenLayerZero.writesFlag);
  CHECK(kBaseOnScreenTight.writesFlag && !kBaseOnScreenTight.returnsOffScreen);
  CHECK(kBaseOnScreenWide.writesFlag && !kBaseOnScreenWide.returnsOffScreen);
  CHECK(kBaseOnScreenParametric.writesFlag && !kBaseOnScreenParametric.returnsOffScreen);
  CHECK(kBaseOnScreenParametric.halfWidth == -1 && kBaseOnScreenParametric.halfHeight == -1);
  return true;
}

// 1c. `contains` masks to 16 bits like the guest's andi 0xFFFF. The two parametric sites take a half-extent in a guest
// register ($5, plain int) that can overflow: with A = 40000 the bound 80320 masks to 14784, so the window is the arc
// [-40000, -25216) U [25536, 40320), not a box, and 0 is outside it.
bool verify_sixteen_bit_parameter_wrap() {
  const int huge = 40000;
  const int bound = 2 * huge + RetailScreen::kWidth;
  const ScreenWindow window = ScreenWindow::horizontal(huge, 0);
  CHECK(window.offset() == huge);
  CHECK(bound > 0xFFFF);
  CHECK(static_cast<int>(static_cast<std::uint16_t>(bound)) == 14784);
  // Measured arcs, edge by edge.
  CHECK(window.contains(-40000));
  CHECK(!window.contains(-25216));
  CHECK(window.contains(-25217));
  CHECK(!window.contains(25535));
  CHECK(window.contains(25536));
  CHECK(!window.contains(40320));
  CHECK(window.contains(40319));
  // 0 is outside; a box reading [-A, B-A) would get it wrong.
  CHECK(!window.contains(0));
  // A negative half-extent ($5 is a plain int) follows the retail arithmetic.
  const ScreenWindow negative = ScreenWindow::horizontal(-100, 0);
  CHECK(negative.offset() == -100);
  CHECK(negative.bound() == -200 + RetailScreen::kWidth);
  CHECK(negative.contains(0) == retailWindow(0, -100, 120));
  // Exhaustive identity for the overflowing parameter too.
  for (int coordinate = -32768; coordinate < 32768; ++coordinate) {
    ++g_windows;
    if (window.contains(coordinate) != retailWindow(coordinate, huge, bound)) {
      ++g_differences;
      std::fprintf(stderr, "FAIL 16-bit wrap v=%d\n", coordinate);
      return false;
    }
  }
  return true;
}

// Negative control: with the margin dropped, the widened edges are no longer admitted.
bool verify_wide_requires_the_plan() {
  const int margin = kExpectedMargin;
  const VisibilityCull retail{retailPlan()};
  const VisibilityCull wide{widePlan(margin)};
  CHECK(retail.horizontalMargin() == 0);
  CHECK(wide.horizontalMargin() == margin);
  // is_on_screen band is [-32, 352) at 4:3 and [-(32+margin), 320+32+margin) wide; objects in either new margin band
  // flip from culled to admitted only when the plan carries the margin.
  const int rightBand = RetailScreen::kWidth + RetailSlack::kTight;
  const int leftBand = -RetailSlack::kTight - 1;
  CHECK(!retail.inside(rightBand, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(wide.inside(rightBand, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(!retail.inside(leftBand, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(wide.inside(leftBand, 0, RetailSlack::kTight, RetailSlack::kTight));
  // And the far edge, so a one-sided widening fails.
  CHECK(!retail.inside(rightBand + margin - 1, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(wide.inside(rightBand + margin - 1, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(!retail.inside(-RetailSlack::kTight - margin, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(wide.inside(-RetailSlack::kTight - margin, 0, RetailSlack::kTight, RetailSlack::kTight));
  // A plan that went narrower than native must clamp to 0 rather than invert the window.
  GuestProjectionPlan inverted = retailPlan();
  inverted.presentationHorizontalMargin = -40;
  CHECK(VisibilityCull{inverted}.horizontalMargin() == 0);
  CHECK(VisibilityCull{inverted}.inside(0, 0, RetailSlack::kTight, RetailSlack::kTight));
  // Wide must agree with retail on every coordinate retail already covered.
  for (int coordinate = -RetailSlack::kTight; coordinate < RetailScreen::kWidth + RetailSlack::kTight; ++coordinate) {
    ++g_windows;
    if (wide.inside(coordinate, 0, RetailSlack::kTight, RetailSlack::kTight) !=
        retail.inside(coordinate, 0, RetailSlack::kTight, RetailSlack::kTight)) {
      ++g_differences;
      std::fprintf(stderr, "FAIL parity x=%d\n", coordinate);
      return false;
    }
  }
  return true;
}

// Bare Game with hand-written RAM; the cull owner reads only guest memory. Game owns a 2 MB array, so it is
// heap-allocated.
struct Fixture {
  std::unique_ptr<Game> game;
  Core *core;

  Fixture() : game(std::make_unique<Game>()), core(&game->core) {}

  // Identity pattern so an offset error reads a wrong but plausible byte.
  void plantObject(std::uint32_t object, std::uint32_t size) {
    for (std::uint32_t i = 0; i < size; ++i) {
      core->mem_w8(object + i, static_cast<std::uint8_t>(0xA0u + i));
    }
  }
  // xField is the measured x-integer offset; y is +4 (0x0A -> 0x0E) in both layouts.
  void setScreenPosition(std::uint32_t object, std::uint32_t xField, int x, int y) {
    core->mem_w16(object + xField, static_cast<std::uint16_t>(x));
    core->mem_w16(object + xField + 4u, static_cast<std::uint16_t>(y));
  }
  void setScroll(int layer, int x, int y) {
    const std::uint32_t base = kCameraLayersAddress + static_cast<std::uint32_t>(layer) * kCameraLayerStride;
    core->mem_w16(base + kCameraScrollX, static_cast<std::uint16_t>(x));
    core->mem_w16(base + kCameraScrollY, static_cast<std::uint16_t>(y));
  }
};

constexpr std::uint32_t kObject = 0x80100000u;
constexpr std::uint32_t kQuad = 0x80101000u;

// 3. Background-relative recovery: both layouts and polarities, including a case where the wrong offset flips the
// answer.
bool verify_background_relative_recovery(Fixture &f) {
  const VisibilityCull retail{retailPlan()};
  f.plantObject(kObject, 0x40u);
  f.plantObject(kQuad, 0x60u);

  // Screen space: a negative background byte means no scroll is subtracted.
  f.core->mem_w8(kObject + 0x14u, 0xFFu);
  f.setScroll(0, 1000, 1000);
  f.setScreenPosition(kObject, 0x0Au, 160, 120);
  CHECK(retail.screenX(*f.core, kObject, ObjectLayout::BaseObject, BackgroundSource::ObjectByte).value == 160);
  CHECK(retail.screenY(*f.core, kObject, ObjectLayout::BaseObject, BackgroundSource::ObjectByte).value == 120);

  // Layer 1's scroll is subtracted; the layer index comes from the byte (84 = 0x54 stride).
  f.core->mem_w8(kObject + 0x14u, 1);
  f.setScroll(0, 11, 12);
  f.setScroll(1, 100, 200);
  f.setScroll(2, 300, 400);
  f.setScreenPosition(kObject, 0x0Au, 260, 320);
  CHECK(retail.screenX(*f.core, kObject, ObjectLayout::BaseObject, BackgroundSource::ObjectByte).value == 160);
  CHECK(retail.screenY(*f.core, kObject, ObjectLayout::BaseObject, BackgroundSource::ObjectByte).value == 120);

  // The QuadObj byte is at +0x37, not +0x14; plant opposite values at both.
  f.core->mem_w8(kQuad + 0x14u, 2);
  f.core->mem_w8(kQuad + 0x37u, 1);
  f.setScreenPosition(kQuad, 0x0Au, 260, 320);
  CHECK(retail.screenX(*f.core, kQuad, ObjectLayout::QuadObject, BackgroundSource::ObjectByte).value == 160);
  CHECK(retail.screenY(*f.core, kQuad, ObjectLayout::QuadObject, BackgroundSource::ObjectByte).value == 120);
  // And the BaseObj reading of the same bytes must still use +0x14, i.e. layer 2 -> 300/400 -> -40/-80.
  CHECK(retail.screenX(*f.core, kQuad, ObjectLayout::BaseObject, BackgroundSource::ObjectByte).value == -40);
  CHECK(retail.screenY(*f.core, kQuad, ObjectLayout::BaseObject, BackgroundSource::ObjectByte).value == -80);

  // The LayerZero source ignores the byte entirely, which is what 0x800B8490 does.
  CHECK(retail.screenX(*f.core, kQuad, ObjectLayout::BaseObject, BackgroundSource::LayerZero).value == 260 - 11);
  CHECK(retail.screenY(*f.core, kQuad, ObjectLayout::BaseObject, BackgroundSource::LayerZero).value == 320 - 12);

  // The guest `lhu`s both terms, so its register holds a zero-extended value (0x0000FFFB for -5) and `subu` gives
  // 65431, not -205; `raw` catches a sign-extending transcription.
  f.core->mem_w8(kObject + 0x14u, 1);
  f.setScreenPosition(kObject, 0x0Au, -5, -7);
  const ScreenCoordinate x = retail.screenX(*f.core, kObject, ObjectLayout::BaseObject, BackgroundSource::ObjectByte);
  CHECK(x.raw == 0xFFFBu - 100u); // -5 as u16 is 0xFFFB, not 0xFFFF
  CHECK(x.value == -105);
  // Far negative end: the zero-extended raw is 0x00008000 and the subtraction does not wrap.
  f.setScreenPosition(kObject, 0x0Au, -32768, 0);
  const ScreenCoordinate far = retail.screenX(*f.core, kObject, ObjectLayout::BaseObject, BackgroundSource::ObjectByte);
  CHECK(far.raw == 0x8000u - 100u);
  CHECK(far.value == static_cast<std::int16_t>(0x8000u - 100u));
  return true;
}

// Zero-slack quad: four corners OR'd, object position added, scroll subtracted when the byte is set.
bool verify_quad_corners(Fixture &f) {
  const VisibilityCull retail{retailPlan()};
  const VisibilityCull wide{widePlan(54)};
  f.plantObject(kQuad, 0x60u);
  f.core->mem_w8(kQuad + 0x37u, 0xFFu);

  // Corner 0 far outside on the right, corner 3 well inside. Only a four-corner OR admits this.
  f.setScreenPosition(kQuad, 0x0Au, 0, 0);
  f.core->mem_w16(kQuad + kQuadCornerX[0], 900);
  f.core->mem_w16(kQuad + kQuadCornerY[0], 10);
  f.core->mem_w16(kQuad + kQuadCornerX[1], 900);
  f.core->mem_w16(kQuad + kQuadCornerY[1], 10);
  f.core->mem_w16(kQuad + kQuadCornerX[2], 900);
  f.core->mem_w16(kQuad + kQuadCornerY[2], 10);
  f.core->mem_w16(kQuad + kQuadCornerX[3], 100);
  f.core->mem_w16(kQuad + kQuadCornerY[3], 100);
  CHECK(retail.quadOnScreen(*f.core, kQuad));
  CHECK(wide.quadOnScreen(*f.core, kQuad));

  // Every corner outside -> culled, and the same object is admitted at wide because the band moved.
  for (int corner = 0; corner < 4; ++corner) {
    f.core->mem_w16(kQuad + kQuadCornerX[corner], 500);
    f.core->mem_w16(kQuad + kQuadCornerY[corner], 500);
  }
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  CHECK(!wide.quadOnScreen(*f.core, kQuad));

  // Widening with every edge pinned: the band is [0, 320) at 4:3 and [-margin, 320 + margin) wide.
  const int margin = kExpectedMargin;
  for (int corner = 1; corner < 4; ++corner) {
    f.core->mem_w16(kQuad + kQuadCornerX[corner], 500);
    f.core->mem_w16(kQuad + kQuadCornerY[corner], 500);
  }
  f.core->mem_w16(kQuad + kQuadCornerY[0], 100);

  // Just inside the retail right edge: admitted at both widths (the widening must not lose it).
  f.core->mem_w16(kQuad + kQuadCornerX[0], RetailScreen::kWidth - 1);
  CHECK(retail.quadOnScreen(*f.core, kQuad));
  CHECK(wide.quadOnScreen(*f.core, kQuad));
  // Exactly the retail right edge: rejected at 4:3, admitted wide.
  f.core->mem_w16(kQuad + kQuadCornerX[0], RetailScreen::kWidth);
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  CHECK(wide.quadOnScreen(*f.core, kQuad));
  // The widened right edge, one inside and one outside.
  f.core->mem_w16(kQuad + kQuadCornerX[0], RetailScreen::kWidth + margin - 1);
  CHECK(wide.quadOnScreen(*f.core, kQuad));
  f.core->mem_w16(kQuad + kQuadCornerX[0], RetailScreen::kWidth + margin);
  CHECK(!wide.quadOnScreen(*f.core, kQuad));
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  // Left edge: retail has no counterpart; at 4:3 every negative corner is rejected.
  f.core->mem_w16(kQuad + kQuadCornerX[0], -margin);
  CHECK(wide.quadOnScreen(*f.core, kQuad));
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  f.core->mem_w16(kQuad + kQuadCornerX[0], -margin - 1);
  CHECK(!wide.quadOnScreen(*f.core, kQuad));
  // The vertical never moved, even though this is a wide leg: a corner above 240 is still rejected.
  f.core->mem_w16(kQuad + kQuadCornerX[0], 100);
  f.core->mem_w16(kQuad + kQuadCornerY[0], RetailScreen::kHeight);
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  CHECK(!wide.quadOnScreen(*f.core, kQuad));
  f.core->mem_w16(kQuad + kQuadCornerY[0], RetailScreen::kHeight - 1);
  CHECK(retail.quadOnScreen(*f.core, kQuad));
  CHECK(wide.quadOnScreen(*f.core, kQuad));

  // Background-relative quad: only corner 0 is inside, isolating the scroll from the OR; scroll x = 100, byte SET.
  f.setScroll(0, 100, 0);
  f.setScreenPosition(kQuad, 0x0Au, 0, 0);
  for (int corner = 1; corner < 4; ++corner) {
    f.core->mem_w16(kQuad + kQuadCornerX[corner], 500);
    f.core->mem_w16(kQuad + kQuadCornerY[corner], 500);
  }
  f.core->mem_w16(kQuad + kQuadCornerY[0], 100);

  // Byte 0 means layer 0, not screen space; only a negative byte is screen space.
  f.core->mem_w8(kQuad + 0x37u, 0);
  f.core->mem_w16(kQuad + kQuadCornerX[0], 500);
  CHECK(!retail.quadOnScreen(*f.core, kQuad)); // 500 - 100 = 400, outside
  f.core->mem_w16(kQuad + kQuadCornerX[0], 420);
  CHECK(!retail.quadOnScreen(*f.core, kQuad)); // 420 - 100 = 320, and 320 is not < 320
  f.core->mem_w16(kQuad + kQuadCornerX[0], 419);
  CHECK(retail.quadOnScreen(*f.core, kQuad)); // 419 - 100 = 319, the last inside column

  // Negative: a negative byte is screen space, so the extent that mapped to 319 now sits at 420, outside.
  f.core->mem_w8(kQuad + 0x37u, 0xFFu);
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  f.core->mem_w16(kQuad + kQuadCornerX[0], 100);
  CHECK(retail.quadOnScreen(*f.core, kQuad));

  // Body arithmetic: `lhu` extent and position, `addu` in 32 bits, `subu` scroll, then `andi 0xFFFF`.
  // Extent 0xFFFF at position 2 is 1; read as signed it would be -1 and rejected.
  f.setScreenPosition(kQuad, 0x0Au, 2, 0);
  f.core->mem_w16(kQuad + kQuadCornerX[0], 0xFFFFu);
  CHECK(retail.quadOnScreen(*f.core, kQuad)); // (0xFFFF + 2) & 0xFFFF == 1, inside [0, 320)
  // 0xFFFE + 2 == 0x10000 masks to 0, inside.
  f.core->mem_w16(kQuad + kQuadCornerX[0], 0xFFFEu);
  CHECK(retail.quadOnScreen(*f.core, kQuad));
  // 0x8000 is outside either way; pins that neither reading is clamped.
  f.core->mem_w16(kQuad + kQuadCornerX[0], 0x8000u);
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  CHECK(!wide.quadOnScreen(*f.core, kQuad));

  // A position whose own s16 wrap matters: position -2 with extent 4 is 2, and a signed read of the
  // extent 0xFFFC (=-4) would instead give -6, which the band rejects.
  f.setScreenPosition(kQuad, 0x0Au, -2, 0);
  f.core->mem_w16(kQuad + kQuadCornerX[0], 4);
  CHECK(retail.quadOnScreen(*f.core, kQuad));
  f.core->mem_w16(kQuad + kQuadCornerX[0], 0xFFFCu); // -4 unsigned; -4 + -2 = -6 signed, 65530 unmasked
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  return true;
}

// 4. Publication: the byte at +3 for both layouts, including revoke of a pre-set 1 and non-aliasing neighbours.
bool verify_publication(Fixture &f) {
  const int margin = kExpectedMargin;
  const VisibilityCull cull{widePlan(margin)};
  f.plantObject(kObject, 0x40u);
  f.plantObject(kQuad, 0x60u);
  f.core->mem_w8(kObject + 0x14u, 0xFFu);
  f.core->mem_w8(kQuad + 0x37u, 0xFFu);

  // Newly admitted right margin band: inside the wide window, outside retail.
  const int rightBand = RetailScreen::kWidth + RetailSlack::kTight;
  f.setScreenPosition(kObject, 0x0Au, rightBand, 120);
  CHECK(cull.inside(rightBand, 120, RetailSlack::kTight, RetailSlack::kTight));
  f.core->mem_w8(kObject + kOnScreenOffset, 0);
  cull.publishOnScreen(*f.core, kObject, true);
  CHECK(f.core->mem_r8(kObject + kOnScreenOffset) == 1);
  // The neighbours must be untouched: the plant pattern is 0xA2/0xA4, and neither is 0 or 1.
  CHECK(f.core->mem_r8(kObject + 0x02u) == 0xA2);
  CHECK(f.core->mem_r8(kObject + 0x04u) == 0xA4);

  // Revoke: just outside the widened right edge a set flag must be cleared.
  const int outsideRight = RetailScreen::kWidth + RetailSlack::kTight + margin;
  f.setScreenPosition(kObject, 0x0Au, outsideRight, 120);
  CHECK(!cull.inside(outsideRight, 120, RetailSlack::kTight, RetailSlack::kTight));
  cull.publishOnScreen(*f.core, kObject, false);
  CHECK(f.core->mem_r8(kObject + kOnScreenOffset) == 0);

  // QuadObj publishes at its own +3; the objects are 0x1000 apart to show non-aliasing.
  f.setScreenPosition(kQuad, 0x0Au, rightBand, 120);
  cull.publishOnScreen(*f.core, kQuad, true);
  CHECK(f.core->mem_r8(kQuad + kOnScreenOffset) == 1);
  cull.publishOnScreen(*f.core, kObject, false);
  CHECK(f.core->mem_r8(kQuad + kOnScreenOffset) == 1);
  CHECK(f.core->mem_r8(kObject + kOnScreenOffset) == 0);

  // Off screen publishes 0 from a clean state too.
  f.core->mem_w8(kObject + kOnScreenOffset, 1);
  f.setScreenPosition(kObject, 0x0Au, -32768, 120);
  cull.publishOnScreen(*f.core, kObject, false);
  CHECK(f.core->mem_r8(kObject + kOnScreenOffset) == 0);
  return true;
}

} // namespace

int main() {
  Fixture fixture;
  if (!verify_4x3_identity_exhaustive() || !verify_measured_site_table() || !verify_sixteen_bit_parameter_wrap() ||
      !verify_widened_bands(kExpectedMargin) || !verify_wide_requires_the_plan() ||
      !verify_background_relative_recovery(fixture) || !verify_quad_corners(fixture) || !verify_publication(fixture)) {
    return 1;
  }
  std::fprintf(stderr,
               "x4_visibility_cull: %d checks, %d window evaluations, %d differences\n",
               g_checks,
               g_windows,
               g_differences);
  return 0;
}
