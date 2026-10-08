// SPDX-License-Identifier: AGPL-3.0-or-later
// derived from external/mmx4
// vram_rect_queue.h - the guest's eight-entry VRAM rectangle upload queue; the appender has no capacity test.
#pragma once

#include <cstdint>

class Core;

namespace x4::vram_rect {

// Queue layout.
// `lui/addiu 0x59D0` @ 0x80015E10 (clear), 0x80015E60 (upload).
inline constexpr std::uint32_t kQueueBase = 0x801659D0u;
// `addiu $3,$s0,0x60` @ 0x80015E64; also item_objects[0].
inline constexpr std::uint32_t kQueueEnd = kQueueBase + 0x60u;
// `sltiu 8` @ 0x80015E40.
inline constexpr std::uint32_t kEntryCapacity = 8u;
// `addiu 0xc` @ 0x80015E38 / 0x80015E94: sizeof(RECT) + sizeof(void*).
inline constexpr std::uint32_t kEntryStride = 12u;
// Append cursor; written only by clear (0x80015E18), upload (0x80015EB0) and append (0x80015FE0).
inline constexpr std::uint32_t kCursorGlobal = 0x80141F68u;
// Structure right after the queue.
inline constexpr std::uint32_t kItemObjectsBase = kQueueEnd;
inline constexpr std::uint32_t kItemStride = 0x8Cu;
inline constexpr std::uint32_t kItemCount = 0x20u;

// Guest entry points replaced.
inline constexpr std::uint32_t kClearQueueGuest = 0x80015E0Cu;  // clear_vram_rect_ptrs
inline constexpr std::uint32_t kUploadQueueGuest = 0x80015E54u; // load_vram_rect_ptrs
inline constexpr std::uint32_t kAppendBandsGuest = 0x80015ECCu; // decompress_player_gfx

// The decompressor stays a guest call since it owns the compression format; LoadImage is called @ 0x80015E8C.
inline constexpr std::uint32_t kDecompressGfxGuest = 0x80016FF4u;
inline constexpr std::uint32_t kLoadImageGuest = 0x800EA4D0u;

// Return points (jal + 8) for the two nested guest calls; they must be explicit because r[31] holds an
// unrelated caller's link when the override runs.
inline constexpr std::uint32_t kDecompressGfxReturn = 0x80015F5Cu;  // `jal` at 0x80015F54
inline constexpr std::uint32_t kLoadImageGuestReturn = 0x80015E94u; // `jal` at 0x80015E8C

// Appender constants.
// Animation word `lw` @ 0x80015F14; `srl 0x14` @ 0x80015F20 gives a 12-bit band count.
inline constexpr std::uint32_t kBandCountShift = 20u;
inline constexpr std::uint32_t kBandCountMask = 0xFFFu;
// 16-bit stream offset (`ori 0xffff` @ 0x80015F48); the reference decomp prints 0xFFFFF.
inline constexpr std::uint32_t kStreamOffsetMask = 0xFFFFu;
// Buffers formed @ 0x80015F24-0x80015F28 (shared) and 0x80015F38-0x80015F3C (per slot, `sll 0xc` @ 0x80015F34).
inline constexpr std::uint32_t kSharedGfxBuffer = 0x8016DEA8u;
inline constexpr std::uint32_t kPerSlotGfxBuffer = 0x8016EEA8u;
inline constexpr std::uint32_t kGfxBufferStride = 0x1000u;
inline constexpr std::int32_t kSharedGfxSlot = 3; // `lb $3,0x49($4)` / `addiu $2,$zero,3` + `bne`
// `addiu 0x10` @ 0x80015F64 and `slti 0x10` @ 0x80015F78.
inline constexpr std::int32_t kBandHeight = 16;
// `addiu 0x40` @ 0x80015F68.
inline constexpr std::int32_t kFullBandWidth = 0x40;
// `addiu 0x800` @ 0x80015FC4.
inline constexpr std::uint32_t kFullBandSourceBytes = 0x800u;

// Registers the guest bodies leave behind; sp and s0-s3 keep entry values (epilogue reloads them).
// Clearer 0x80015E0C-0x80015E4C; terminal loop counters:
//   a0 = kQueueBase + 8*12     `lui a0,0x8016` / `addiu a0,a0,0x59D0` then 8x `addiu a0,a0,0xc` (0x80015E48)
//   a1 = 8                      8x `addiu a1,a1,1` (0x80015E3C)
//   v0 = 0                      `sltiu v0,a1,8` (0x80015E40) with a1 already 8
//   v1 = kQueueBase + 8 + 8*12  `addiu v1,a0,8` (0x80015E20) then 8x `addiu v1,v1,0xc` (0x80015E38)
//   at = 0x8014                 `lui at,0x8014` (0x80015E14)
inline constexpr std::uint32_t kClearFinalA0 = kQueueEnd;      // == kQueueBase + 8*12
inline constexpr std::uint32_t kClearFinalV1 = kQueueEnd + 8u; // == kQueueBase + 8 + 8*12
inline constexpr std::uint32_t kClearFinalV0 = 0u;
inline constexpr std::uint32_t kClearFinalA1 = kEntryCapacity;
// `lui at,0x8014`, left by clear and upload.
inline constexpr std::uint32_t kGuestPage8014 = 0x8014u;

// Uploader 0x80015E54-0x80015EB4; a0/a1 are clobbered by LoadImage as in the guest.
inline constexpr std::uint32_t kUploadFinalV0 = kQueueBase; // `lui v0,0x8016` / `addiu v0,v0,0x59d0` (0x80015EA4/8)
inline constexpr std::uint32_t kUploadFinalV1 = kQueueEnd;  // `addiu v1,s0,0x60` (0x80015E64), never rewritten

// Appender 0x80015ECC-0x80015FFC at loop exit (`bnez` @ 0x80015FD0); v1 is the last head band count.
inline constexpr std::uint32_t kAppendFinalV0 = 0u;
inline constexpr std::uint32_t kAppendFinalA2 = kFullBandWidth; // `addiu a2,zero,0x40` (0x80015F68)
inline constexpr std::uint32_t kAppendFinalA3 = kBandHeight;    // `addiu a3,zero,0x10` (0x80015F64)
// The early return @ 0x80015EF4 leaves the two compared bytes in v1/v0.
inline constexpr std::uint32_t kCurrentAnimRegister = 3;  // $v1
inline constexpr std::uint32_t kPreviousAnimRegister = 2; // $v0
// `lbu 0x47/0x48` @ 0x80015EE8-0x80015EEC, `beq` @ 0x80015EF4: unchanged animation index returns early.
inline constexpr std::uint32_t kCurrentAnimOffset = 0x47u;
inline constexpr std::uint32_t kPreviousAnimOffset = 0x48u;
// `lb 0x49` @ 0x80015F08, signed.
inline constexpr std::uint32_t kGfxSlotOffset = 0x49u;
// `lw 0x38` @ 0x80015F00: the compressed blob.
inline constexpr std::uint32_t kBlobOffset = 0x38u;
// Guest per-field counter, used to label census entries.
inline constexpr std::uint32_t kFieldCounter = 0x80141BD8u;

// `struct RectPtrPair { RECT rect; u32 pixels; }`; the stores are `sh` @ 0x80015F7C/0x80015F80/
// 0x80015F94/0x80015F9C (+ full band 0x80015FA8/0x80015FB8) and `sw` @ 0x80015F88.
struct Rect {
  std::int16_t x = 0;
  std::int16_t y = 0;
  std::int16_t w = 0;
  std::int16_t h = 0;
};
struct Entry {
  Rect rect;
  std::uint32_t pixels = 0;
};
static_assert(sizeof(Rect) == 8);
static_assert(sizeof(Entry) == kEntryStride);
static_assert(kQueueEnd == kItemObjectsBase, "the queue's end IS the first item object");
static_assert(kQueueEnd - kQueueBase == kEntryCapacity * kEntryStride,
              "the queue holds exactly kEntryCapacity records");
static_assert(kGfxBufferStride == 0x1000u, "the per-slot graphics stride is 0x1000 bytes");
static_assert(kBandHeight == 0x10, "the trailing-band threshold is the band height");
static_assert((0xFFFFFFFFu >> kBandCountShift) == ((1u << (32u - kBandCountShift)) - 1u),
              "the band count is masked to the twelve bits the shift leaves above it");

// One append call, recorded for the census.
struct Append {
  std::uint32_t field = 0;   // the guest's own field counter
  std::uint32_t caller = 0;  // the guest return address — which of the 17 call sites
  std::uint32_t object = 0;  // the object whose graphics were decompressed
  std::int32_t x = 0;        // the caller's rectangle x
  std::int32_t y = 0;        // the caller's rectangle y
  std::uint32_t emitted = 0; // entries this call appended
  std::uint32_t refused = 0; // entries this call could not append, capacity reached
};

// Installs the three native overrides.
void install(Core &core);

// Zeroes all kEntryCapacity entries and republishes kQueueBase.
void clear(Core &core);

// LoadImages every entry with a non-null source in order, then republishes kQueueBase.
void upload(Core &core);

// One 16-pixel band per entry; reached from 17 guest call sites.
void append(Core &core, std::uint32_t object, std::int32_t x, std::int32_t y);

// Run census; `calls` includes calls that emitted nothing.
struct Census {
  std::uint64_t calls = 0;
  std::uint64_t emitted = 0;
  std::uint64_t refused = 0;
  std::uint64_t clears = 0;
  std::uint64_t uploads = 0;
  std::uint64_t uploadedEntries = 0;
};
Census census();
void reportCensus(const char *why);

} // namespace x4::vram_rect
