// SPDX-License-Identifier: AGPL-3.0-or-later
// derived from external/mmx4
//
// vram_rect_queue.h — the native owner of the guest's VRAM rectangle upload queue.
//
// WHAT THIS OWNS, and why it is the owner rather than a lens. The guest keeps an eight-entry queue
// of `RECT` + source-pointer pairs at `kQueueBase` and a published append cursor in guest RAM. Three
// guest functions touch it: `clear` (zero all eight, republish the base), `upload` (LoadImage every
// entry whose source pointer is non-null, then republish the base), and `append` (decompress one
// object's graphics and emit one `RECT` per 16-pixel band).
//
// The appender has NO capacity test anywhere in its 75 instructions, and its post-loop terminator
// store lands on `&entry[emitted]` — the slot AFTER the last one it wrote. `kQueueEnd` is
// `item_objects[0]`, the first record of the next guest structure, so:
//
//   * emitting an entry at index 8 overwrites `item_objects[0].active/id/x/y` with rectangle data;
//   * emitting exactly 8 entries — the queue's DESIGNED capacity — and then running the terminator
//     store zeroes `item_objects[0].x_pos` at +8.
//
// Neither is a hypothetical. The first is the stage-load fault of docs/issues/0034. The
// second fires on every field that fills the queue, and is a property of the appender rather than of
// any particular object state. The bound is a LAYOUT fact, not a guess: `kQueueEnd` is exactly eight
// 12-byte records past `kQueueBase`, and the guest's own `clear` (`sltiu $2,$5,8` at 0x80015E40) and
// `upload` (`addiu $3,$s0,0x60` at 0x80015E64) both state eight.
//
// Every constant below names the instruction in the authenticated SLUS_005.61 that materialises it,
// so any word, immediate or address can be checked against the image. The
// AGPL-3.0 reference decompilation (external/mmx4) supplied the structure NAMES and the loop shape;
// the C++ here is this repository's own, and no decompiled text is shipped.
#pragma once

#include <cstdint>

class Core;

