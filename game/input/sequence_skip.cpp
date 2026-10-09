// SPDX-License-Identifier: AGPL-3.0-or-later
#include "sequence_skip.h"

#include "core.h"
#include "player_object.h"

namespace x4::sequence_skip {

bool SequenceSkip::inBriefing(Core &core) {
  return core.mem_r8(kEngineAddress + kEngineStateOffset) == kBriefingState &&
         core.mem_r8(kEngineAddress + kEngineSubStateOffset) == kBriefingSubState;
}

void SequenceSkip::afterPadRoute(Core &core) {
  const guest::PadLens pad(core, guest::kPadHeldP1);
  if (!inBriefing(core) || (pad.held() & kStartMask) == 0) {
    fields_ = 0;
    return;
  }
  const bool advance = fields_ % kAdvanceCadence == 0;
  ++fields_;
  if (!advance) {
    return;
  }
  const std::uint16_t held = pad.held();
  const std::uint16_t previous = pad.previous();
  core.mem_w16(guest::kPadHeldP1, static_cast<std::uint16_t>(held | kCrossMask));
  core.mem_w16(guest::kPadPressedP1,
               static_cast<std::uint16_t>(pad.pressed() | ((previous & kCrossMask) == 0 ? kCrossMask : 0)));
}

} // namespace x4::sequence_skip
