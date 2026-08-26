// SPDX-License-Identifier: AGPL-3.0-or-later
// Derived from external/mmx4/src/main/title_quad.c; retail addresses and layout are independently
// re-measured by tools/re_title_quad.py from SLUS_005.61.
#include "title_quad.h"

#include "core.h"
#include "override_registry.h"

#include <lucent/log.h>

#ifdef MMX4_HAVE_SUBSTRATE
extern void gen_func_800D6F94(Core *);
extern void shard_set_override(std::uint32_t, void (*)(Core *));
#endif

namespace x4::title_quad {

namespace {

constexpr std::uint32_t kCoordinateCount = 8u;
constexpr std::uint32_t kCoordinateStride = 4u;
constexpr std::uint32_t kPresetStride = kCoordinateCount * sizeof(std::uint16_t);
constexpr std::uint8_t kVisibleBit = 0x80u;
constexpr std::uint8_t kInitialState = 3u;
constexpr std::uint8_t kInitialPrimitiveCode = 0x10u;
constexpr std::uint16_t kInitialTimer = 0x14u;

} // namespace

void initializeWhiteLogoQuad(Core *core) {
  const std::uint32_t object = core->r[4];
  const std::int32_t variant = static_cast<std::int8_t>(core->mem_r8(object + Fields::kVariant));
  const std::uint32_t preset = kVertexPresets + static_cast<std::uint32_t>(variant * kPresetStride);

  core->mem_w8(object + Fields::kBackgroundOffset, 0xFFu);
  core->mem_w8(object + Fields::kEnabled, 1u);
  core->mem_w16(object + Fields::kXPositionInteger, 0u);
  core->mem_w16(object + Fields::kYPositionInteger, 0u);
  core->mem_w8(object + Fields::kActive, core->mem_r8(object + Fields::kActive) | kVisibleBit);

  for (std::uint32_t coordinate = 0; coordinate < kCoordinateCount; ++coordinate) {
    core->mem_w16(object + Fields::kFirstVertexCoordinate + coordinate * kCoordinateStride,
                  core->mem_r16(preset + coordinate * sizeof(std::uint16_t)));
  }

  const std::uint16_t color = core->mem_r16(kInitialColor);
  core->mem_w8(object + Fields::kPrimitiveCode, kInitialPrimitiveCode);
  core->mem_w8(object + Fields::kState, kInitialState);
  core->mem_w16(object + Fields::kTimer, kInitialTimer);
  core->mem_w8(object + Fields::kPhase, 0u);
  core->mem_w16(object + Fields::kColor, color);

  // Preserve the retail body's caller-saved register leaves. Mirror verification compares these in
  // addition to every touched RAM byte; matching only the QuadObj would be a hollow ownership gate.
  core->r[2] = kInitialTimer;
  core->r[3] = color;
  core->r[5] = kVertexPresets;
}

void registerOverride() {
#ifdef MMX4_HAVE_SUBSTRATE
  overrides::install(kInitializeWhiteLogoQuad,
                     "title::initializeWhiteLogoQuad",
                     initializeWhiteLogoQuad,
                     gen_func_800D6F94,
                     shard_set_override);
#else
  lucent::debug("x4-title", "title-quad ownership registration deferred: no generated substrate");
#endif
}

} // namespace x4::title_quad
