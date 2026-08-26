// SPDX-License-Identifier: AGPL-3.0-or-later
// Derived from external/mmx4/src/main/title_quad.c; retail addresses and layout are independently
// re-measured by tools/re_title_quad.py from SLUS_005.61.
#pragma once

#include <cstdint>

class Core;

namespace x4::title_quad {

inline constexpr std::uint32_t kInitializeWhiteLogoQuad = 0x800D6F94u;
inline constexpr std::uint32_t kTitleQuadUpdate = 0x800D76F8u;
inline constexpr std::uint32_t kTitleStateDispatch = 0x8010FDD0u;
inline constexpr std::uint32_t kVertexPresets = 0x8010FCCCu;
inline constexpr std::uint32_t kInitialColor = 0x8010FD94u;

struct Fields {
  static constexpr std::uint32_t kActive = 0x00u;
  static constexpr std::uint32_t kVariant = 0x02u;
  static constexpr std::uint32_t kState = 0x04u;
  static constexpr std::uint32_t kXPositionInteger = 0x0Au;
  static constexpr std::uint32_t kYPositionInteger = 0x0Eu;
  static constexpr std::uint32_t kFirstVertexCoordinate = 0x16u;
  static constexpr std::uint32_t kColor = 0x34u;
  static constexpr std::uint32_t kPrimitiveCode = 0x36u;
  static constexpr std::uint32_t kBackgroundOffset = 0x37u;
  static constexpr std::uint32_t kTimer = 0x38u;
  static constexpr std::uint32_t kEnabled = 0x42u;
  static constexpr std::uint32_t kPhase = 0x43u;
};

// First matching-decomp-seeded native body (RE-10). Initializes the white quad that becomes the
// MEGAMAN title logo. The guest ABI passes the 0x60-byte QuadObj in a0; mirror verification compares
// this body with gen_func_800D6F94 on live title state.
void initializeWhiteLogoQuad(Core *core);

// Installs the retained-super ownership triple only in the shipping substrate target.
void registerOverride();

} // namespace x4::title_quad
