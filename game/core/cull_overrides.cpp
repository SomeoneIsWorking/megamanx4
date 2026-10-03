// SPDX-License-Identifier: AGPL-3.0-or-later
// cull_overrides.cpp — the seven measured cull owners, transcribed guest body by guest body.
//
// WHAT AN ADAPTER OWNS, and what it deliberately does not. Each site has a different guest ABI (how
// many arguments, in which registers), a different return polarity, and — at 0x800B8490 — a different
// rule for where the camera scroll comes from. All three are per-site facts from the disassembly, so
// each site gets its own small function here. What they share, and what lives in visibility_cull.cpp,
// is the recovered arithmetic: recover the screen position, decide the window, publish the decision.
//
// THE REGISTER LEAVES ARE NOT REPRODUCED, and that is a measured decision rather than a convenience.
// These bodies are leaves: they allocate no frame, call nothing, and clobber only caller-saved
// registers ($2-$15, $24, $25) per the MIPS ABI, which the guest's own compiler observed at all 895
// call sites. The one register a caller may read is $v0, and every adapter writes it with the site's
// own return value. The 895 call sites were measured for how many read a caller-saved register
// before redefining it; that count is the evidence for this paragraph.
//
// A site that returned a value its callers test IS reproduced faithfully, because the value is the
// contract: 0x8002B160 and 0x8002B1E8 return 1 when the object is OFF screen (external/mmx4/src/main/
// BBE34.c:247 and BE4C0.c:338 test it with `== 0` and `!= 0`), while the five writers publish the flag
// byte and leave 0/1 in $v0.
#include "cull_overrides.h"

#include "core.h"
#include "native_dispatch.h"

#include "x4_context.h"

namespace x4::cull {
namespace {

// Guest argument registers, named. $4 is a0, $5 a1, $6 a2.
constexpr int kArg0 = 4;
constexpr int kArg1 = 5;
constexpr int kArg2 = 6;
// $v0, the one register a callee owns and a caller may read.
constexpr int kReturnValue = 2;

// The cull decision plus the screen coordinates it was taken from, so an adapter publishes what it
// decided without recovering the position a second time.
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

// A flag-writing site: the recovered body stores the 0/1 in BaseObj/QuadObj.on_screen, which is the byte
// the draw pass reads, and leaves the same 0/1 in $v0.
void publishFlag(Core &core, std::uint32_t object, const Decision &decision) {
  core.mem_w8(object + kOnScreenOffset, decision.onScreen ? 1u : 0u);
  core.r[kReturnValue] = decision.onScreen ? 1u : 0u;
}

// A site whose RETURN VALUE is the decision, inverted: these bodies return 1 when the object is OFF
// screen. The polarity is the site's, read from its `xori $2,$2,0x1`, not this owner's.
void publishOffScreenReturn(Core &core, const Decision &decision) {
  core.r[kReturnValue] = decision.onScreen ? 0u : 1u;
}

// ── 0x8002B288 is_on_screen ──────────────────────────────────────────────────────────────────────
// `void is_on_screen(BaseObj*)`: a0 is the object, and the body writes on_screen and nothing else. Its
// slack is 32 on each side, from `addiu $2,$5,0x20` and the `sltiu` bounds 0x180 / 0x130.
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

// ── 0x8002B3C0 ───────────────────────────────────────────────────────────────────────────────────
// The same shape with the game's WIDEST window: `addiu 0x60`/`sltiu 0x200` horizontally and
// `addiu 0x50`/`sltiu 0x190` vertically, so the two slacks are 96 and 80 and not one number. Called for
// its side effect only (external/mmx4/src/main/323C.c:2621 and six more).
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

// ── 0x8002B318 ───────────────────────────────────────────────────────────────────────────────────
// The PARAMETRIC flag writer: a1 and a2 are the per-side half-extents, and the body computes the bound
// as 2*half + 320 / 2*half + 240 in registers. The decomp's own call sites pass 0x20/0x20
// (visual_objs.c:26), 0x80/0x30 (select_a_character.c:332) and 0xA0/0xA0 (395D0.c:3634), which is the
// proof that these two arguments are the slack and not a coordinate. 403 call sites: the most-used cull
// in the game.
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

// ── 0x8002B1E8 ───────────────────────────────────────────────────────────────────────────────────
// The same parametric test, returning the OFF-screen flag instead of writing one. Its return value is
// part of the contract: callers branch on it.
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

// ── 0x8002B160 ───────────────────────────────────────────────────────────────────────────────────
// The fixed 64/64 variant returning the OFF-screen flag: `addiu 0x40` with `sltiu 0x1C0` / `0x170`.
// Also read by callers (BBE34.c:247, effect_objs.c:178, shot_objs.c:444).
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

// ── 0x800B8490 ───────────────────────────────────────────────────────────────────────────────────
// The same fixed 64/64 test as a standalone body a pool loop calls. It is the one site that does NOT
// consult the object's own background byte: it loads 0x801419BA and 0x801419BE unconditionally and never
// reads +0x14, so its scroll always comes from camera layer 0. That is measured; treating it as "read
// the byte like the others" would be a guess that happens to be right for objects on layer 0 and wrong
// for every other layer.
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

// ── 0x800D46F4 quad_is_on_screen ─────────────────────────────────────────────────────────────────
// The QuadObj's own four corner extents with ZERO slack, OR'd, publishing QuadObj.on_screen. It reads
// its background byte at +0x37, not +0x14, and its four corner pairs at +0x16/+0x1A, +0x1E/+0x22,
// +0x26/+0x2A and +0x2E/+0x32.
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
