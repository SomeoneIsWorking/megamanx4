// SPDX-License-Identifier: AGPL-3.0-or-later
//
// tests/test_x4_title_layout.cpp — the title's 2D WIDESCREEN LAYOUT contract.
//
// Two things live here, and they are one contract:
//
//   1. `centeredX` translates one authored 16.16 title coordinate by the margin the title-owned
//      projection plan supplies.
//   2. That margin is not a hand-written constant. It is derived, here, from the framework's own pure
//      plan builder fed X4's MEASURED retail geometry (320x240 presentation, 320x240 projection,
//      draw width 320 — tools/verify_projection.py), and then handed to the framework's own pure 2D
//      layout rule `rq_2d_xform`. The previous version of this test injected a hand-typed
//      `GuestProjectionPlan` literal, so a change to `guest_wide_extent_width` or to the plan's margin
//      derivation would not have moved a single assertion here.
//
// The last block is the one that names WHY the title has to own its 2D layout at all
// (docs/issues/0019). X4 ships `RenderCapabilities::widescreenOnly()`, so its Core runs
// `RenderPath::Gte`. `RenderMode::enhancementsAllowed()` is therefore false, and the host-native
// widescreen engine — which is what gates the framework's 2D widening in
// `RenderQueue::emitOrQueue` — can never be true for this title. X4's widening lives in
// `guestDisplay.plan()` instead. This asserts the capability half of that fact from the framework's
// own API, so a future change that made the host-native gate reachable here (Native path, or a
// relaxed `enhancementsAllowed`) would have to confront it instead of silently double-shifting the
// 2D composition.
#include "title_layout.h"

#include "render_capabilities.h"
#include "render_mode.h"
#include "render_queue.h"
#include "wide_2d_layout.h"

#include <cstdio>

namespace {

int gChecks = 0;

#define CHECK(condition)                                                                                               \
  do {                                                                                                                 \
    ++gChecks;                                                                                                         \
    if (!(condition)) {                                                                                                \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition);                                        \
      return 1;                                                                                                        \
    }                                                                                                                  \
  } while (0)

GuestProjectionPlan titlePlan(PresentationAspect aspect, int width, int margin) {
  GuestProjectionPlan plan;
  plan.aspect = aspect;
  plan.nativeExtent = {320, 240};
  plan.presentationExtent = {width, 240};
  plan.presentationHorizontalMargin = margin;
  return plan;
}

// SLUS_005.61's measured geometry, fed to the framework's own plan builder. `sink` is the presented
// picture size the run composes into; it is deliberately the 16:9 sink the product presents, because
// the plan's rounding is a property of the aspect rule and not of the window.
constexpr GuestProjectionGeometry kRetailGeometry{{320, 240}, 320};

GuestProjectionPlan measuredPlan(PresentationAspect requested) {
  return guest_projection_plan({
      .path = RenderPath::Gte,
      .requested = requested,
      .nativePresentation = {320, 240},
      .nativeProjection = kRetailGeometry,
      .sink = {1280, 720},
      .vramWidth = 1024,
  });
}

} // namespace

