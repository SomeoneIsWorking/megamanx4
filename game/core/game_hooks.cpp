// game_hooks.cpp — the Mega Man X4 GameHooks vtable: the behaviour the PSX-generic framework calls
// into. This port owns NO game behaviour natively, so the table is deliberately tiny.
//
// There are exactly two kinds of member here, and the distinction is the point (the shape is taken
// from spider1/game/core/game_hooks.cpp, which learned it the hard way):
//
//   NEUTRAL   — the hook asks "what does the GAME's native code contribute here?", and the honest
//               answer while nothing is owned is "nothing". A neutral body is the CORRECT semantic,
//               not a placeholder.
//   FAIL-FAST — the hook is only reachable from a framework path this port has not stood up. Being
//               called means the run wandered into an un-RE'd path, and the only correct response is
//               to say so loudly and abort. A silent stub would let a half-wired path look like it
//               worked, which is the fake-green the porting doc warns about.
//
// bootInit is the ONE hook with real work, and even that work is one line: dispatch the guest's own
// main() and let the substrate run the game. It cannot do that yet — GameConfig::gameMain is 0
// because RE-01 has not been done — so it refuses rather than dispatching address zero.
#include "core.h"
#include "game_iface.h"
#include "cfg.h"
#include <stdlib.h>

// ── boot ────────────────────────────────────────────────────────────────────────────────────────
static void x4_bootInit(Core* c) {
  if (!c->cfg->gameMain) {
    cfg_loge("boot", "GameConfig::gameMain is 0 — this port's crt0/boot RE (RE-01 in "
                     "docs/re-frontier.md) has not been done, so there is no guest main() to "
                     "dispatch. Refusing to dispatch address 0.");
    abort();
  }
  cfg_logi("boot", "dispatching guest main() 0x%08X on the recompiled substrate", c->cfg->gameMain);
  rec_dispatch(c, c->cfg->gameMain);
}

// ── neutral ─────────────────────────────────────────────────────────────────────────────────────
static void x4_registerOverrides(Game*) {
  // No native override exists — this port owns no guest function. Nothing to install is the truthful
  // state, and keeping the hook wired means the wiring is exercised from the first commit rather than
  // stood up later on top of an untested seam.
}

static void x4_renderFadeState(Core*, FadeState* out) {
  out->mode = 0;                      // 0 == no fade; the present path leaves pixels untouched
  out->r = out->g = out->b = 0;
}

static void x4_renderBbFrameReset(Core*) {
  // No native billboard records are kept — nothing to reset.
}

static bool x4_hasNativeHandlerForEntry(Core*, uint32_t) { return false; }  // truthfully: none
static int  x4_devAreaCount(Core*)            { return 0; }   // truthfully: no area index RE'd
static const char* x4_devAreaName(Core*, int) { return ""; }  // "" == no sourced name
static bool x4_devWarpAllowed(Core*)          { return false; }

// ── fail-fast ───────────────────────────────────────────────────────────────────────────────────
static void unstood_up(const char* what) {
  cfg_loge("hooks", "%s was called, but this port has not stood that path up yet. Reaching it means "
                    "the run entered an un-RE'd framework path — see docs/re-frontier.md. Refusing "
                    "to continue with fabricated behaviour.", what);
  abort();
}

// frameUpdate / drawOTag are fail-fast AND STAY THAT WAY. They are not "not yet" — this port does not
// stand up the framework's native frame loop at all, because the game is already 60fps so there is no
// interpolation to serve and no native producer to drive (USER decision 2026-08-12, CLAUDE.md). In
// codemap vocabulary the native frame loop is ➖ not-applicable, NOT ⬜ todo. If either of these is ever
// reached, the run wandered somewhere this port has no business being, and aborting says so.
static void x4_frameUpdate(Core*)         { unstood_up("frameUpdate (native frame loop)"); }
static void x4_drawOTag(Core*, uint32_t)  { unstood_up("drawOTag (native frame loop)"); }
static int  x4_schedStageBody(Core*, int, void*) { unstood_up("schedStageBody (PcScheduler)"); return 0; }
static bool x4_schedFreshEntry(Core*, int, uint32_t, uint32_t) { unstood_up("schedFreshEntry (PcScheduler)"); return false; }
static void x4_devWarpAreaLoad(Core*)     { unstood_up("devWarpAreaLoad (dev warp)"); }

// DESIGNATED initialisers, deliberately — every hook binds BY NAME, so a field added upstream cannot
// slide this table by one (which, between two hooks of the same signature, compiles silently and calls
// the wrong function). C++20 requires designators in declaration order; keep them so when adding one.
// Unlisted members are value-initialised to null, so this list reads as the exact inventory of what
// this port has stood up.
static const GameHooks g_x4_hooks = {
    .frameUpdate              = x4_frameUpdate,
    .drawOTag                 = x4_drawOTag,
    .bootInit                 = x4_bootInit,
    .schedFreshEntry          = x4_schedFreshEntry,
    .hasNativeHandlerForEntry = x4_hasNativeHandlerForEntry,
    .registerOverrides        = x4_registerOverrides,
    .renderFadeState          = x4_renderFadeState,
    .renderBbFrameReset       = x4_renderBbFrameReset,
    .devWarpAreaLoad          = x4_devWarpAreaLoad,
    .devAreaCount             = x4_devAreaCount,
    .devAreaName              = x4_devAreaName,
    .devWarpAllowed           = x4_devWarpAllowed,
    .schedStageBody           = x4_schedStageBody,
};

const GameHooks* x4_game_hooks() { return &g_x4_hooks; }
