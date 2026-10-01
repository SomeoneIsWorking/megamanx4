// SPDX-License-Identifier: AGPL-3.0-or-later
// visibility_cull.h — the native owner for SLUS_005.61's VISIBILITY CULL.
//
// WHY THIS EXISTS. X4's widescreen is a real horizontal FOV widening: the title replaces OFX 160 -> 214
// and the draw-environment RECT.w 320 -> 428 and leaves the focal length H = 512 alone, so the visible
// horizontal half-extent scales by 428/320 = 1.3375 while the centre pixel still maps to x/z = 0. The
// frame therefore GAINS 108 columns of guest geometry, 54 on each side of the authored 320-wide
// picture. SLUS_005.61 never learns that. Its cull asks whether an object's screen position lies in a
// window stated in retail 4:3 coordinates, and the draw pass then draws ONLY objects whose
// `on_screen` byte survived that test (external/mmx4/src/main/323C.c:3058-3236, one
// `if (obj->on_screen != 0) func_80024334(obj);` per object pool). So the widening's new margins had
// no coverage at all: geometry the wide frame can now show was discarded before it was drawn.
//
// THE ROOT CAUSE IS ONE THING, and it is not "two functions forgot 428". Every cull owner in the
// resident code states its window in the SAME retail idiom, found by decoding all 294,400
// instruction words of the executable's text section and searching for the idiom rather than for a
// list of known addresses (7 object-pool owners, 895 call sites). The idiom
// is
//
//     t = v + A ; t &= 0xFFFF ; (u32)t <u B
//
// which over the s16 the guest loaded is exactly the half-open box [-A, B-A). One recovered predicate
// serves all of them and the ONLY terms that change for widescreen are A and B.
//
// RETAIL FACTS (each an immediate in the image; the address sits
// beside every constant). PLAN-DERIVED (one term only). The plan contributes the horizontal margin
// and nothing else:
//
//   * the retail 320x240 extents are the guest's own, and the VERTICAL ones are never changed — a
//     widening is horizontal, and the recovered vertical bounds stay exactly as the bytes state them;
//   * `horizontalMargin` is `GuestProjectionPlan::presentationHorizontalMargin`, the framework's own 2D
//     layout shift (runtime/psx/render_queue.cpp:1341 `rq_2d_xform`, applied by
//     runtime/psx/wide_2d_layout.cpp:58, and independently by game/core/title_layout.cpp:19 for this
//     title's fixed-screen menu items). The cull MUST use the shift the draw path uses, because the
//     cull states its window in the guest's own pre-shift coordinates. That is why the widened window
//     is [-margin - slack, 428 - margin + slack) in guest coordinates and NOT [0, 428): an object at
//     guest x = -40 is drawn at 54 - 40 = +14, inside the new left margin, and a cull that ignored the
//     shift would throw it away — the same defect, moved.
//
// There is no second source of truth for the width and no literal 428 anywhere: at 4:3 the margin is
// 0, A and B reduce to the retail immediates, and this owner is the identity.
//
// AT 4:3 THIS OWNER IS THE IDENTITY, and that is a contract rather than a side effect. `ScreenWindow`
// is the transcription of three instructions, so the property is provable instead of sampled: at
// margin 0 `offset()` and `bound()` return the retail `addiu` and `sltiu` immediates for every
// recovered site, and `contains()` is then bit-for-bit the guest's unsigned 16-bit compare
// (tests/test_x4_visibility_cull.cpp pins it over ALL 65,536 coordinates for every window shape).
#pragma once

#include "guest_widescreen_projection.h"

#include <cstdint>

class Core;

