// SPDX-License-Identifier: AGPL-3.0-or-later
#include "widened_objects.h"

#include "core.h"

namespace x4::cull {

void WidenedObjects::record(Core &core, std::uint32_t object, bool retailOnScreen, bool widenedOnScreen) {
  if (widenedOnScreen && !retailOnScreen) {
    idByObject_[object] = core.mem_r8(object + kObjectIdOffset);
  } else {
    idByObject_.erase(object);
  }
}

std::vector<std::uint32_t> WidenedObjects::raise(Core &core) const {
  std::vector<std::uint32_t> raised;
  for (const auto &[object, id] : idByObject_) {
    const bool live = core.mem_r8(object + kObjectActiveOffset) != 0 && core.mem_r8(object + kObjectIdOffset) == id;
    if (live && core.mem_r8(object + kOnScreenOffset) == 0) {
      core.mem_w8(object + kOnScreenOffset, 1u);
      raised.push_back(object);
    }
  }
  return raised;
}

void WidenedObjects::lower(Core &core, const std::vector<std::uint32_t> &raised) {
  for (const std::uint32_t object : raised) {
    core.mem_w8(object + kOnScreenOffset, 0u);
  }
}

} // namespace x4::cull
