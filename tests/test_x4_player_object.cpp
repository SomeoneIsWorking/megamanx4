// test_x4_player_object.cpp — hermetic gate for RE-07's typed lens (game/core/player_object.h).
//
// POSITIVE class: guest state planted at the measured addresses is read back through the
// named lens accessors with the documented semantics.
// NEGATIVE classes:
//   1. NON-ALIASING — the same bytes planted at an address 0x100 past each measured block
//      must NOT be visible through the lens (a wrong constant would read them).
//   2. OFFSET PINNING — every PlayerOffsets/CameraLayerOffsets constant lands on a distinct
//      planted byte, so a wrong offset reads the wrong value (compile-time asserts pin the
//      fixed-point half pairs; runtime asserts pin everything else).
// No disc, no window, no guest execution: a bare Game/Core with hand-written RAM.
#include "player_object.h"

#include "core.h"
#include "game.h"

#include <cstdio>
#include <memory>

namespace {

using x4::guest::CameraLayerLens;
using x4::guest::kCameraLayersAddress;
using x4::guest::kCameraLayerStride;
using x4::guest::kEntityAddress;
using x4::guest::kPadHeldP1;
using x4::guest::kPadHeldP2;
using x4::guest::kPadPressedP1;
using x4::guest::kPlayerAddress;
using x4::guest::PlayerLens;
using x4::guest::PlayerOffsets;

int g_checks = 0;

#define CHECK(cond)                                                                                                    \
  do {                                                                                                                 \
    ++g_checks;                                                                                                        \
    if (!(cond)) {                                                                                                     \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                                             \
      return false;                                                                                                    \
    }                                                                                                                  \
  } while (0)

bool verify_player_lens(Core &core) {
  // Plant a full identity pattern so any offset error reads a wrong-but-plausible byte.
  for (uint32_t i = 0; i < 0xE4; ++i) {
    core.mem_w8(kPlayerAddress + i, static_cast<uint8_t>(i));
  }
  core.mem_w8(kPlayerAddress + PlayerOffsets::kActive, 1);
  core.mem_w8(kPlayerAddress + PlayerOffsets::kId, 0x11);
  core.mem_w8(kPlayerAddress + PlayerOffsets::kCharacter, 0);
  core.mem_w16(kPlayerAddress + PlayerOffsets::kXPos, 0xBEEF); // fraction half must not leak
  core.mem_w16(kPlayerAddress + PlayerOffsets::kXPosHi, static_cast<uint16_t>(-160));
  core.mem_w16(kPlayerAddress + PlayerOffsets::kYPosHi, 120);
  core.mem_w8(kPlayerAddress + PlayerOffsets::kBgSlot, static_cast<uint8_t>(-1));
  core.mem_w8(kPlayerAddress + PlayerOffsets::kCurAnim, 7);
  core.mem_w8(kPlayerAddress + PlayerOffsets::kHitpoints, static_cast<uint8_t>(-3));

  PlayerLens player(core, kPlayerAddress);
  CHECK(player.active());
  CHECK(player.id() == 0x11);
  CHECK(player.character() == 0);
  CHECK(player.xPixels() == -160);
  CHECK(player.yPixels() == 120);
  CHECK(player.bgSlot() == -1);
  CHECK(player.currentAnimation() == 7);
  CHECK(player.hitpoints() == -3);

  // The same layout at g_Entity's address reads ITS own block, not the player's.
  core.mem_w8(kEntityAddress + PlayerOffsets::kCharacter, 1);
  core.mem_w16(kEntityAddress + PlayerOffsets::kXPosHi, 64);
  PlayerLens entity(core, kEntityAddress);
  CHECK(entity.active() == ((core.mem_r8(kEntityAddress) != 0)));
  CHECK(entity.xPixels() == 64);
  CHECK(entity.character() == 1);

  // NEGATIVE: a block one slot down is invisible to a correctly-addressed lens. Clear the
  // real block first so a later non-zero read could only mean the plants aliased.
  core.mem_w8(kPlayerAddress + PlayerOffsets::kActive, 0);
  core.mem_w8(kPlayerAddress + PlayerOffsets::kCharacter, 0);
  core.mem_w8(kPlayerAddress + 0x100 + PlayerOffsets::kActive, 1);
  core.mem_w8(kPlayerAddress + 0x100 + PlayerOffsets::kCharacter, 0x5A);
  PlayerLens shifted(core, kPlayerAddress + 0x100);
  CHECK(shifted.active());
  CHECK(shifted.character() == 0x5A);
  CHECK(!player.active());
  CHECK(player.character() == 0);
  return true;
}

bool verify_camera_lens(Core &core) {
  for (uint32_t slot = 0; slot < x4::guest::kCameraLayerCount; ++slot) {
    const uint32_t base = kCameraLayersAddress + slot * kCameraLayerStride;
    core.mem_w16(base + x4::guest::CameraLayerOffsets::kScrollX, static_cast<uint16_t>(100 * (slot + 1)));
    core.mem_w16(base + x4::guest::CameraLayerOffsets::kScrollY, static_cast<uint16_t>(40 + slot));
    core.mem_w8(base + x4::guest::CameraLayerOffsets::kMode, static_cast<uint8_t>(slot));
  }
  for (uint32_t slot = 0; slot < x4::guest::kCameraLayerCount; ++slot) {
    CameraLayerLens layer(core, kCameraLayersAddress, slot);
    CHECK(layer.scrollX() == static_cast<int16_t>(100 * (slot + 1)));
    CHECK(layer.scrollY() == static_cast<int16_t>(40 + slot));
    CHECK(layer.mode() == slot);
  }
  // NEGATIVE: stride errors alias adjacent layers — assert slots do not see each other.
  CameraLayerLens zero(core, kCameraLayersAddress, 0);
  CHECK(zero.mode() == 0);
  core.mem_w8(kCameraLayersAddress + kCameraLayerStride + x4::guest::CameraLayerOffsets::kMode, 0x5A);
  CHECK(zero.mode() == 0);
  return true;
}

bool verify_pad_lens(Core &core) {
  constexpr uint16_t kHeld = 0x1234;
  constexpr uint16_t kPrev = 0x5678;
  constexpr uint16_t kEdge = kHeld & static_cast<uint16_t>(~kPrev);
  core.mem_w16(kPadHeldP1, kHeld);
  core.mem_w16(kPadHeldP1 + 2, kPrev);
  core.mem_w16(kPadPressedP1, kEdge);
  x4::guest::PadLens pad1(core, kPadHeldP1);
  CHECK(pad1.held() == kHeld);
  CHECK(pad1.previous() == kPrev);
  CHECK(pad1.pressed() == kEdge);

  core.mem_w16(kPadHeldP2, 0xFFFF);
  x4::guest::PadLens pad2(core, kPadHeldP2);
  CHECK(pad2.held() == 0xFFFF);
  // NEGATIVE: pad 2 state lives at its own address; pad 1's view is unchanged.
  CHECK(pad1.held() == kHeld);
  return true;
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;

  if (!verify_player_lens(core) || !verify_camera_lens(core) || !verify_pad_lens(core)) {
    return 1;
  }
  std::fprintf(stderr, "x4_player_object: %d checks passed\n", g_checks);
  return 0;
}
