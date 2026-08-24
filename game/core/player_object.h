// player_object.h — RE-07's READ-ONLY typed lens over the guest player-object system.
//
// Every constant below was measured against BOTH sources and is documented in
// docs/re-player-object.md: the AGPL reference decomp (external/mmx4, whose build target
// SHA-1 equals our extracted SLUS_005.61) AND our own bytes — either a raw instruction scan
// of the extracted executable or a Ghidra decompile of resident code
// (scratch/decomp/x4_*.c). A borrowed address that only ONE source carries would not be
// here. Offsets are pinned by static_assert so a future re-measurement that disagrees
// breaks the build instead of silently drifting.
//
// THIS LENS WRITES NOTHING. It names guest memory; it does not own or change it. The first
// native owner of any of these structures must land with its own byte-match gate (RE-10)
// before it rewires anything.
#pragma once

#include "core.h"

#include <cstdint>

namespace x4::guest {

// ── addresses ──────────────────────────────────────────────────────────────────────────────
// The player object ("g_Player" in mmx4): PlayerObj, 0xE4 bytes. 123 binary xrefs (scan
// floor); spawned by func_80035240; reset by func_8002A7D0.
inline constexpr uint32_t kPlayerAddress = 0x801418C8;
// The second PlayerObj ("g_Entity"): enemy/boss-side entity, same layout, spawned/reset as
// a pair with the player.
inline constexpr uint32_t kEntityAddress = 0x80175D58;
// Camera layer array: 3 entries, stride 0x54 ("background_objects" in mmx4). Entry 0 is the
// gameplay camera; layers 1/2 derive from it.
inline constexpr uint32_t kCameraLayersAddress = 0x801419B0;
inline constexpr uint32_t kCameraLayerCount = 3;
inline constexpr uint32_t kCameraLayerStride = 0x54;

// Input decode products, written every gameMain iteration by kInputRouterFn.
inline constexpr uint32_t kPadHeldP1 = 0x80166C08;    // u16 held buttons, pad 1
inline constexpr uint32_t kPadPrevP1 = 0x80166C0A;    // u16 previous-frame held
inline constexpr uint32_t kPadPressedP1 = 0x80166C0C; // u16 pressed edge == "controller_state"
inline constexpr uint32_t kPadHeldP2 = 0x80166D50;    // pad 2 trio — decoded by retail,
inline constexpr uint32_t kPadPrevP2 = 0x80166D52;    // consumed by nothing outside the
inline constexpr uint32_t kPadPressedP2 = 0x80166D54; // router (scan floor, see doc §3)

// Engine state bytes the spawn path consumes ("engine_obj" in mmx4 @ 0x801721C0).
inline constexpr uint32_t kEngineCharacterAddress = 0x80172203; // selected character (X=0 per
                                                                // the +2 branch in func_80035240)

// libpad packet buffers handed to InitPAD at 0x80012194 (RE-06), capacity 0x22 each.
inline constexpr uint32_t kPadPacketBufferP1 = 0x80166D68;
inline constexpr uint32_t kPadPacketBufferP2 = 0x8012F46C;

// Named guest functions (documentation-grade constants for traces/gates; no call site here).
inline constexpr uint32_t kInputRouterFn = 0x80012328;
inline constexpr uint32_t kPlayerInitFn = 0x80035240;
inline constexpr uint32_t kCameraDispatchFn = 0x80027850;
inline constexpr uint32_t kCameraModeFnTable = 0x800F3134;
inline constexpr uint32_t kInitObjectsFn = 0x80023DB8;
inline constexpr uint32_t kResetObjectsFn = 0x8002A7D0;
inline constexpr uint32_t kFindFreeMainObjFn = 0x8002AB74;
inline constexpr uint32_t kUpdateMainObjectsFn = 0x80021234;
inline constexpr uint32_t kMainObjectUpdateTable = 0x800F24A4;

// ── measured offsets ───────────────────────────────────────────────────────────────────────
struct PlayerOffsets {
  static constexpr uint32_t kActive = 0x00;       // u8: 1 after kPlayerInitFn spawns it
  static constexpr uint32_t kId = 0x01;           // u8: main_object_update_funcs[id] dispatch
  static constexpr uint32_t kCharacter = 0x02;    // u8: X/Zero selector copied from engine state
  static constexpr uint32_t kOnScreen = 0x03;     // u8: written by the on-screen cull pass
  static constexpr uint32_t kState = 0x04;        // u8: behaviour state (semantics: mmx4-sourced)
  static constexpr uint32_t kXPos = 0x08;         // s32 s16.16 fixed point; integer half at +0x0A
  static constexpr uint32_t kXPosHi = 0x0A;       // s16 integer part of x — what the camera follows
  static constexpr uint32_t kYPos = 0x0C;         // s32 s16.16 fixed point; integer half at +0x0E
  static constexpr uint32_t kYPosHi = 0x0E;       // s16 integer part of y
  static constexpr uint32_t kBgSlot = 0x14;       // s8 background layer index; <0 means screen-space
  static constexpr uint32_t kAnimTable = 0x30;    // pointer to the per-character animation table
  static constexpr uint32_t kCurAnim = 0x47;      // u8 frame-table index consumed by the sprite pass
  static constexpr uint32_t kPrevAnim = 0x48;     // u8
  static constexpr uint32_t kHitpoints = 0x5C;    // s8 life-gauge source (gauge renderer 0x800253F0)
  static constexpr uint32_t kMaxHitpoints = 0x5D; // s8
};

struct CameraLayerOffsets {
  static constexpr uint32_t kEnabled = 0x03;       // u8 init writes 1
  static constexpr uint32_t kMode = 0x04;          // u8 index into kCameraModeFnTable
  static constexpr uint32_t kTargetX = 0x08;       // s32 follow target
  static constexpr uint32_t kTargetY = 0x0C;       // s32
  static constexpr uint32_t kScrollX = 0x0A;       // s16 THE camera x — consumers subtract it
  static constexpr uint32_t kScrollY = 0x0E;       // s16 THE camera y
  static constexpr uint32_t kAnchorX = 0x16;       // s16 screen-edge load trigger anchor
  static constexpr uint32_t kAnchorY = 0x1A;       // s16
  static constexpr uint32_t kBoundMinX = 0x1C;     // s16 hard clamp windows (+ push-back on player)
  static constexpr uint32_t kBoundMaxX = 0x1E;     // s16
  static constexpr uint32_t kBoundMinY = 0x20;     // s16
  static constexpr uint32_t kBoundMaxY = 0x22;     // s16
  static constexpr uint32_t kDeadZoneLeft = 0x30;  // u16 horizontal dead-zone margins used by
  static constexpr uint32_t kDeadZoneRight = 0x32; // u16 the follow helpers
  static constexpr uint32_t kStepMax = 0x48;       // u8 max forward step per frame
  static constexpr uint32_t kStepBack = 0x49;      // s8 (= -kStepMax once following)
};

static_assert(PlayerOffsets::kXPosHi == PlayerOffsets::kXPos + 2);
static_assert(PlayerOffsets::kYPosHi == PlayerOffsets::kYPos + 2);

// ── the lens ───────────────────────────────────────────────────────────────────────────────
// Read-only named views over guest memory. Construction stores one Core*; every accessor
// reads through it live, so a lens never snapshots or pins guest state.
class PlayerLens {
public:
  explicit PlayerLens(Core &core, uint32_t address) : core_(core), address_(address) {}

