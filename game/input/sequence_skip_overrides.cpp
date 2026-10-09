// SPDX-License-Identifier: AGPL-3.0-or-later
// The retail pad route runs unchanged through the scoped original call; the skip edits its products afterwards.
#include "sequence_skip_overrides.h"

#include "core.h"
#include "enhancements.h"
#include "native_dispatch.h"
#include "player_object.h"
#include "resumable_guest_call.h"
#include "sequence_skip.h"

#include "x4_context.h"

namespace x4::sequence_skip {
namespace {

void padRoute(Core *core) {
  psx::cpu::callOriginalResumingToReturn(*core, "sequence_skip::padRoute original", guest::kInputRouterFn, core->r[31]);
  if (enh(skipCvar())) {
    context(*core).sequenceSkip.afterPadRoute(*core);
  }
}

} // namespace

void registerOverrides(Core &core) {
  psx::cpu::installNativeOverride(core, guest::kInputRouterFn, "sequence_skip::padRoute", padRoute);
}

} // namespace x4::sequence_skip
