// Hermetic gate for game/render/hud_anchor.{h,cpp}: the HUD packets move to their own edge, against hand-written RAM.
#include "hud_anchor.h"

#include "core.h"
#include "game.h"

#include <cstdio>
#include <memory>

namespace {

using x4::hud::ArenaPositions;
using x4::hud::HudAnchor;
using x4::hud::kArenaCursors;

#define CHECK(cond)                                                                                                    \
  do {                                                                                                                 \
    if (!(cond)) {                                                                                                     \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                                             \
      return false;                                                                                                    \
    }                                                                                                                  \
  } while (0)

// 16:9 on the 320-wide guest buffer: (428 - 320) / 2.
constexpr int kMargin = 54;
constexpr std::uint32_t kSpriteArena = 0x80139830u;
constexpr std::uint32_t kPolygonArena = 0x80149998u;

GuestProjectionPlan planWithMargin(int margin) {
  GuestProjectionPlan plan;
  plan.presentationHorizontalMargin = margin;
  return plan;
}

struct Fixture {
  std::unique_ptr<Game> game = std::make_unique<Game>();
  Core &core = game->core;

  // SPRT_16: tag (length 3), colour + command, xy, uv + clut.
  void sprite(std::uint32_t at, int x, int y) {
    core.mem_w32(at, 0x03000000u);
    core.mem_w32(at + 4, 0x7C808080u);
    core.mem_w16(at + 8, static_cast<std::uint16_t>(x));
    core.mem_w16(at + 10, static_cast<std::uint16_t>(y));
    core.mem_w32(at + 12, 0u);
  }
  // POLY_G4: tag (length 8), then colour/vertex pairs.
  void shadedQuad(std::uint32_t at, int x) {
    core.mem_w32(at, 0x08000000u);
    core.mem_w32(at + 4, 0x38808080u);
    for (std::uint32_t i = 0; i < 4; ++i) {
      const std::uint32_t vertex = at + 8 + i * 8;
      core.mem_w16(vertex, static_cast<std::uint16_t>(x + static_cast<int>(i % 2) * 8));
      core.mem_w16(vertex + 2, static_cast<std::uint16_t>(i / 2 * 8));
      if (i < 3) {
        core.mem_w32(vertex + 4, 0x00808080u);
      }
    }
  }
  int x(std::uint32_t at) const {
    return static_cast<std::int16_t>(core.mem_r16(at + 8));
  }
  void setCursors(std::uint32_t polygons, std::uint32_t sprites) {
    core.mem_w32(kArenaCursors[0], polygons);
    core.mem_w32(kArenaCursors[1], polygons);
    core.mem_w32(kArenaCursors[2], sprites);
  }
};

bool verifySpritesMoveToTheirEdge(Fixture &f) {
  const HudAnchor anchor{planWithMargin(kMargin)};
  f.setCursors(kPolygonArena, kSpriteArena);
  const ArenaPositions before = HudAnchor::positions(f.core);
  f.sprite(kSpriteArena, 20, 8);
  f.sprite(kSpriteArena + 16, 280, 8);
  f.sprite(kSpriteArena + 32, 159, 8);
  f.core.mem_w32(kArenaCursors[2], kSpriteArena + 48);
  anchor.anchor(f.core, before);
  CHECK(f.x(kSpriteArena) == 20 - kMargin);
  CHECK(f.x(kSpriteArena + 16) == 280 + kMargin);
  CHECK(f.x(kSpriteArena + 32) == 159 - kMargin);
  // y is untouched.
  CHECK(static_cast<std::int16_t>(f.core.mem_r16(kSpriteArena + 10)) == 8);
  return true;
}

bool verifyOnlyNewPacketsMove(Fixture &f) {
  const HudAnchor anchor{planWithMargin(kMargin)};
  f.setCursors(kPolygonArena, kSpriteArena + 16);
  f.sprite(kSpriteArena, 20, 8);
  const ArenaPositions before = HudAnchor::positions(f.core);
  f.sprite(kSpriteArena + 16, 20, 8);
  f.core.mem_w32(kArenaCursors[2], kSpriteArena + 32);
  anchor.anchor(f.core, before);
  CHECK(f.x(kSpriteArena) == 20);
  CHECK(f.x(kSpriteArena + 16) == 20 - kMargin);
  return true;
}

bool verifyPolygonsMoveAsOne(Fixture &f) {
  const HudAnchor anchor{planWithMargin(kMargin)};
  f.setCursors(kPolygonArena, kSpriteArena);
  const ArenaPositions before = HudAnchor::positions(f.core);
  f.shadedQuad(kPolygonArena, 300);
  f.core.mem_w32(kArenaCursors[0], kPolygonArena + 36);
  anchor.anchor(f.core, before);
  CHECK(static_cast<std::int16_t>(f.core.mem_r16(kPolygonArena + 8)) == 300 + kMargin);
  CHECK(static_cast<std::int16_t>(f.core.mem_r16(kPolygonArena + 16)) == 308 + kMargin);
  CHECK(static_cast<std::int16_t>(f.core.mem_r16(kPolygonArena + 24)) == 300 + kMargin);
  CHECK(static_cast<std::int16_t>(f.core.mem_r16(kPolygonArena + 32)) == 308 + kMargin);
  return true;
}

bool verifyNoMarginChangesNothing(Fixture &f) {
  const HudAnchor retail{planWithMargin(0)};
  CHECK(retail.margin() == 0);
  f.setCursors(kPolygonArena, kSpriteArena);
  const ArenaPositions before = HudAnchor::positions(f.core);
  f.sprite(kSpriteArena, 20, 8);
  f.core.mem_w32(kArenaCursors[2], kSpriteArena + 16);
  retail.anchor(f.core, before);
  CHECK(f.x(kSpriteArena) == 20);
  const HudAnchor inverted{planWithMargin(-40)};
  inverted.anchor(f.core, before);
  CHECK(f.x(kSpriteArena) == 20);
  return true;
}

} // namespace

int main() {
  Fixture fixture;
  if (!verifySpritesMoveToTheirEdge(fixture) || !verifyOnlyNewPacketsMove(fixture) ||
      !verifyPolygonsMoveAsOne(fixture) || !verifyNoMarginChangesNothing(fixture)) {
    return 1;
  }
  std::fputs("x4_hud_anchor: ok\n", stderr);
  return 0;
}
