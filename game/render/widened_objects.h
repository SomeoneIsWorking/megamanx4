// SPDX-License-Identifier: AGPL-3.0-or-later
// widened_objects.h - objects the widened box admits but the retail box culls; they are drawn, never simulated.
#pragma once

#include "visibility_cull.h"

#include <cstdint>
#include <unordered_map>
#include <vector>

class Core;

namespace x4::cull {

// Object header shared by every pool: `active` byte +0 and `id` byte +1 (the update dispatch index).
inline constexpr std::uint32_t kObjectActiveOffset = 0x00u;
inline constexpr std::uint32_t kObjectIdOffset = 0x01u;

// Gameplay reads the retail on_screen byte; only the draw pass sees the raised one.
class WidenedObjects {
public:
  // Called by each flag-writing cull site with both verdicts; keeps the entry only for a widened-only object.
  void record(Core &core, std::uint32_t object, bool retailOnScreen, bool widenedOnScreen);

  // Raises on_screen to 1 on every recorded object that is still live and retail-culled; returns them.
  std::vector<std::uint32_t> raise(Core &core) const;

  // Puts the retail value back on the objects raise() returned.
  static void lower(Core &core, const std::vector<std::uint32_t> &raised);

  std::size_t size() const {
    return idByObject_.size();
  }

private:
  // object address -> id byte when recorded, so a reused slot does not inherit the entry.
  std::unordered_map<std::uint32_t, std::uint8_t> idByObject_;
};

} // namespace x4::cull