namespace x4::vram_rect {

// ── the queue's own layout, measured ──────────────────────────────────────────────────────────

// `lui $4,0x8016 / addiu $4,$4,0x59D0` at 0x80015E10 (clear) and `lui $s0,0x8016 / addiu $s0,$s0,0x59d0`
// at 0x80015E60 (upload).
inline constexpr std::uint32_t kQueueBase = 0x801659D0u;
// `addiu $3,$s0,0x60` at 0x80015E64 — the end, which is also `item_objects[0]`.
inline constexpr std::uint32_t kQueueEnd = kQueueBase + 0x60u;
// `sltiu $2,$5,0x8` at 0x80015E40 — the clear's own trip count.
inline constexpr std::uint32_t kEntryCapacity = 8u;
// `addiu $v1,$v1,0xc` at 0x80015E38 and `addiu $s0,$s0,0xc` at 0x80015E94: the record stride is 12
// bytes, which is `sizeof(RECT) + sizeof(void*)` and nothing else.
inline constexpr std::uint32_t kEntryStride = 12u;
// The append cursor global. Written by all three guest functions: `sw $a0,0x1f68($at)` at
// 0x80015E18 (clear), `sw $v0,0x1f68($at)` at 0x80015EB0 (upload), `sw $a1,0x1f68($at)` at 0x80015FE0
// (append). No other instruction in .text writes this word.
inline constexpr std::uint32_t kCursorGlobal = 0x80141F68u;
// The structure immediately after the queue, whose first record is the queue's end address.
inline constexpr std::uint32_t kItemObjectsBase = kQueueEnd;
inline constexpr std::uint32_t kItemStride = 0x8Cu;
inline constexpr std::uint32_t kItemCount = 0x20u;

// ── the guest entry points this owner replaces ────────────────────────────────────────────────

inline constexpr std::uint32_t kClearQueueGuest = 0x80015E0Cu;  // clear_vram_rect_ptrs
inline constexpr std::uint32_t kUploadQueueGuest = 0x80015E54u; // load_vram_rect_ptrs
inline constexpr std::uint32_t kAppendBandsGuest = 0x80015ECCu; // decompress_player_gfx

// The run-length decompressor stays a guest call: it is a leaf at 0x80016FF4 that owns the
// compression format, and reimplementing it here would duplicate a format rather than own behaviour.
// The BIOS `LoadImage` entry the uploader calls is `jal 0x800EA4D0` at 0x80015E8C.
inline constexpr std::uint32_t kDecompressGfxGuest = 0x80016FF4u;
inline constexpr std::uint32_t kLoadImageGuest = 0x800EA4D0u;

// The return points for the two guest calls this owner stands in for. A `jal` links `$ra` to PC+8
// because of the delay slot, so the return address is `jal + 8`; both values below are the call
// sites this owner's own comments already named, and both are reproducible from the image:
// the decompressor's is the ONLY `jal` targeting 0x80016FF4 in
// 294,400 words, so it is the call and not a candidate; LoadImage has 11 sites, and this is the one
// at 0x80015E8C that this owner documents.
//
// These are required, not cosmetic. `x4::guest::call` used to take its boundary from `core->r[31]`,
// which is a return address only when GUEST code executed the `jal`; a native owner inherited
// whatever the guest last left, and the decompress call inherited 0x80022060 - the return address of
// an unrelated `jal 0x80015ecc`. It could not return there, ran 757,804 cycles past its own end and
// faulted at a non-address.
inline constexpr std::uint32_t kDecompressGfxReturn = 0x80015F5Cu;  // `jal` at 0x80015F54
inline constexpr std::uint32_t kLoadImageGuestReturn = 0x80015E94u; // `jal` at 0x80015E8C

// ── the appender's own constants, measured ───────────────────────────────────────────────────

// The per-object animation word: `lw $5,0($2)` at 0x80015F14 with `$2 = unk38 + unk47*4`.
// `srl $16,$5,0x14` at 0x80015F20 takes the band count from bits 20..31 — TWELVE bits, so the
// band's signedness test at 0x80015FA4 (`bgez`) can never take its negative arm.
inline constexpr std::uint32_t kBandCountShift = 20u;
inline constexpr std::uint32_t kBandCountMask = 0xFFFu;
// The compressed-stream offset inside the object's blob. `ori $4,$4,0xffff` at 0x80015F48 followed
// by `and $4,$5,$4` at 0x80015F4C: the mask is SIXTEEN bits, and the gate says so out loud because
// the reference decompilation prints 0xFFFFF. A 20-bit mask would let the offset run a megabyte past
// the blob, so this is a constant the image had to be asked about, not one that could be read off.
inline constexpr std::uint32_t kStreamOffsetMask = 0xFFFFu;
// The decompressed buffer. `lui $17,0x8017 / addiu $17,$17,-0x2158` at 0x80015F24-0x80015F28 forms
// 0x8016DEA8 for the shared slot; `lui $2,0x8017 / addiu $2,$2,-0x1158` at 0x80015F38-0x80015F3C forms
// 0x8016EEA8, indexed by `sll $3,$3,0xc` at 0x80015F34.
inline constexpr std::uint32_t kSharedGfxBuffer = 0x8016DEA8u;
inline constexpr std::uint32_t kPerSlotGfxBuffer = 0x8016EEA8u;
inline constexpr std::uint32_t kGfxBufferStride = 0x1000u;
inline constexpr std::int32_t kSharedGfxSlot = 3; // `lb $3,0x49($4)` / `addiu $2,$zero,3` + `bne`
// `addiu $7,$zero,0x10` at 0x80015F64 — the trailing band's height, and the `size < 16` threshold
// (`slti $2,$3,0x10` at 0x80015F78).
inline constexpr std::int32_t kBandHeight = 16;
// `addiu $6,$zero,0x40` at 0x80015F68 — a full band's rectangle width, stored for `size >= 16`.
inline constexpr std::int32_t kFullBandWidth = 0x40;
// `addiu $17,$17,0x800` at 0x80015FC4 — one band's decompressed source advance, 16 pixels of 4-bit
// TIM data as 16-bit words.
inline constexpr std::uint32_t kFullBandSourceBytes = 0x800u;

// ── the register file each guest body leaves behind ──────────────────────────────────────────
//
// The override differential (psxport 0138) compares `v0`, `v1` and the callee-saved set, and it
// found this owner's first version leaving `v1` and `v0` holding whatever the CALLER had. That is a
// real fidelity defect and not a formal one: these are three guest functions replacing three guest
// functions, and a body that does not leave the registers its original leaves is a different
// function. The values below are the loop counters' terminal values, read out of the bytes.
//
// `sp` and `s0`-`s3` are NOT listed: the guest's own epilogue reloads them from the frame
// (`lw ra,32(sp)` / `lw s3,28(sp)` / `lw s2,24(sp)` / `lw s1,20(sp)` / `lw s0,16(sp)` at
// 0x80015FE4-0x80015FF4), so the guest leaves them at their ENTRY values and so does this owner by
// not touching them.
//
// The clearer, 0x80015E0C-0x80015E4C. Its loop runs exactly kEntryCapacity times, so the counters
// are terminal by construction rather than by observation:
//   a0 = kQueueBase + 8*12     `lui a0,0x8016` / `addiu a0,a0,0x59D0` then 8x `addiu a0,a0,0xc` (0x80015E48)
//   a1 = 8                      8x `addiu a1,a1,1` (0x80015E3C)
//   v0 = 0                      `sltiu v0,a1,8` (0x80015E40) with a1 already 8
//   v1 = kQueueBase + 8 + 8*12  `addiu v1,a0,8` (0x80015E20) then 8x `addiu v1,v1,0xc` (0x80015E38)
//   at = 0x8014                 `lui at,0x8014` (0x80015E14)
inline constexpr std::uint32_t kClearFinalA0 = kQueueEnd;      // == kQueueBase + 8*12
inline constexpr std::uint32_t kClearFinalV1 = kQueueEnd + 8u; // == kQueueBase + 8 + 8*12
inline constexpr std::uint32_t kClearFinalV0 = 0u;
inline constexpr std::uint32_t kClearFinalA1 = kEntryCapacity;
// The page both the clearer and the uploader leave in `at`, from `lui at,0x8014`.
inline constexpr std::uint32_t kGuestPage8014 = 0x8014u;

// The uploader, 0x80015E54-0x80015EB4. `a0`/`a1` need no publishing: the guest sets them to the
// entry and its source pointer and then `jal`s LoadImage, so the BIOS B-call clobbers them, and this
// owner makes the same call with the same arguments and gets the same clobber.
inline constexpr std::uint32_t kUploadFinalV0 = kQueueBase; // `lui v0,0x8016` / `addiu v0,v0,0x59d0` (0x80015EA4/8)
inline constexpr std::uint32_t kUploadFinalV1 = kQueueEnd;  // `addiu v1,s0,0x60` (0x80015E64), never rewritten

// The appender, 0x80015ECC-0x80015FFC, on BOTH exits from its band loop. The loop's back edge is
// `bnez v0,0x80015F74` at 0x80015FD0 with `sll v0,s0,0x10` at 0x80015FCC, so on exit `v0` is zero in
// both the trailing-band arm (which sets `s0` to zero at 0x80015F8C) and the full-band arm (which
// subtracts the band height until it reaches zero). `v1` is whatever the LAST loop head read, so it
// is the band count that iteration was entered with — the owner has to hand that back, and it is
// the register the differential compares.
inline constexpr std::uint32_t kAppendFinalV0 = 0u;
inline constexpr std::uint32_t kAppendFinalA2 = kFullBandWidth; // `addiu a2,zero,0x40` (0x80015F68)
inline constexpr std::uint32_t kAppendFinalA3 = kBandHeight;    // `addiu a3,zero,0x10` (0x80015F64)
// The appender's EARLY return, taken at 0x80015EF4 before it decompresses anything, leaves the two
// bytes it just compared: `lbu v1,0x47($a0)` and `lbu v0,0x48($a0)` at 0x80015EE8/0x80015EEC.
inline constexpr std::uint32_t kCurrentAnimRegister = 3;  // $v1
inline constexpr std::uint32_t kPreviousAnimRegister = 2; // $v0
// `lbu $3,0x47($4)` / `lbu $2,0x48($4)` at 0x80015EE8-0x80015EEC and `beq $2,$3,0x80015FE4` at
// 0x80015EF4: the appender returns immediately when the object's animation index has not changed.
inline constexpr std::uint32_t kCurrentAnimOffset = 0x47u;
inline constexpr std::uint32_t kPreviousAnimOffset = 0x48u;
// `lb $3,0x49($4)` at 0x80015F08 — SIGNED, and `sll $3,$3,0xc` makes a negative slot wrap below
// the per-slot base, which is why the guest compares it against 3 first.
inline constexpr std::uint32_t kGfxSlotOffset = 0x49u;
// `lw $6,0x38($4)` at 0x80015F00 — the object's compressed blob.
inline constexpr std::uint32_t kBlobOffset = 0x38u;
// The guest's own per-field counter, `D_80141BD8.unk0++` at x4_frame_driver.cpp. Read to label a
// census entry with the field it happened in; it is not part of the queue's own state.
inline constexpr std::uint32_t kFieldCounter = 0x80141BD8u;

// ── the recovered record ─────────────────────────────────────────────────────────────────────

// `struct RectPtrPair { RECT rect; u32 pixels; }` — RECT is four little-endian s16 at +0..+7 and
// the source pointer at +8, which is the 12 bytes the guest's stores actually write:
//   `sh $19,0($5)`      rect.x      0x80015F7C
//   `sh $18,-4($4)`     rect.y      0x80015F80   ($4 is $5+6)
//   `sh $2,-2($4)`      rect.w      0x80015F94   (trailing band)  /  0x80015FA8 (full band)
//   `sh $7,0($4)`       rect.h      0x80015F9C   (trailing band)  /  0x80015FB8 (full band)
//   `sw $17,2($4)`      pixels      0x80015F88
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
// The relation the whole mitigation rests on, checked where it is written rather than only in the
// gate. If a future edit moves either address by a single entry the build stops here.
static_assert(kQueueEnd == kItemObjectsBase, "the queue's end IS the first item object");
static_assert(kQueueEnd - kQueueBase == kEntryCapacity * kEntryStride,
              "the queue holds exactly kEntryCapacity records");
static_assert(kGfxBufferStride == 0x1000u, "the per-slot graphics stride is 0x1000 bytes");
static_assert(kBandHeight == 0x10, "the trailing-band threshold is the band height");
static_assert((0xFFFFFFFFu >> kBandCountShift) == ((1u << (32u - kBandCountShift)) - 1u),
              "the band count is masked to the twelve bits the shift leaves above it");

// One appended call, as the owner saw it. The owner records every emission so a census has a
// denominator and an attribution, which is the whole reason the owner exists rather than a clamp.
struct Append {
  std::uint32_t field = 0;   // the guest's own field counter
  std::uint32_t caller = 0;  // the guest return address — which of the 17 call sites
  std::uint32_t object = 0;  // the object whose graphics were decompressed
  std::int32_t x = 0;        // the caller's rectangle x
  std::int32_t y = 0;        // the caller's rectangle y
  std::uint32_t emitted = 0; // entries this call appended
  std::uint32_t refused = 0; // entries this call could not append, capacity reached
};

// ── the owner ─────────────────────────────────────────────────────────────────────────────────

// Install the three native overrides against the active authenticated image.
void install(Core &core);

// The recovered `clear`: zero all kEntryCapacity entries and republish kQueueBase.
void clear(Core &core);

// The recovered `upload`: LoadImage every entry whose source pointer is non-null, in array order,
// then republish kQueueBase. This is the guest's ONLY bound on the queue — `addiu $3,$s0,0x60` and
// `sltu` at 0x80015E64/0x80015E68 — and it reads exactly kEntryCapacity entries.
void upload(Core &core);

// The recovered `append`: one 16-pixel band per entry, sources walking forward kFullBandSourceBytes
// per full band. This is the entry point the 17 guest call sites reach.
void append(Core &core, std::uint32_t object, std::int32_t x, std::int32_t y);

// The run's census, for the run-end report. `calls` counts every invocation that reached the
// appender, including the ones whose animation index had not moved and emitted nothing.
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
