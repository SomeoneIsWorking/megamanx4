// game_hooks.cpp — bounded compatibility callbacks not yet migrated into X4Runtime.
//
// There are exactly two kinds of member here, and the distinction is the point
// (the shape is taken from spider1/game/core/game_hooks.cpp, which learned it
// the hard way):
//
//   NEUTRAL   — the hook asks "what does the GAME's native code contribute
//   here?", and the honest
//               answer while nothing is owned is "nothing". A neutral body is
//               the CORRECT semantic, not a placeholder.
//   FAIL-FAST — the hook is only reachable from a framework path this port has
//   not stood up. Being
//               called means the run wandered into an un-RE'd path, and the
//               only correct response is to say so loudly and abort. A silent
//               stub would let a half-wired path look like it worked, which is
//               the fake-green the porting doc warns about.
//
#include "cfg.h"
#include "core.h"
#include "game_iface.h"
#include "legacy_game_interface.h"
#include <stdlib.h>

// ── neutral
// ─────────────────────────────────────────────────────────────────────────────────────
static void x4_renderFadeState(Core *, FadeState *out) {
  out->mode = 0; // 0 == no fade; the present path leaves pixels untouched
  out->r = out->g = out->b = 0;
}

static void x4_renderBbFrameReset(Core *) {
  // No native billboard records are kept — nothing to reset.
}

static bool x4_hasNativeHandlerForEntry(Core *, uint32_t) {
  return false;
} // truthfully: none
static int x4_devAreaCount(Core *) {
  return 0;
} // truthfully: no area index RE'd
static const char *x4_devAreaName(Core *, int) {
  return "";
} // "" == no sourced name
static bool x4_devWarpAllowed(Core *) {
  return false;
}

// ── fail-fast
// ───────────────────────────────────────────────────────────────────────────────────
static void unstood_up(const char *what) {
  cfg_loge("hooks",
           "%s was called, but this port has not stood that path up yet. "
           "Reaching it means "
           "the run entered an un-RE'd framework path — see "
           "docs/re-frontier.md. Refusing "
           "to continue with fabricated behaviour.",
           what);
  abort();
}

// frameUpdate / drawOTag are fail-fast AND STAY THAT WAY. The typed X4FrameDriver owns the one-step
// retail loop directly; it does not route through these legacy native-producer hooks. If either is
// reached, the run entered a second loop/render ownership path, and aborting exposes that split.
static void x4_frameUpdate(Core *) {
  unstood_up("frameUpdate (native frame loop)");
}
static void x4_drawOTag(Core *, uint32_t) {
  unstood_up("drawOTag (native frame loop)");
}
static int x4_schedStageBody(Core *, int, void *) {
  unstood_up("schedStageBody (PcScheduler)");
  return 0;
}
static bool x4_schedFreshEntry(Core *, int, uint32_t, uint32_t) {
  unstood_up("schedFreshEntry (PcScheduler)");
  return false;
}
static void x4_devWarp(Core *, int, int) {
  unstood_up("devWarp");
}

// DESIGNATED initialisers, deliberately — every hook binds BY NAME, so a field
// added upstream cannot slide this table by one (which, between two hooks of
// the same signature, compiles silently and calls the wrong function). C++20
// requires designators in declaration order; keep them so when adding one.
// Unlisted members are value-initialised to null, so this list reads as the
// exact inventory of what this port has stood up.
static const GameHooks g_x4_hooks = {
    .frameUpdate = x4_frameUpdate,
    .drawOTag = x4_drawOTag,
    .schedFreshEntry = x4_schedFreshEntry,
    .hasNativeHandlerForEntry = x4_hasNativeHandlerForEntry,
    .renderFadeState = x4_renderFadeState,
    .renderBbFrameReset = x4_renderBbFrameReset,
    .devWarp = x4_devWarp,
    .devAreaCount = x4_devAreaCount,
    .devAreaName = x4_devAreaName,
    .devWarpAllowed = x4_devWarpAllowed,
    .schedStageBody = x4_schedStageBody,
};

const GameHooks &x4::legacy::compatibilityHooks = g_x4_hooks;
