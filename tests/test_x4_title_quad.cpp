// SPDX-License-Identifier: AGPL-3.0-or-later
// Hermetic contract for RE-10's first matching-decomp-seeded native body.
#include "title_quad.h"

#include "core.h"
#include "game.h"

#include <array>
#include <cstdio>
#include <memory>

namespace {

constexpr std::uint32_t kObject = 0x80150000u;
constexpr std::uint8_t kVariant = 1u;
constexpr std::array<std::uint16_t, 8> kCoordinates = {
    0x1111u, 0x2222u, 0x3333u, 0x4444u, 0x5555u, 0x6666u, 0x7777u, 0x8888u};
constexpr std::uint16_t kColor = 0xBEEFu;

int g_checks = 0;

#define CHECK(condition)                                                                                               \
  do {                                                                                                                 \
    ++g_checks;                                                                                                        \
    if (!(condition)) {                                                                                                \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition);                                        \
      return 1;                                                                                                        \
    }                                                                                                                  \
  } while (0)

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  const std::uint32_t preset = x4::title_quad::kVertexPresets + kVariant * 16u;

  core.r[4] = kObject;
  core.r[2] = 0xDEADBEEFu;
  core.r[3] = 0xCAFEBABEu;
  core.r[5] = 0xFEEDFACEu;
  core.mem_w8(kObject + x4::title_quad::Fields::kVariant, kVariant);
  core.mem_w8(kObject + x4::title_quad::Fields::kActive, 0x25u);
  core.mem_w16(kObject + x4::title_quad::Fields::kXPositionInteger, 0xAAAAu);
  core.mem_w16(kObject + x4::title_quad::Fields::kYPositionInteger, 0xBBBBu);
  for (std::uint32_t i = 0; i < kCoordinates.size(); ++i) {
    core.mem_w16(preset + i * sizeof(std::uint16_t), kCoordinates[i]);
  }
  core.mem_w16(x4::title_quad::kInitialColor, kColor);

  x4::title_quad::initializeWhiteLogoQuad(&core);

  CHECK(core.mem_r8(kObject + x4::title_quad::Fields::kActive) == 0xA5u);
  CHECK(core.mem_r8(kObject + x4::title_quad::Fields::kVariant) == kVariant);
  CHECK(core.mem_r8(kObject + x4::title_quad::Fields::kState) == 3u);
  CHECK(core.mem_r16(kObject + x4::title_quad::Fields::kXPositionInteger) == 0u);
  CHECK(core.mem_r16(kObject + x4::title_quad::Fields::kYPositionInteger) == 0u);
  for (std::uint32_t i = 0; i < kCoordinates.size(); ++i) {
    CHECK(core.mem_r16(kObject + x4::title_quad::Fields::kFirstVertexCoordinate + i * 4u) == kCoordinates[i]);
  }
  CHECK(core.mem_r16(kObject + x4::title_quad::Fields::kColor) == kColor);
  CHECK(core.mem_r8(kObject + x4::title_quad::Fields::kPrimitiveCode) == 0x10u);
  CHECK(core.mem_r8(kObject + x4::title_quad::Fields::kBackgroundOffset) == 0xFFu);
  CHECK(core.mem_r16(kObject + x4::title_quad::Fields::kTimer) == 0x14u);
  CHECK(core.mem_r8(kObject + x4::title_quad::Fields::kEnabled) == 1u);
  CHECK(core.mem_r8(kObject + x4::title_quad::Fields::kPhase) == 0u);
  CHECK(core.r[2] == 0x14u);
  CHECK(core.r[3] == kColor);
  CHECK(core.r[4] == kObject);
  CHECK(core.r[5] == x4::title_quad::kVertexPresets);

  std::fprintf(stderr, "x4_title_quad: %d checks passed\n", g_checks);
  return 0;
}