namespace x4::cull {

// ── RETAIL FACTS ───────────────────────────────────────────────────────────────────────────────
// The guest's own 4:3 extents, as the immediates that state them. Widening moves the horizontal
// window; these stay the numbers a zero-margin window is built from.
struct RetailScreen {
  // sltiu $2,$2,0x140 @ 0x800D4774 / 0x800D4804 / 0x800D4894 / 0x800D4924 — quad_is_on_screen's x corners
  static constexpr int kWidth = 320;
  // sltiu $2,$2,0x0F0 @ 0x800D4780 / 0x800D4810 / 0x800D48A0 / 0x800D4930 — the same body's y corners
  static constexpr int kHeight = 240;
};

// Per-side slack in pixels, recovered per site. The slack is RETAIL: the number of pixels the game
// deliberately keeps outside the visible band so an object is not dropped while it enters or leaves.
// Widening moves the band and never the slack, which is why every widened window keeps exactly the
// same slack on each side of the wider band.
struct RetailSlack {
  // addiu $2,$5,0x20 with sltiu 0x180 / 0x130 @ 0x8002B2E8 / 0x8002B300 — is_on_screen
  static constexpr int kTight = 32;
  // addiu 0x60 with sltiu 0x200, addiu 0x50 with sltiu 0x190 @ 0x8002B420 / 0x8002B430
  static constexpr int kWideX = 96;
  static constexpr int kWideY = 80;
  // addiu 0x40 with sltiu 0x1C0 / 0x170 @ 0x8002B1BC / 0x8002B1D0 and 0x800B84B0 / 0x800B84C4
  static constexpr int kLoose = 64;
};

// The camera layer array, and the two fields inside one entry that convert world to screen. Measured:
// `lui $1,0x8014` with `lhu $3,0x19BA($1)` @ 0x8002B2C4 / 0x8002B2CC resolves to 0x801419BA plus
// 84*bg, and 0x54 is the entry stride the four `sll`/`addu` pairs build from the layer byte.
inline constexpr std::uint32_t kCameraLayersAddress = 0x801419B0u;
inline constexpr std::uint32_t kCameraLayerStride = 0x54u;
inline constexpr std::uint32_t kCameraScrollX = 0x0Au;
inline constexpr std::uint32_t kCameraScrollY = 0x0Eu;

// The measured header offsets of the two layouts, as the two bodies read them.
//   BaseObj: `lb $3,0x14($6)` @ 0x8002B28C and `lhu $5,0xa($6)` @ 0x8002B29C, `lhu $4,0xe($6)` @ 0x8002B2A0
//   QuadObj: `lb $3,0x37($6)` @ 0x800D46F8 and `lhu $3,0xa($6)` @ 0x800D470C, `lhu $2,0xe($6)` @ 0x800D4714
// The background offset DIFFERING between the two is the whole reason `ObjectLayout` exists.
inline constexpr std::uint32_t kBaseObjectBackgroundOffset = 0x14u;
inline constexpr std::uint32_t kQuadObjectBackgroundOffset = 0x37u;
inline constexpr std::uint32_t kPositionIntegerX = 0x0Au;
inline constexpr std::uint32_t kPositionIntegerY = 0x0Eu;

// The two object layouts the cull reads. They are NOT the same struct and the difference is
// load-bearing: the background byte is at +0x14 in BaseObj and at +0x37 in QuadObj (see the constants
// above), because QuadObj is a flat struct that repeats the header instead of embedding BaseObj. One
// shared offset would read the wrong byte for one of them.
enum class ObjectLayout {
  BaseObject,
  QuadObject,
};

struct LayoutOffsets {
  std::uint32_t backgroundOffset;
  std::uint32_t xInteger; // the integer half of the s16.16 position
  std::uint32_t yInteger;
};

// Where the scroll that converts world to screen comes from. One site ignores the object's own
// background byte and always subtracts camera layer 0 (measured: 0x800B8490 loads 0x801419BA /
// 0x801419BE unconditionally and never reads +0x14), so this is per-site data, not an assumption.
enum class BackgroundSource {
  ObjectByte, // a negative background byte means screen space; otherwise index the layer array
  LayerZero,  // always subtract camera layer 0
};

// quad_is_on_screen's four corner extents, in the order its four blocks read them. Offsets are from
// the QuadObj base and were confirmed against all eight `lhu` sites in the body.
inline constexpr std::uint32_t kQuadCornerX[4] = {0x16u, 0x1Eu, 0x26u, 0x2Eu};
inline constexpr std::uint32_t kQuadCornerY[4] = {0x1Au, 0x22u, 0x2Au, 0x32u};

// BaseObj.on_screen and QuadObj.on_screen, the byte the draw pass reads. Both layouts place it at +3
// (`sb $zero,0x3($6)` @ 0x8002B298 and @ 0x800D4704).
inline constexpr std::uint32_t kOnScreenOffset = 0x03u;

// ── the recovered window, as a value ────────────────────────────────────────────────────────────
// One 16-bit screen-space test: `(u16)(value + offset) <u bound`. Both terms are masked to sixteen
// bits because the guest masks them, so a 32-bit intermediate that overflows behaves exactly as it did
// in the guest.
//
// While `bound` fits in fifteen bits — which every MEASURED site does — that is the half-open box
// [-offset, bound - offset), and the offset is the site's recovered slack. Past that the predicate is
// a CYCLIC arc on the sixteen-bit circle rather than a box: the two parametric sites take their
// half-extent in a plain int register, so a caller can pass 40000 and the window becomes
// [-40000, -25216) union [25536, 40320). `contains` implements the wrap form, so it is correct in both
// regimes; the box reading is only the convenient description. tests/test_x4_visibility_cull.cpp pins
// both, so the convenience is never mistaken for the rule.
class ScreenWindow {
public:
  // The horizontal window: the retail width, the recovered per-side slack, and the plan's shift.
  static ScreenWindow horizontal(int half, int margin);
  // The vertical window. There is deliberately no margin parameter: a widening is horizontal, and a
  // vertical shift parameter would be an invitation to invent one later.
  static ScreenWindow vertical(int half);

