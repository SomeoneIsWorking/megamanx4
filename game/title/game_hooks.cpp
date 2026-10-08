// game_hooks.cpp - legacy framework hooks: neutral answers where the game contributes nothing, abort elsewhere.
#include "cfg.h"
#include "core.h"
#include "game_iface.h"
#include "legacy_game_interface.h"
#include <stdlib.h>

namespace x4::legacy {
namespace {

void renderFadeState(Core *, FadeState *out) {
  out->mode = 0;
  out->r = out->g = out->b = 0;
}

void renderBbFrameReset(Core *) {}

bool hasNativeHandlerForEntry(Core *, uint32_t) {
  return false;
}
int devAreaCount(Core *) {
  return 0;
}
const char *devAreaName(Core *, int) {
  return "";
}
bool devWarpAllowed(Core *) {
  return false;
}

void unstood_up(const char *what) {
  cfg_loge("hooks",
           "%s was called, but this port has not stood that path up yet. "
           "Reaching it means "
           "the run entered an un-RE'd framework path — see "
           "docs/issues/. Refusing "
           "to continue with fabricated behaviour.",
           what);
  abort();
}

// The typed X4FrameDriver owns the frame loop; reaching these means a second loop path exists.
void frameUpdate(Core *) {
  unstood_up("frameUpdate (native frame loop)");
}
void drawOTag(Core *, uint32_t) {
  unstood_up("drawOTag (native frame loop)");
}
int schedStageBody(Core *, int, void *) {
  unstood_up("schedStageBody (PcScheduler)");
  return 0;
}
bool schedFreshEntry(Core *, int, uint32_t, uint32_t) {
  unstood_up("schedFreshEntry (PcScheduler)");
  return false;
}
void devWarp(Core *, int, int) {
  unstood_up("devWarp");
}

// Designated initializers so an upstream field cannot shift the table; keep declaration order.
const GameHooks g_hooks = {
    .frameUpdate = frameUpdate,
    .drawOTag = drawOTag,
    .schedFreshEntry = schedFreshEntry,
    .hasNativeHandlerForEntry = hasNativeHandlerForEntry,
    .renderFadeState = renderFadeState,
    .renderBbFrameReset = renderBbFrameReset,
    .devWarp = devWarp,
    .devAreaCount = devAreaCount,
    .devAreaName = devAreaName,
    .devWarpAllowed = devWarpAllowed,
    .schedStageBody = schedStageBody,
};

} // namespace

const GameHooks &compatibilityHooks() {
  return g_hooks;
}

} // namespace x4::legacy