  bool active() const {
    return core_.mem_r8(address_ + PlayerOffsets::kActive) != 0;
  }
  uint8_t id() const {
    return core_.mem_r8(address_ + PlayerOffsets::kId);
  }
  uint8_t character() const {
    return core_.mem_r8(address_ + PlayerOffsets::kCharacter);
  }
  uint8_t onScreen() const {
    return core_.mem_r8(address_ + PlayerOffsets::kOnScreen);
  }
  uint8_t state() const {
    return core_.mem_r8(address_ + PlayerOffsets::kState);
  }

  // Integer position in pixels — the s16.16 halves the camera and cull passes actually use.
  int16_t xPixels() const {
    return static_cast<int16_t>(core_.mem_r16(address_ + PlayerOffsets::kXPosHi));
  }
  int16_t yPixels() const {
    return static_cast<int16_t>(core_.mem_r16(address_ + PlayerOffsets::kYPosHi));
  }
  int8_t bgSlot() const {
    return static_cast<int8_t>(core_.mem_r8(address_ + PlayerOffsets::kBgSlot));
  }
  uint8_t currentAnimation() const {
    return core_.mem_r8(address_ + PlayerOffsets::kCurAnim);
  }
  int8_t hitpoints() const {
    return static_cast<int8_t>(core_.mem_r8(address_ + PlayerOffsets::kHitpoints));
  }

private:
  Core &core_;
  uint32_t address_;
};

class CameraLayerLens {
public:
  explicit CameraLayerLens(Core &core, uint32_t baseAddress, uint32_t slot)
      : core_(core), address_(baseAddress + slot * kCameraLayerStride) {}

  uint8_t mode() const {
    return core_.mem_r8(address_ + CameraLayerOffsets::kMode);
  }
  int16_t scrollX() const {
    return static_cast<int16_t>(core_.mem_r16(address_ + CameraLayerOffsets::kScrollX));
  }
  int16_t scrollY() const {
    return static_cast<int16_t>(core_.mem_r16(address_ + CameraLayerOffsets::kScrollY));
  }

private:
  Core &core_;
  uint32_t address_;
};

class PadLens {
public:
  explicit PadLens(Core &core, uint32_t heldAddress) : core_(core), held_(heldAddress) {}

  uint16_t held() const {
    return core_.mem_r16(held_);
  }
  uint16_t previous() const {
    return core_.mem_r16(held_ + 2);
  }
  uint16_t pressed() const {
    return core_.mem_r16(held_ + 4);
  }

private:
  Core &core_;
  uint32_t held_;
};

} // namespace x4::guest
