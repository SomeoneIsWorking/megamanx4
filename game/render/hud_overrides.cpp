// SPDX-License-Identifier: AGPL-3.0-or-later
// The retail HUD pass runs unchanged through the scoped original call; its packets are moved after it returns.
#include "hud_overrides.h"

#include "core.h"
#include "hud_anchor.h"
#include "native_dispatch.h"
#include "resumable_guest_call.h"

#include "x4_context.h"

namespace x4::hud {
namespace {

void hudPass(Core *core) {
  const ArenaPositions before = HudAnchor::positions(*core);
  psx::cpu::callOriginalResumingToReturn(*core, "hud::hudPass original", kHudPass, core->r[31]);
  HudAnchor{context(*core).widescreen.plan()}.anchor(*core, before);
}

} // namespace

void registerOverrides(Core &core) {
  psx::cpu::installNativeOverride(core, kHudPass, "hud::hudPass", hudPass);
}

} // namespace x4::hud
