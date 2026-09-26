// test_x4_visibility_cull.cpp — hermetic gate for the RE cull census's native owner
// (game/core/visibility_cull.{h,cpp}).
//
// THE CONTRACT THIS FILE EXISTS TO PIN, in order of how much it is worth:
//
//   1. IDENTITY AT 4:3. The owner's `ScreenWindow` must reproduce the guest's three-instruction
//      compare bit for bit. This is checked EXHAUSTIVELY over all 65,536 coordinate values for
//      every recovered window shape, against a model transcribed straight from the disassembly,
//      not against a sample. A 4:3 frame that differs from retail in one pixel of culling is a
//      regression in a title whose whole value is being faithful, so this is the load-bearing test.
//
//   2. THE WIDENING IS REAL AND BOUNDED. At the plan's own margin the same window must admit
//      exactly the two new margin bands, must still reject the positions just outside each edge,
//      and must NOT admit the corners retail rejected for a different reason (a negative coordinate
//      still wraps to a large unsigned value and still fails).
//
//   3. THE BACKGROUND-RELATIVE RECOVERY IS THE RIGHT ONE. bg_offset >= 0 must subtract the named
//      camera layer's scroll; a negative byte must not. And BaseObj's byte is at +0x14 while
//      QuadObj's is at +0x37 — a shared offset reads the wrong byte for one of them, so the two
//      layouts are pinned apart, including a case where using the wrong offset flips the answer.
//
//   4. THE ADAPTERS PUBLISH WHAT THE DRAW PASS READS. The on_screen byte, at +3 for both layouts.
//
// NEGATIVE COVERAGE. Every class has at least one case that must fail for the right reason, and the
// mutations that make each class fire are listed at the end of this header's companion report:
//   - an identity model with the unsigned compare replaced by a signed one,
//   - a window that forgets the plan margin (the exact defect being fixed),
//   - a QuadObj layout that reuses BaseObj's +0x14,
//   - a background path that ignores bg_offset,
//   - a quad corner loop that stops after the first corner.
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

// The plan the widening reads. `presentationHorizontalMargin` is the only term this owner consumes,
// and it is the framework's own 2D layout shift, so a hand-built plan is a faithful stand-in: at
// margin 0 it is the 4:3 identity and the test does not need a Core, a disc or a frame.
//
// The margin value used for the wide legs is NOT chosen here. It is the plan's own term, and the test
// derives the expected band from it, so the assertions hold for whatever margin the framework
// latches; `kExpectedMargin` is only the concrete instance this gate exercises (the 320 -> 428
// widening of tools/verify_projection.py, whose margin is (428 - 320) / 2).
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

// THE RETAIL COMPARISON, transcribed from the disassembly and nothing else:
//
//   addiu  t, v, A          @ 0x8002B2E8  (and @ 0x8002B1BC, 0x8002B420, 0x800B84B0, ...)
//   andi   t, t, 0xFFFF      @ 0x8002B2EC
//   sltiu  c, t, B          @ 0x8002B2F0   ->  (u32)((u16)(v + A)) <u  B
//
// The `sltu` form at 0x8002B38C is the same predicate with the bound in a register. Both are the same
// function of (A, B), which is why one model covers every site.
bool retailWindow(int value, int addend, int bound) {
  const unsigned int shifted = static_cast<unsigned int>(static_cast<int>(static_cast<short>(value)) +
                                                         static_cast<int>(static_cast<short>(addend)));
  return static_cast<unsigned short>(shifted) < static_cast<unsigned short>(bound);
}

// Every recovered window shape: the site's per-side slack, and the retail `addiu`/`sltiu` immediates
// the disassembly carries for it. `expectedAddend` and `expectedBound` are the retail immediates, so
// this table is a transcription of the image, not of the owner.
struct Shape {
  const char *name;
  int halfX;
  int halfY;
  int retailAddendX;
  int retailBoundX;
  int retailAddendY;
  int retailBoundY;
};

