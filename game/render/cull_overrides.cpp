// SPDX-License-Identifier: AGPL-3.0-or-later
// Guest leaves that clobber only caller-saved registers, so only $v0 and the site's stores are reproduced.
#include "cull_overrides.h"

#include "core.h"
#include "native_dispatch.h"

#include "x4_context.h"

namespace x4::cull {
namespace {

// Guest argument registers $4-$6 (a0-a2).
constexpr int kArg0 = 4;
constexpr int kArg1 = 5;
constexpr int kArg2 = 6;
// $v0.
constexpr int kReturnValue = 2;

struct Decision {
  bool onScreen;
};

Decision
decide(Core &core, std::uint32_t object, ObjectLayout layout, BackgroundSource source, int halfWidth, int halfHeight) {
  const VisibilityCull cull{context(core).widescreen.plan()};
  const ScreenCoordinate x = cull.screenX(core, object, layout, source);
  const ScreenCoordinate y = cull.screenY(core, object, layout, source);
  return {cull.inside(x.value, y.value, halfWidth, halfHeight)};
}

// Stores 0/1 in on_screen (the byte the draw pass reads) and leaves it in $v0.
void publishFlag(Core &core, std::uint32_t object, const Decision &decision) {
  core.mem_w8(object + kOnScreenOffset, decision.onScreen ? 1u : 0u);
  core.r[kReturnValue] = decision.onScreen ? 1u : 0u;
}

// These sites return 1 when the object is off screen (`xori $2,$2,0x1`).
void publishOffScreenReturn(Core &core, const Decision &decision) {
  core.r[kReturnValue] = decision.onScreen ? 0u : 1u;
}

// 0x8002B288 is_on_screen: slack 32 each side.
void isOnScreenTight(Core *core) {
  const std::uint32_t object = core->r[kArg0];
  publishFlag(*core,
              object,
              decide(*core,
                     object,
                     ObjectLayout::BaseObject,
                     BackgroundSource::ObjectByte,
                     kBaseOnScreenTight.halfWidth,
                     kBaseOnScreenTight.halfHeight));
}

// 0x8002B3C0: widest window, slack 96 horizontal and 80 vertical.
void onScreenWide(Core *core) {
  const std::uint32_t object = core->r[kArg0];
  publishFlag(*core,
              object,
              decide(*core,
                     object,
                     ObjectLayout::BaseObject,
                     BackgroundSource::ObjectByte,
                     kBaseOnScreenWide.halfWidth,
                     kBaseOnScreenWide.halfHeight));
}

// 0x8002B318: a1/a2 are the per-side half-extents.
void onScreenParametric(Core *core) {
  const std::uint32_t object = core->r[kArg0];
  publishFlag(*core,
              object,
              decide(*core,
                     object,
                     ObjectLayout::BaseObject,
                     BackgroundSource::ObjectByte,
                     static_cast<int>(core->r[kArg1]),
                     static_cast<int>(core->r[kArg2])));
}

// 0x8002B1E8: parametric test returning the off-screen flag.
void offScreenParametric(Core *core) {
  const std::uint32_t object = core->r[kArg0];
  publishOffScreenReturn(*core,
                         decide(*core,
                                object,
                                ObjectLayout::BaseObject,
                                BackgroundSource::ObjectByte,
                                static_cast<int>(core->r[kArg1]),
                                static_cast<int>(core->r[kArg2])));
}

// 0x8002B160: fixed 64/64 slack, returns the off-screen flag.
void offScreenLoose(Core *core) {
  const std::uint32_t object = core->r[kArg0];
  publishOffScreenReturn(*core,
                         decide(*core,
                                object,
                                ObjectLayout::BaseObject,
                                BackgroundSource::ObjectByte,
                                kBaseOffScreenLoose.halfWidth,
                                kBaseOffScreenLoose.halfHeight));
}

// 0x800B8490: fixed 64/64; never reads the object background byte, scroll is always camera layer 0.
void offScreenLayerZero(Core *core) {
  const std::uint32_t object = core->r[kArg0];
  publishOffScreenReturn(*core,
                         decide(*core,
                                object,
                                ObjectLayout::BaseObject,
                                BackgroundSource::LayerZero,
                                kBaseOffScreenLayerZero.halfWidth,
                                kBaseOffScreenLayerZero.halfHeight));
}

// 0x800D46F4 quad_is_on_screen: the QuadObj corner extents with no slack; background byte at +0x37.
void quadOnScreen(Core *core) {
  const VisibilityCull cull{context(*core).widescreen.plan()};
  const std::uint32_t object = core->r[kArg0];
  const bool onScreen = cull.quadOnScreen(*core, object);
  cull.publishOnScreen(*core, object, onScreen);
  core->r[kReturnValue] = onScreen ? 1u : 0u;
}

} // namespace

void registerOverrides(Core &core) {
  psx::cpu::installNativeOverride(core, kBaseOnScreenTight.address, "cull::isOnScreenTight", isOnScreenTight);
  psx::cpu::installNativeOverride(core, kBaseOnScreenWide.address, "cull::onScreenWide", onScreenWide);
  psx::cpu::installNativeOverride(
      core, kBaseOnScreenParametric.address, "cull::onScreenParametric", onScreenParametric);
  psx::cpu::installNativeOverride(
      core, kBaseOffScreenParametric.address, "cull::offScreenParametric", offScreenParametric);
  psx::cpu::installNativeOverride(core, kBaseOffScreenLoose.address, "cull::offScreenLoose", offScreenLoose);
  psx::cpu::installNativeOverride(
      core, kBaseOffScreenLayerZero.address, "cull::offScreenLayerZero", offScreenLayerZero);
  psx::cpu::installNativeOverride(core, kQuadOnScreen.address, "cull::quadOnScreen", quadOnScreen);
}

} // namespace x4::cull
