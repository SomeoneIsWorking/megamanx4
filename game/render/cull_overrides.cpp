// SPDX-License-Identifier: AGPL-3.0-or-later
// Guest leaves that clobber only caller-saved registers, so only $v0 and the site's stores are reproduced.
#include "cull_overrides.h"

#include "core.h"
#include "native_dispatch.h"
#include "resumable_guest_call.h"

#include <lucent/log.h>

#include "x4_context.h"

namespace x4::cull {
namespace {

// Guest argument registers $4-$6 (a0-a2).
constexpr int kArg0 = 4;
constexpr int kArg1 = 5;
constexpr int kArg2 = 6;
// $v0.
constexpr int kReturnValue = 2;

// The retail verdict is what gameplay reads; the widened verdict only decides what is drawn.
struct Verdicts {
  bool retail;
  bool widened;
};

Verdicts decide(Core &core, std::uint32_t object, int halfWidth, int halfHeight) {
  const VisibilityCull widened{context(core).widescreen.plan()};
  const VisibilityCull retail = VisibilityCull::retail();
  const ScreenCoordinate x = retail.screenX(core, object, ObjectLayout::BaseObject);
  const ScreenCoordinate y = retail.screenY(core, object, ObjectLayout::BaseObject);
  return {retail.inside(x.value, y.value, halfWidth, halfHeight),
          widened.inside(x.value, y.value, halfWidth, halfHeight)};
}

// Stores the retail 0/1 in on_screen, leaves it in $v0 and remembers an object only the widened box admits.
void publish(Core &core, std::uint32_t object, const Verdicts &verdicts) {
  core.mem_w8(object + kOnScreenOffset, verdicts.retail ? 1u : 0u);
  core.r[kReturnValue] = verdicts.retail ? 1u : 0u;
  context(core).widenedObjects.record(core, object, verdicts.retail, verdicts.widened);
}

// 0x8002B288 is_on_screen: slack 32 each side.
void isOnScreenTight(Core *core) {
  const std::uint32_t object = core->r[kArg0];
  publish(*core, object, decide(*core, object, kBaseOnScreenTight.halfWidth, kBaseOnScreenTight.halfHeight));
}

// 0x8002B3C0: widest window, slack 96 horizontal and 80 vertical.
void onScreenWide(Core *core) {
  const std::uint32_t object = core->r[kArg0];
  publish(*core, object, decide(*core, object, kBaseOnScreenWide.halfWidth, kBaseOnScreenWide.halfHeight));
}

// 0x8002B318: a1/a2 are the per-side half-extents.
void onScreenParametric(Core *core) {
  const std::uint32_t object = core->r[kArg0];
  publish(*core, object, decide(*core, object, static_cast<int>(core->r[kArg1]), static_cast<int>(core->r[kArg2])));
}

// 0x800D46F4 quad_is_on_screen: the QuadObj corner extents with no slack; background byte at +0x37.
void quadOnScreen(Core *core) {
  const std::uint32_t object = core->r[kArg0];
  const Verdicts verdicts{VisibilityCull::retail().quadOnScreen(*core, object),
                          VisibilityCull{context(*core).widescreen.plan()}.quadOnScreen(*core, object)};
  publish(*core, object, verdicts);
}

// 0x80023DB8: the retail draw pass runs with widened-only objects raised, then gameplay's bytes come back.
void objectDrawPass(Core *core) {
  WidenedObjects &widened = context(*core).widenedObjects;
  const std::vector<std::uint32_t> raised = widened.raise(*core);
  lucent::debug("x4-cull", "draw pass raises {} of {} widened objects", raised.size(), widened.size());
  psx::cpu::callOriginalResumingToReturn(*core, "cull::objectDrawPass original", guest::kObjectDrawPassFn, core->r[31]);
  WidenedObjects::lower(*core, raised);
}

} // namespace

void registerOverrides(Core &core) {
  psx::cpu::installNativeOverride(core, kBaseOnScreenTight.address, "cull::isOnScreenTight", isOnScreenTight);
  psx::cpu::installNativeOverride(core, kBaseOnScreenWide.address, "cull::onScreenWide", onScreenWide);
  psx::cpu::installNativeOverride(
      core, kBaseOnScreenParametric.address, "cull::onScreenParametric", onScreenParametric);
  psx::cpu::installNativeOverride(core, kQuadOnScreen.address, "cull::quadOnScreen", quadOnScreen);
  psx::cpu::installNativeOverride(core, guest::kObjectDrawPassFn, "cull::objectDrawPass", objectDrawPass);
}

} // namespace x4::cull