// One row per measured window shape. `halfX`/`halfY` are the site's recovered per-side slack, and the
// four immediates are the retail `addiu` and `sltiu` operands the disassembly carries for it. This
// table is a transcription of the IMAGE, not of the owner, which is what makes the identity sweep
// below a comparison against the binary rather than a restatement of the code under test.
constexpr Shape kShapes[] = {
    // is_on_screen 0x8002B288: addiu 0x20 / sltiu 0x180, addiu 0x20 / sltiu 0x130
    {"is_on_screen tight", RetailSlack::kTight, RetailSlack::kTight, 0x20, 0x180, 0x20, 0x130},
    // func_8002B3C0 0x8002B3C0: addiu 0x60 / sltiu 0x200, addiu 0x50 / sltiu 0x190 — ASYMMETRIC slack,
    // 96 horizontally and 80 vertically, which is why the two are separate constants.
    {"on_screen wide", RetailSlack::kWideX, RetailSlack::kWideY, 0x60, 0x200, 0x50, 0x190},
    // func_8002B160 0x8002B160 and 0x800B8490: addiu 0x40 / sltiu 0x1C0, addiu 0x40 / sltiu 0x170
    {"off_screen loose", RetailSlack::kLoose, RetailSlack::kLoose, 0x40, 0x1C0, 0x40, 0x170},
    // quad_is_on_screen 0x800D46F4: no addend at all, sltiu 0x140 / sltiu 0x0F0
    {"quad corner", 0, 0, 0x00, 0x140, 0x00, 0x0F0},
    // func_8002B318 / 0x8002B1E8 pass the half-extent in $5/$6, so the bound is a REGISTER there. The
    // decomp's own call sites pass 0x20/0x20 (visual_objs.c:26), 0x80/0x30 (select_a_character.c:332)
    // and 0xA0/0xA0 (395D0.c:3634); the row below is the 0x20/0x20 instance, so its bound is the
    // register form 2*0x20 + 320 and 2*0x20 + 240.
    {"parametric 0x20/0x20", 0x20, 0x20, 0x20, 0x40 + 0x140, 0x20, 0x40 + 0xF0},
    // And one asymmetric parametric instance, 0x80/0x30, which is the measured reason the horizontal
    // and vertical slacks cannot be one number.
    {"parametric 0x80/0x30", 0x80, 0x30, 0x80, 0x100 + 0x140, 0x30, 0x60 + 0xF0},
};