int main() {
  constexpr std::int32_t kRetailMenuX = 128 << 16;

  CHECK(x4::title_layout::centeredX(kRetailMenuX, titlePlan(PresentationAspect::Standard4x3, 320, 0)) == kRetailMenuX);
  CHECK(x4::title_layout::centeredX(kRetailMenuX, titlePlan(PresentationAspect::Wide16x9, 428, 54)) == (182 << 16));
  CHECK(x4::title_layout::centeredX(kRetailMenuX, titlePlan(PresentationAspect::Wide16x9, 320, 0)) == kRetailMenuX);

  // ---- the plan is DERIVED from X4's measured geometry, not typed in --------------------------------
  const GuestProjectionPlan wide = measuredPlan(PresentationAspect::Wide16x9);
  CHECK(wide.aspect == PresentationAspect::Wide16x9);
  CHECK(wide.nativeExtent.width == 320 && wide.nativeExtent.height == 240);
  CHECK(wide.presentationExtent.width == 428 && wide.presentationExtent.height == 240);
  CHECK(wide.projectionExtent.width == 428 && wide.projectionExtent.height == 240);
  CHECK(wide.nativeGuestDrawWidth == 320 && wide.guestDrawWidth == 428);
  CHECK(wide.presentationHorizontalMargin == 54);
  CHECK(wide.projectionHorizontalMargin == 54);
  CHECK(wide.projectionCenterX == 214);
  CHECK(wide.projectionClipRight == 427 && wide.guestClipRight == 427);
  CHECK(wide.widescreen());

  const GuestProjectionPlan narrow = measuredPlan(PresentationAspect::Standard4x3);
  CHECK(narrow.presentationExtent.width == 320 && narrow.guestDrawWidth == 320);
  CHECK(narrow.presentationHorizontalMargin == 0);
  CHECK(narrow.projectionCenterX == 160);
  CHECK(narrow.projectionClipRight == 319 && narrow.guestClipRight == 319);
  CHECK(!narrow.widescreen());

  // X4's own title coordinate goes through the DERIVED plan, not a literal: 128 -> 182.
  CHECK(x4::title_layout::centeredX(kRetailMenuX, wide) == (182 << 16));
  CHECK(x4::title_layout::centeredX(kRetailMenuX, narrow) == kRetailMenuX);

  // ---- the framework's 2D layout rule applied to those same plan facts -----------------------------
  // This is the number issue #19 is missing. The title's fixed-screen 2D is authored 4:3, so the
  // framework's own rule centres it by the plan's presentation margin: guest x 0 -> 54, and the
  // authored right edge 319 -> 373, which is exactly the 4:3 composition centred in the 428 canvas.
  const int presented = wide.presentationExtent.width;
  const int native = wide.nativeExtent.width;
  const Rq2dXform authoredHud =
      rq_2d_xform(presented, native, RQ_2D_AUTHORED_4_3, RQ_HUD, /*flat=*/false, /*untextured=*/false);
  CHECK(!authoredHud.stretch);
  CHECK(authoredHud.apply(0) == 54);
  CHECK(authoredHud.apply(160) == 214); // the authored centre lands on the projection centre
  CHECK(authoredHud.apply(319) == 373);
  // At 4:3 the same rule is the identity, on every layer and material: 4:3 identity is a contract,
  // not a side effect of the wide path being right.
  for (int layer = 0; layer < RQ_LAYER_COUNT; ++layer) {
    for (int flat = 0; flat < 2; ++flat) {
      for (int untextured = 0; untextured < 2; ++untextured) {
        const Rq2dXform identity = rq_2d_xform(320, 320, RQ_2D_AUTHORED_4_3, layer, flat, untextured);
        CHECK(identity.apply(0) == 0);
        CHECK(identity.apply(319) == 319);
        CHECK(!identity.stretch);
      }
    }
  }
  // The two 2D CLASSES the census has to keep apart, from the same rule: a uniform untextured
  // background fills the whole canvas, and everything else CENTRES. A blanket translation is
  // therefore wrong for the background class, which is why issue #19 refuses a renderer-wide offset.
  const Rq2dXform fillBackground =
      rq_2d_xform(presented, native, RQ_2D_AUTHORED_4_3, RQ_BACKGROUND, /*flat=*/true, /*untextured=*/true);
  CHECK(fillBackground.stretch);
  CHECK(fillBackground.apply(0) == 0);
  CHECK(fillBackground.apply(320) == 428);
  const Rq2dXform texturedBackground =
      rq_2d_xform(presented, native, RQ_2D_AUTHORED_4_3, RQ_BACKGROUND, /*flat=*/true, /*untextured=*/false);
  CHECK(!texturedBackground.stretch);
  CHECK(texturedBackground.apply(320) == 374); // centred, not stretched: 320 + 54

  // ---- WHY the title has to own this at all, AND WHY IT NOW DOES --------------------------------
  // The host-native widescreen engine is `Mods::aspect != 4:3 && RenderMode::enhancementsAllowed()`
  // (runtime/psx/gpu_vk.cpp), and X4 ships the widescreen-only profile, so its Core is Gte and that
  // conjunction is FALSE for every frame of this product. `RenderQueue::emitOrQueue` used to gate the
  // 2D widening above on exactly that, so the rule never ran here: the composition sat at host x=0
  // while 4:3 content began at x=164, a 164-pixel shift over a 635/635-2D frame. That is issue #19,
  // and the gate is what made it unreachable rather than merely unfixed.
  //
  // The framework now asks about BOTH widening mechanisms (psxport runtime/psx/wide_2d_layout.h): the
  // host PC engine, and the title-owned `GuestWidescreenProjection` that a Gte-path title uses. So the
  // rule is reachable for X4, and these are the framework's own numbers for X4's own plan — asserted
  // rather than restated, so a regression that made the guest mechanism invisible again would fail
  // here instead of in a picture.
  RenderMode mode;
  mode.setPath(RenderCapabilities::widescreenOnly().defaultPath);
  CHECK(mode.path() == RenderPath::Gte);
  CHECK(!mode.enhancementsAllowed());
  CHECK(mode.guestWidescreenAllowed());
  {
    // X4's Core: the host engine is NOT engaged, the guest projection is, at 320 -> 428.
    const Wide2dExtent extent = wide_2d_extent(/*host_wide=*/0,
                                               /*host_engaged=*/false,
                                               /*guest_wide=*/presented,
                                               /*guest_engaged=*/true,
                                               native);
    CHECK(extent.wide == 428);
    CHECK(extent.native == 320);
    CHECK(wide_2d_layout_active_for(/*host_wide=*/0,
                                    /*host_engaged=*/false,
                                    /*guest_wide=*/presented,
                                    /*guest_engaged=*/true,
                                    native));
    // The layout the framework will therefore apply to X4's authored 4:3 2D, which is the number
    // issue #19 was missing and the one its frame-800 capture predicted (162 host px at 1284/428,
    // against 164 measured).
    const Rq2dXform fixed = rq_2d_xform(extent.wide,
                                        extent.native,
                                        RQ_2D_AUTHORED_4_3,
                                        RQ_HUD,
                                        /*flat=*/false,
                                        /*untextured=*/false);
    CHECK(!fixed.stretch);
    CHECK(fixed.apply(0) == 54);
    CHECK(fixed.apply(160) == 214);
    // At 4:3 the same decision is not active, so the identity is the answer on every layer.
    CHECK(!wide_2d_layout_active_for(/*host_wide=*/0,
                                     /*host_engaged=*/false,
                                     /*guest_wide=*/320,
                                     /*guest_engaged=*/true,
                                     320));
  }

  std::fprintf(stderr, "x4_title_layout: %d checks passed\n", gChecks);
  return 0;
}
