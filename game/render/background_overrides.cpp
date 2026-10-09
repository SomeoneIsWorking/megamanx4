// SPDX-License-Identifier: AGPL-3.0-or-later
// The retail bodies run unchanged through the scoped original call; the margin is added after they return.
#include "background_overrides.h"

#include "background_tiles.h"
#include "core.h"
#include "native_dispatch.h"
#include "resumable_guest_call.h"

#include "x4_context.h"

namespace x4::background {
namespace {

// Guest argument register $4 (a0).
constexpr int kArg0 = 4;

void original(Core *core, std::uint32_t address, const char *owner) {
  psx::cpu::callOriginalResumingToReturn(*core, owner, address, core->r[31]);
}

void drawLayer(Core *core) {
  const int layer = static_cast<int>(core->r[kArg0]);
  original(core, kDrawLayer, "background::drawLayer original");
  WideBackground{context(*core).widescreen.plan()}.drawLayer(*core, layer);
}

void refillRing(Core *core) {
  original(core, kRefillRing, "background::refillRing original");
  WideBackground{context(*core).widescreen.plan()}.refillRing(*core);
}

} // namespace

void registerOverrides(Core &core) {
  psx::cpu::installNativeOverride(core, kDrawLayer, "background::drawLayer", drawLayer);
  psx::cpu::installNativeOverride(core, kRefillRing, "background::refillRing", refillRing);
}

} // namespace x4::background