// 1. IDENTITY AT 4:3, exhaustively. Also proves the owner and the disassembly agree on where each
// window's edges are, because a wrong bound shifts the band by a pixel somewhere in the sweep.
bool verify_4x3_identity_exhaustive() {
  // One sweep covers both axes. A 4:3 identity that only checked x would not notice a vertical change,
  // and the widening must not have touched the vertical at all.
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

// The same sweep at the plan's own margin. The retail model is NOT reused: the widened decision is
// compared against the box derived from the widened frame, which is the property the fix claims.
//
// WHY THAT BOX. The draw path shifts an authored guest x by +margin (rq_2d_xform / title_layout), so
// a guest coordinate reaches the wide frame at x + margin, and the wide frame spans
// [0, 320 + 2*margin). A guest coordinate can therefore land inside the frame over [-margin,
// 320 + margin), and the site's own recovered slack keeps `half` pixels beyond that on each side.
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
    // The 16-bit masking must still wrap. A coordinate far below the band sums to a large unsigned
    // value and is rejected; a "widening" that dropped the mask, or that compared signed, would admit
    // the whole left half of the level.
    CHECK(!cull.inside(-32768, 0, shape.halfX, shape.halfY));
    CHECK(!cull.inside(-32768 + shape.halfX + margin, 0, shape.halfX, shape.halfY));
    // The vertical is untouched: its band is still [-halfY, 240 + halfY) whatever the margin is, so
    // every one of these is the RETAIL edge and none of them moved.
    CHECK(cull.inside(0, -shape.halfY, shape.halfX, shape.halfY));
    CHECK(cull.inside(0, RetailScreen::kHeight + shape.halfY - 1, shape.halfX, shape.halfY));
    CHECK(!cull.inside(0, -shape.halfY - 1, shape.halfX, shape.halfY));
    CHECK(!cull.inside(0, RetailScreen::kHeight + shape.halfY, shape.halfX, shape.halfY));
    // Exhaustive agreement with the widened box, so a 4:3-only sweep could not hide a wide-only bug.
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

// 1b. THE MEASURED SITE TABLE. The identity sweep above proves the ARITHMETIC is the guest's, given a
// slack. This class proves each measured site is bound to the slack its own disassembly carries, which
// is a different claim: a table that gave 0x8002B3C0 the 32/32 slack would pass every sweep above and
// still cull wrongly. Each row is checked against the retail immediates transcribed in kShapes, and the
// two parametric rows are checked for being marked as such rather than pinned to a number.
bool verify_measured_site_table() {
  // Seven sites, no duplicate addresses, every address inside the executable's own text section.
  for (std::size_t i = 0; i < std::size(kMeasuredSites); ++i) {
    const MeasuredSite &site = kMeasuredSites[i];
    for (std::size_t j = 0; j < i; ++j) {
      CHECK(kMeasuredSites[j].address != site.address);
    }
    CHECK(site.address >= 0x80010000u && site.address < 0x80130000u);
  }
  // The addresses are the measured ones, in the executable's own text section.
  CHECK(kBaseOnScreenTight.address == 0x8002B288u);
  CHECK(kBaseOnScreenParametric.address == 0x8002B318u);
  CHECK(kBaseOnScreenWide.address == 0x8002B3C0u);
  CHECK(kBaseOffScreenParametric.address == 0x8002B1E8u);
  CHECK(kBaseOffScreenLoose.address == 0x8002B160u);
  CHECK(kBaseOffScreenLayerZero.address == 0x800B8490u);
  CHECK(kQuadOnScreen.address == 0x800D46F4u);

  // A site's slack must be one the exhaustive sweep actually covered, or the row is untested. The
  // parametric rows carry -1 and are exempt, because their slack arrives in a register at run time.
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
  // The asymmetric row is the one that would break if the two slacks were collapsed: its own
  // immediates are 0x60/0x200 horizontally and 0x50/0x190 vertically, which is 96/80 and NOT 96/96.
  CHECK(kBaseOnScreenWide.halfWidth == 0x60);
  CHECK(kBaseOnScreenWide.halfHeight == 0x50);
  CHECK(kBaseOnScreenWide.halfWidth != kBaseOnScreenWide.halfHeight);
  // The layer-0 row is the only one that ignores the object's background byte, and the zero-slack row
  // is the only publishing one with no slack at all.
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

// 1c. WHERE THE 16-BIT MASK IS ACTUALLY OBSERVABLE. `contains` masks to sixteen bits on both operands
// because the guest does (`andi $2,$2,0xFFFF` before `sltiu`). For every value the owner feeds it the
// caller has already truncated to s16, so that mask is a SECOND truncation and dropping it would change
// nothing — a property worth pinning rather than leaving to chance, and the reason the mutation harness
// reports a 32-bit compare as equivalent. The mask earns its keep when a PARAMETER overflows sixteen
// bits: the two parametric sites take their half-extent in a guest register and $5 is a plain int, so a
// caller can pass 40000.
//
// AND THE WINDOW IS NOT A BOX THERE. With A = 40000 the bound 2*40000 + 320 = 80320 has low sixteen bits
// 14784, so the predicate is `(u16)(v + 40000) <u 14784`, which on the 16-bit circle is the arc
// [-40000, -25216) union [25536, 40320) — two pieces, and 0 is OUTSIDE it. The "[-A, B-A)" box reading
// in the header is exact only while the bound fits in fifteen bits, which every real site does; this
// class pins the wrap form itself so the header's convenience is never mistaken for the rule.
bool verify_sixteen_bit_parameter_wrap() {
  const int huge = 40000;
  const int bound = 2 * huge + RetailScreen::kWidth;
  const ScreenWindow window = ScreenWindow::horizontal(huge, 0);
  CHECK(window.offset() == huge);
  CHECK(bound > 0xFFFF);
  CHECK(static_cast<int>(static_cast<std::uint16_t>(bound)) == 14784);
  // The measured arcs, edge by edge, in both directions.
  CHECK(window.contains(-40000));
  CHECK(!window.contains(-25216));
  CHECK(window.contains(-25217));
  CHECK(!window.contains(25535));
  CHECK(window.contains(25536));
  CHECK(!window.contains(40320));
  CHECK(window.contains(40319));
  // And 0 is outside, which a box reading of [-A, B-A) would have got wrong.
  CHECK(!window.contains(0));
  // A NEGATIVE half-extent — $5 is a plain int, so a caller can pass one — must behave as the retail
  // arithmetic does rather than as a sanity-checked input.
  const ScreenWindow negative = ScreenWindow::horizontal(-100, 0);
  CHECK(negative.offset() == -100);
  CHECK(negative.bound() == -200 + RetailScreen::kWidth);
  CHECK(negative.contains(0) == retailWindow(0, -100, 120));
  // Exhaustive identity for the overflowing parameter too, on the same transcribed model, so the two
  // pieces of the arc above are a sample of a proven match rather than the whole claim.
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

// A NEGATIVE control for the widened class itself: with the margin dropped, the widened edges must
// stop being admitted. This is the exact defect being fixed, asserted as a failing case so the class
// above is known to be load-bearing rather than vacuously true.
bool verify_wide_requires_the_plan() {
  const int margin = kExpectedMargin;
  const VisibilityCull retail{retailPlan()};
  const VisibilityCull wide{widePlan(margin)};
  CHECK(retail.horizontalMargin() == 0);
  CHECK(wide.horizontalMargin() == margin);
  // The is_on_screen band is [-32, 352) at 4:3 and [-(32+margin), 320+32+margin) at wide. So a guest
  // coordinate inside the new right margin band, and one inside the new left margin band, must both
  // flip from culled to admitted when — and only when — the plan carries the margin. These are the
  // two cases the defect was about: both are drawn inside the wide frame and both were discarded.
  const int rightBand = RetailScreen::kWidth + RetailSlack::kTight;
  const int leftBand = -RetailSlack::kTight - 1;
  CHECK(!retail.inside(rightBand, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(wide.inside(rightBand, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(!retail.inside(leftBand, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(wide.inside(leftBand, 0, RetailSlack::kTight, RetailSlack::kTight));
  // And the far edge of the new band, so a one-sided widening that moved only one edge fails.
  CHECK(!retail.inside(rightBand + margin - 1, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(wide.inside(rightBand + margin - 1, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(!retail.inside(-RetailSlack::kTight - margin, 0, RetailSlack::kTight, RetailSlack::kTight));
  CHECK(wide.inside(-RetailSlack::kTight - margin, 0, RetailSlack::kTight, RetailSlack::kTight));
  // A plan that went narrower than native must clamp to 0 rather than invert the window.
  GuestProjectionPlan inverted = retailPlan();
  inverted.presentationHorizontalMargin = -40;
  CHECK(VisibilityCull{inverted}.horizontalMargin() == 0);
  CHECK(VisibilityCull{inverted}.inside(0, 0, RetailSlack::kTight, RetailSlack::kTight));
  // The parity cost of the identity: the widened owner must agree with the retail owner on every
  // coordinate the retail band already covered, or it would be changing 4:3-visible geometry.
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

// A bare Game with hand-written RAM: no disc, no window, no guest execution. The cull owner reads
// only guest memory, so the whole predicate is exercisable without a frame. Game owns a 2 MB RAM
// array, so it is heap-allocated rather than placed in the test's stack frame.
struct Fixture {
  std::unique_ptr<Game> game;
  Core *core;

  Fixture() : game(std::make_unique<Game>()), core(&game->core) {}

  // Plant an object with an identity pattern first, so an offset error reads a wrong-but-plausible
  // byte instead of a zero that would accidentally be right.
  void plantObject(std::uint32_t object, std::uint32_t size) {
    for (std::uint32_t i = 0; i < size; ++i) {
      core->mem_w8(object + i, static_cast<std::uint8_t>(0xA0u + i));
    }
  }
  // `xField` is the measured x-integer offset; the y-integer offset is the same field plus 4 (0x0A ->
  // 0x0E) in both measured layouts.
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

// 3. THE BACKGROUND-RELATIVE RECOVERY. Both layouts, both polarities of the background byte, and a
// case where reading the wrong offset flips the answer.
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

  // Background-relative: layer 1's scroll is the one that must be subtracted, and the layer INDEX
  // must come from the byte. 84 = 0x54 stride, so a wrong stride lands on the wrong layer.
  f.core->mem_w8(kObject + 0x14u, 1);
  f.setScroll(0, 11, 12);
  f.setScroll(1, 100, 200);
  f.setScroll(2, 300, 400);
  f.setScreenPosition(kObject, 0x0Au, 260, 320);
  CHECK(retail.screenX(*f.core, kObject, ObjectLayout::BaseObject, BackgroundSource::ObjectByte).value == 160);
  CHECK(retail.screenY(*f.core, kObject, ObjectLayout::BaseObject, BackgroundSource::ObjectByte).value == 120);

  // The QuadObj byte is at +0x37, NOT +0x14. Plant opposite values at both offsets so an owner that
  // reuses BaseObj's offset reads a different layer and lands on a different scroll.
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

  // The s16/u16 edge, stated exactly. The guest LOADS both terms with `lhu`, so its 32-bit register
  // holds a ZERO-extended 16-bit value (0x0000FFFB for a position of -5) and its `subu` computes
  // 0x0000FFFB - 100 = 65431, NOT the sign-extended -5 - 100 = -205. The two differ, and the window
  // only ever reads the low sixteen bits, so `value` would be -105 under either reading — which is
  // exactly why `raw` is the field that catches a sign-extending transcription of the load.
  f.core->mem_w8(kObject + 0x14u, 1);
  f.setScreenPosition(kObject, 0x0Au, -5, -7);
  const ScreenCoordinate x = retail.screenX(*f.core, kObject, ObjectLayout::BaseObject, BackgroundSource::ObjectByte);
  CHECK(x.raw == 0xFFFBu - 100u); // -5 as u16 is 0xFFFB, not 0xFFFF
  CHECK(x.value == -105);
  // The far negative end: the zero-extended load makes the raw register 0x00008000 and the subtraction
  // does not wrap, where a sign-extended load would have wrapped.
  f.setScreenPosition(kObject, 0x0Au, -32768, 0);
  const ScreenCoordinate far = retail.screenX(*f.core, kObject, ObjectLayout::BaseObject, BackgroundSource::ObjectByte);
  CHECK(far.raw == 0x8000u - 100u);
  CHECK(far.value == static_cast<std::int16_t>(0x8000u - 100u));
  return true;
}

// The zero-slack quad: four corners, OR'd, with the object position added to each extent and the
// background scroll subtracted when the byte is set. A loop that stopped after the first corner would
// cull a quad whose first corner is outside and whose fourth is inside; the plant below is that case.
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

  // The widening, with every band edge pinned. The zero-slack quad band is [0, 320) at 4:3 and
  // [-margin, 320 + margin) at wide, so each of the four edges below moves and each is checked on
  // both sides: a widening that moved only the right edge, or that widened the box to the full frame
  // width [0, 428) in guest coordinates, would fail one of them.
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
  // Exactly the retail right edge: rejected at 4:3, admitted at wide. This is a newly-admitted object.
  f.core->mem_w16(kQuad + kQuadCornerX[0], RetailScreen::kWidth);
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  CHECK(wide.quadOnScreen(*f.core, kQuad));
  // The widened right edge, one inside and one outside.
  f.core->mem_w16(kQuad + kQuadCornerX[0], RetailScreen::kWidth + margin - 1);
  CHECK(wide.quadOnScreen(*f.core, kQuad));
  f.core->mem_w16(kQuad + kQuadCornerX[0], RetailScreen::kWidth + margin);
  CHECK(!wide.quadOnScreen(*f.core, kQuad));
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  // The widened LEFT edge, which retail has no counterpart for at all: the quad corners carry no
  // slack, so at 4:3 the band starts at 0 and every negative corner was rejected.
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

  // The background-relative quad: the scroll must be subtracted from the corner sums, and the byte
  // selects whether it is. Corner 0 is the only corner inside, so this isolates the scroll recovery
  // from the corner OR. With scroll x = 100 and the byte SET, corner 0's screen x is extent - 100.
  f.setScroll(0, 100, 0);
  f.setScreenPosition(kQuad, 0x0Au, 0, 0);
  for (int corner = 1; corner < 4; ++corner) {
    f.core->mem_w16(kQuad + kQuadCornerX[corner], 500);
    f.core->mem_w16(kQuad + kQuadCornerY[corner], 500);
  }
  f.core->mem_w16(kQuad + kQuadCornerY[0], 100);

  // A background byte of 0 means LAYER 0, not screen space — only a NEGATIVE byte means screen space.
  // So the scroll is subtracted here, and the extent that lands exactly on the retail right edge is
  // the one that fails. The pair pins that edge to the pixel.
  f.core->mem_w8(kQuad + 0x37u, 0);
  f.core->mem_w16(kQuad + kQuadCornerX[0], 500);
  CHECK(!retail.quadOnScreen(*f.core, kQuad)); // 500 - 100 = 400, outside
  f.core->mem_w16(kQuad + kQuadCornerX[0], 420);
  CHECK(!retail.quadOnScreen(*f.core, kQuad)); // 420 - 100 = 320, and 320 is not < 320
  f.core->mem_w16(kQuad + kQuadCornerX[0], 419);
  CHECK(retail.quadOnScreen(*f.core, kQuad)); // 419 - 100 = 319, the last inside column

  // NEGATIVE, and this is the pair that makes the three rows above load-bearing: a negative byte means
  // screen space, so the same extent that mapped to 319 now sits at 420 and is outside. An owner that
  // treated byte 0 as screen space, or that subtracted the scroll regardless of the byte, cannot
  // produce all three answers.
  f.core->mem_w8(kQuad + 0x37u, 0xFFu);
  CHECK(!retail.quadOnScreen(*f.core, kQuad));
  f.core->mem_w16(kQuad + kQuadCornerX[0], 100);
  CHECK(retail.quadOnScreen(*f.core, kQuad));

  // The u16 extent and s16 position edges, in the arithmetic the body actually uses: it `lhu`s each
  // extent and each position, `addu`s them in 32 bits, `subu`s the scroll, and only then `andi 0xFFFF`
  // before the compare. So an extent of 0xFFFF at position 2 is 1, not 65537 and not -1 — and 0xFFFF
  // read as a SIGNED halfword would be -1, which the band rejects. This is the case that separates
  // the two.
  f.setScreenPosition(kQuad, 0x0Au, 2, 0);
  f.core->mem_w16(kQuad + kQuadCornerX[0], 0xFFFFu);
  CHECK(retail.quadOnScreen(*f.core, kQuad)); // (0xFFFF + 2) & 0xFFFF == 1, inside [0, 320)
  // 0xFFFE + 2 == 0x10000, which masks to 0: also inside, and unreachable by a signed read (which
  // would give -2 + 2 == 0 by accident, so the two rows together pin the 16-bit wrap).
  f.core->mem_w16(kQuad + kQuadCornerX[0], 0xFFFEu);
  CHECK(retail.quadOnScreen(*f.core, kQuad));
  // 0x8000 is the other discriminating extent: unsigned it is 32768 (way outside), signed it is
  // -32768 (also outside) — so this row pins only that neither reading is silently clamped, and the
  // 0xFFFF/0xFFFE pair above is what pins the u16.
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

// 4. PUBLICATION. The byte the draw pass reads, at +3 for both layouts, including the revoke path (a
// pre-set 1 must be cleared when the object is outside) and the non-aliasing of the neighbours, so a
// write at the wrong offset cannot pass.
bool verify_publication(Fixture &f) {
  const int margin = kExpectedMargin;
  const VisibilityCull cull{widePlan(margin)};
  f.plantObject(kObject, 0x40u);
  f.plantObject(kQuad, 0x60u);
  f.core->mem_w8(kObject + 0x14u, 0xFFu);
  f.core->mem_w8(kQuad + 0x37u, 0xFFu);

  // A coordinate in the newly-admitted right margin band: inside the wide window, outside the retail
  // one. This is the object the defect discarded.
  const int rightBand = RetailScreen::kWidth + RetailSlack::kTight;
  f.setScreenPosition(kObject, 0x0Au, rightBand, 120);
  CHECK(cull.inside(rightBand, 120, RetailSlack::kTight, RetailSlack::kTight));
  f.core->mem_w8(kObject + kOnScreenOffset, 0);
  cull.publishOnScreen(*f.core, kObject, true);
  CHECK(f.core->mem_r8(kObject + kOnScreenOffset) == 1);
  // The neighbours must be untouched: the plant pattern is 0xA2/0xA4, and neither is 0 or 1.
  CHECK(f.core->mem_r8(kObject + 0x02u) == 0xA2);
  CHECK(f.core->mem_r8(kObject + 0x04u) == 0xA4);

  // The revoke path: just outside the widened right edge the flag must be CLEARED even though it was
  // set, because that revoke is the entire reason the byte exists.
  const int outsideRight = RetailScreen::kWidth + RetailSlack::kTight + margin;
  f.setScreenPosition(kObject, 0x0Au, outsideRight, 120);
  CHECK(!cull.inside(outsideRight, 120, RetailSlack::kTight, RetailSlack::kTight));
  cull.publishOnScreen(*f.core, kObject, false);
  CHECK(f.core->mem_r8(kObject + kOnScreenOffset) == 0);

  // The QuadObj publishes at ITS +3, and writing the BaseObj must not reach it. The two objects are
  // 0x1000 apart so the non-aliasing is visible.
  f.setScreenPosition(kQuad, 0x0Au, rightBand, 120);
  cull.publishOnScreen(*f.core, kQuad, true);
  CHECK(f.core->mem_r8(kQuad + kOnScreenOffset) == 1);
  cull.publishOnScreen(*f.core, kObject, false);
  CHECK(f.core->mem_r8(kQuad + kOnScreenOffset) == 1);
  CHECK(f.core->mem_r8(kObject + kOnScreenOffset) == 0);

  // An object that is off screen must publish 0 from a clean state too, not merely clear a 1.
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