  bool contains(int value) const;
  int offset() const {
    return offset_;
  }
  int bound() const {
    return bound_;
  }

private:
  ScreenWindow(int offset, int bound) : offset_(offset), bound_(bound) {}

  int offset_;
  int bound_;
};

// One coordinate as the recovered body held it: `raw` is the 32-bit register (zero-extended u16 terms
// subtracted), `value` its low sixteen bits read as the s16 the window states.
struct ScreenCoordinate {
  std::int32_t raw;
  int value;
};

// ── the owner ───────────────────────────────────────────────────────────────────────────────────
// One concept: recover an object's screen-space position from the camera layers, decide the cull, and
// publish the decision the way the recovered site publishes it. No globals and no stored Core; the
// latched plan is taken by the caller and narrowed to the single term that varies.
class VisibilityCull {
public:
  // `plan.presentationHorizontalMargin` is the framework's own 2D layout shift. It is already 0
  // whenever the presentation is 4:3, whenever the widescreen knob is off, and on a typed comparison
  // run, because all three are resolved before the plan reaches this constructor.
  explicit VisibilityCull(const GuestProjectionPlan &plan) : margin_(plan.presentationHorizontalMargin) {}

  // 0 at 4:3, with the enhancement off, and on a typed comparison run — the plan already resolves all
  // three, so this owner needs no second gate and cannot disagree with the draw path.
  int horizontalMargin() const {
    return margin_ > 0 ? margin_ : 0;
  }

  static LayoutOffsets offsetsFor(ObjectLayout layout);

  // The recovered world-to-screen recovery: a negative background byte means the object is already in
  // screen space, otherwise the named camera layer's scroll is subtracted from the position.
  ScreenCoordinate screenX(Core &core, std::uint32_t object, ObjectLayout layout, BackgroundSource source) const;
  ScreenCoordinate screenY(Core &core, std::uint32_t object, ObjectLayout layout, BackgroundSource source) const;

  // The one recovered predicate. `half` is the site's recovered per-side slack in pixels; the quad's
  // four corners pass 0, which is exactly what makes their retail window carry no slack at all.
  bool inside(int screenX, int screenY, int halfWidth, int halfHeight) const;

  // quad_is_on_screen: the object is admitted when ANY of its four corners is inside the zero-slack
  // box. Each corner's coordinate is its extent plus the object position, in the same 16-bit
  // arithmetic the body uses.
  bool quadOnScreen(Core &core, std::uint32_t object) const;

  void publishOnScreen(Core &core, std::uint32_t object, bool onScreen) const;

private:
  int layerFor(Core &core, std::uint32_t object, ObjectLayout layout, BackgroundSource source) const;
  std::uint32_t scrollBits(Core &core, int layer, std::uint32_t field) const;

  int margin_;
};

// ── the measured sites ───────────────────────────────────────────────────────────────────────────
// One row per cull owner: the guest entry point, the recovered per-side slack, whether the site
// PUBLISHES the on_screen flag or RETURNS a value, what a returned 1 means, and where its scroll
// comes from. This table is the owner's binding of guest address to recovered parameters, and the
// adapters below take their slack and polarity from it rather than repeating them, so there is one
// place to be wrong. Every row is re-derivable from SLUS_005.61 — the address, the
// `addiu` addend and the `sltiu` bound at each one — and fails the gate if the image disagrees.
struct MeasuredSite {
  std::uint32_t address;
  int halfWidth;         // pixels of slack per side; -1 when the site takes it in a guest register
  int halfHeight;        // pixels of slack per side; -1 likewise, and NOT always equal to halfWidth
  bool writesFlag;       // publishes on_screen, rather than returning a value
  bool returnsOffScreen; // the value it returns is 1 when the object is OFF screen
  bool layerZeroScroll;  // ignores the object's own background byte and always uses camera layer 0
};

// func_8002B160 (external/mmx4/src/main/1A5BC.c:597) — the fixed 64/64 test, returning OFF-screen. Its
// return value IS read by callers (`== 0` at BBE34.c:247, effect_objs.c:178, shot_objs.c:444).
inline constexpr MeasuredSite kBaseOffScreenLoose{
    0x8002B160u, RetailSlack::kLoose, RetailSlack::kLoose, false, true, false};
// func_8002B1E8 (1A5BC.c:599) — the parametric form of the same, with the half-extents in $5/$6.
inline constexpr MeasuredSite kBaseOffScreenParametric{0x8002B1E8u, -1, -1, false, true, false};
// is_on_screen (1A5BC.c:601) — 32/32 slack, publishing the flag the draw pass reads. 279 call sites.
inline constexpr MeasuredSite kBaseOnScreenTight{
    0x8002B288u, RetailSlack::kTight, RetailSlack::kTight, true, false, false};
// func_8002B318 (1A5BC.c:620) — parametric, publishing. 403 call sites, the most-used cull in the game.
inline constexpr MeasuredSite kBaseOnScreenParametric{0x8002B318u, -1, -1, true, false, false};
// func_8002B3C0 (1A5BC.c:622) — ASYMMETRIC 96/80 slack. `kWideX` and `kWideY` are separate constants
// precisely because of this row; collapsing them to one number is a different predicate.
inline constexpr MeasuredSite kBaseOnScreenWide{
    0x8002B3C0u, RetailSlack::kWideX, RetailSlack::kWideY, true, false, false};
// 0x800B8490 (external/mmx4/src/main/A7878.c:88) — the fixed 64/64 test as its own body, and the one
// site that loads 0x801419BA / 0x801419BE without ever reading +0x14.
inline constexpr MeasuredSite kBaseOffScreenLayerZero{
    0x800B8490u, RetailSlack::kLoose, RetailSlack::kLoose, false, true, true};
// quad_is_on_screen (external/mmx4/src/main/C49B0.c:19) — four corners, ZERO slack, publishing.
inline constexpr MeasuredSite kQuadOnScreen{0x800D46F4u, 0, 0, true, false, false};

inline constexpr MeasuredSite kMeasuredSites[] = {
    kBaseOnScreenTight,
    kBaseOnScreenWide,
    kBaseOnScreenParametric,
    kBaseOffScreenParametric,
    kBaseOffScreenLoose,
    kBaseOffScreenLayerZero,
    kQuadOnScreen,
};

// Registering the measured sites against the native seam is cull_overrides.h's job, deliberately: this
// header is the predicate, and it must stay reachable without the guest dispatcher so its 4:3 identity
// can be proven exhaustively.

} // namespace x4::cull
