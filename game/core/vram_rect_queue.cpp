// SPDX-License-Identifier: AGPL-3.0-or-later
// derived from external/mmx4
//
// vram_rect_queue.cpp — the native owner of the guest's VRAM rectangle upload queue.
//
// See vram_rect_queue.h for what is owned and why. The recovery is from the authenticated
// SLUS_005.61 bytes; every constant in the header carries the instruction that materialises it.
// The AGPL-3.0 reference decompilation supplied structure names and the loop shape; the
// C++ below is this repository's own.
#include "vram_rect_queue.h"

#include "core.h"
#include "native_dispatch.h"
#include "resumable_guest_call.h"

#include <algorithm>
#include <cstdint>
#include <lucent/log.h>

namespace x4::vram_rect {
namespace {

Census stats;
std::uint32_t lastRefusalField = 0;
std::uint32_t reportedField = 0;
bool reportedThisField = false;

// The guest's band loop, recovered from 0x80015F74-0x80015FD4. `remaining` is the 12-bit band count
// from the animation word; the loop emits one entry per iteration and leaves when it reaches zero.
//
//   0x80015F74  sra  $3,$2,0x10      remaining = bands
//   0x80015F78  slti $2,$3,0x10      is this the trailing partial band?
//   0x80015F7C  sh   $19,0($5)       rect.x = x
//   0x80015F80  sh   $18,-4($4)      rect.y = y
//   0x80015F88  sw   $17,2($4)       pixels = source
//   trailing:   rect.w = remaining*4 (`sll $2,$3,2`), rect.h = 16 (`sh $7,0($4)`), remaining = 0
//   full:       rect.w = 64 (`sh $6,-2($4)`), rect.h = remaining & ~15 (`sra`/`sll` at 0x80015FB0/
//               0x80015FB4), y += height, remaining -= height, source += 0x800
//   0x80015FD4  addiu $5,$5,0xc      <- the delay slot of the loop branch at 0x80015FD0, so the
//                                       cursor advances once per ENTRY, not once per CALL
//
// That delay slot is the reading issues 0033 and 0034 got wrong, and it matters: the record pointer
// `$5` and the separate walk pointer `$4` both step 12 bytes per iteration, so one CALL can emit
// several entries and the cursor advances once per entry. Both docs read the instruction as a
// post-loop store.
//
// The `bgez` at 0x80015FA4 and its `addiu $2,$2,0xf` are the guest's negative-size arm. It is
// unreachable here and is not modelled: the count is `(word >> 20) & 0xFFF`, twelve bits, and the
// sign-extend at 0x80015F74 cannot set a sign. The gate proves the twelve-bit field.
void emitBands(
    Core &core, std::uint32_t source, std::int32_t x, std::int32_t y, std::int32_t remaining, Append &record) {
  std::uint32_t cursor = core.mem_r32(kCursorGlobal);
  std::int32_t top = y;
  // The band count the LAST loop head read into `$v1` (`sra $3,$2,0x10` at 0x80015F74). It is the
  // register the override differential compares, and it is not a function of anything the caller can
  // see — a two-band call ends with 0 and a 48-band call ends with 16 — so it has to be tracked.
  std::int32_t lastHeadCount = remaining;
  while (remaining != 0) {
    lastHeadCount = remaining;
    // THE BOUND, and the whole reason this owner exists. The guest's loop has no capacity test in
    // its 75 instructions; `kQueueEnd` is `item_objects[0]`, so an entry written at index
    // kEntryCapacity overwrites the first record of the next guest structure. The guest states eight
    // in two places (0x80015E40, 0x80015E64) and enforces it in neither the writer nor the writer's
    // terminator, so the array's real capacity is supplied here, once, at the only store that can
    // cross it.
    //
    // MEMBERSHIP, not an upper bound. A first version tested only `cursor >= kQueueEnd`, which is the
    // reading the fault forces into you and which is wrong: `kCursorGlobal` is a published global the
    // guest also writes, so a cursor BELOW kQueueBase is just as possible and an upper bound would
    // happily write rectangles over whatever is there. The array's extent is the whole contract.
    if (cursor < kQueueBase || cursor >= kQueueEnd) {
      record.refused += 1;
      break;
    }
    const bool trailing = remaining < kBandHeight;
    const std::int32_t height = trailing ? kBandHeight : (remaining & ~(kBandHeight - 1));
    Entry entry;
    entry.rect.x = static_cast<std::int16_t>(x);
    entry.rect.y = static_cast<std::int16_t>(top);
    entry.rect.w = static_cast<std::int16_t>(trailing ? remaining * 4 : kFullBandWidth);
    entry.rect.h = static_cast<std::int16_t>(height);
    entry.pixels = source;
    core.mem_w16(cursor + 0, static_cast<std::uint16_t>(entry.rect.x));
    core.mem_w16(cursor + 2, static_cast<std::uint16_t>(entry.rect.y));
    core.mem_w16(cursor + 4, static_cast<std::uint16_t>(entry.rect.w));
    core.mem_w16(cursor + 6, static_cast<std::uint16_t>(entry.rect.h));
    core.mem_w32(cursor + 8, entry.pixels);
    record.emitted += 1;
    stats.emitted += 1;

    if (trailing) {
      remaining = 0;
    } else {
      top += height;
      remaining -= height;
      source += kFullBandSourceBytes;
    }
    cursor += kEntryStride;
  }

  // The guest's `sw zero,8($5)` at 0x80015FD8, one entry past the last one written. At fewer than
  // kEntryCapacity entries it re-zeroes a slot `clear` already zeroed this field, so it is
  // redundant; at exactly kEntryCapacity it writes `item_objects[0].x_pos`. The same membership test
  // applies, and it must cover the whole record: the store is at `cursor + 8`, so a cursor one entry
  // from the end still reaches past it.
  if (cursor >= kQueueBase && cursor + kEntryStride <= kQueueEnd) {
    core.mem_w32(cursor + 8, 0u);
  }
  core.mem_w32(kCursorGlobal, cursor);

  // The guest's register file on the band-loop exit. `v0` is zero because the back edge's
  // `sll $2,$16,0x10` (0x80015FCC) computes it from a zero band count in both arms; `$5` and `$4` are
  // the advanced cursor (the record-walk pointer `$4` is `$5 + 6` at the loop head and steps with
  // it, so the two differ by 6 at ENTRY to an iteration and are equal at EXIT); `$6` and `$7` are the
  // two literals the loop set up before entering; `at` is the page the publish used.
  core.r[1] = kGuestPage8014;
  core.r[2] = kAppendFinalV0;
  core.r[3] = static_cast<std::uint32_t>(lastHeadCount);
  core.r[4] = cursor;
  core.r[5] = cursor;
  core.r[6] = kAppendFinalA2;
  core.r[7] = kAppendFinalA3;
}

// `lui $17,0x8017 / addiu $17,$17,-0x2158` at 0x80015F24 for the shared slot, and
// `sll $3,$3,0xc` at 0x80015F34 over the signed slot byte for every other one. A negative slot wraps
// BELOW kPerSlotGfxBuffer, which is the guest's own arithmetic and is reproduced rather than clamped.
std::uint32_t decompressedBuffer(Core &core, std::uint32_t object) {
  const std::int32_t slot = core.mem_r8s(object + kGfxSlotOffset);
  if (slot == kSharedGfxSlot) {
    return kSharedGfxBuffer;
  }
  return kPerSlotGfxBuffer + static_cast<std::uint32_t>(slot * static_cast<std::int32_t>(kGfxBufferStride));
}

void runGuest(
    Core &core, std::uint32_t entry, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1, std::uint32_t caller) {
  // `$31` is the caller's link register while the nested call runs, and it is RESTORED afterwards.
  // Restoring it is not tidiness: the guest body saves and reloads `$ra` from its own frame
  // (`sw ra,0x20(sp)` at 0x80015ED8 / `lw ra,0x20(sp)` at 0x80015FE4), so the guest leaves `$31`
  // exactly as it found it, and the override differential compares `ra` as a continuation register.
  // Leaving `$31` holding the decompressor's return point was measured as a mismatch on the first
  // sampled call that did any work — 1 mismatch in 32 samples, 31 matches, and ZERO memory bytes
  // differing. A register clobber that only appears when the sampled call does real work is
  // precisely what a per-call gate catches and a run-time observation cannot.
  const std::uint32_t savedLink = core.r[31];
  core.r[4] = a0;
  core.r[5] = a1;
  // The nested guest call returns to the return address the OVERRIDE was entered with, so a `jr $ra`
  // out of the callee lands on the dispatcher's boundary exactly as the guest's own `jal` would.
  core.r[31] = caller;
  psx::cpu::callGuestToReturnResuming(core, "vram_rect::flushRect", entry, returnPc);
  core.r[31] = savedLink;
}

} // namespace

void clear(Core &core) {
  stats.clears += 1;
  core.mem_w32(kCursorGlobal, kQueueBase);
  for (std::uint32_t index = 0; index < kEntryCapacity; ++index) {
    const std::uint32_t entry = kQueueBase + index * kEntryStride;
    core.mem_w16(entry + 0, 0u);
    core.mem_w16(entry + 2, 0u);
    core.mem_w16(entry + 4, 0u);
    core.mem_w16(entry + 6, 0u);
    core.mem_w32(entry + 8, 0u);
  }
  // The register file the guest's loop leaves. See the header for each value's instruction: without
  // this the override differential reports `v1` differing, and it is right to.
  core.r[1] = kGuestPage8014;
  core.r[2] = kClearFinalV0;
  core.r[3] = kClearFinalV1;
  core.r[4] = kClearFinalA0;
  core.r[5] = kClearFinalA1;
}

void upload(Core &core) {
  stats.uploads += 1;
  const std::uint32_t caller = core.r[31];
  for (std::uint32_t index = 0; index < kEntryCapacity; ++index) {
    const std::uint32_t entry = kQueueBase + index * kEntryStride;
    const std::uint32_t pixels = core.mem_r32(entry + 8);
    if (pixels == 0u) {
      continue;
    }
    // `jal 0x800EA4D0` at 0x80015E8C with `$0 = &entry` and `$1 = entry->pixels`. The RECT is read
    // out of guest memory by the callee, so the entry has to be written before the call, which is
    // what makes this an owner rather than a buffer it could build on the stack.
    runGuest(core, kLoadImageGuest, kLoadImageGuestReturn, entry, pixels, caller);
    stats.uploadedEntries += 1;
  }
  core.mem_w32(kCursorGlobal, kQueueBase);
  // `at` and `v0` from 0x80015EAC/0x80015EA4/8, `v1` from 0x80015E64. `a0`/`a1` are the last BIOS
  // B-call's clobber in both paths, so publishing them here would BREAK the match.
  core.r[1] = kGuestPage8014;
  core.r[2] = kUploadFinalV0;
  core.r[3] = kUploadFinalV1;
}

void append(Core &core, std::uint32_t object, std::int32_t x, std::int32_t y) {
  stats.calls += 1;
  const std::uint32_t caller = core.r[31];
  Append record;
  record.field = core.mem_r32(kFieldCounter);
  record.caller = caller;
  record.object = object;
  record.x = x;
  record.y = y;

  // `lbu $3,0x47($4)` / `lbu $2,0x48($4)` and `beq $2,$3,0x80015FE4` — the appender returns before it
  // decompresses anything when the object's animation index has not moved this field. `sb $3,0x48($4)`
  // at 0x80015F04 is the latching that makes "moved" mean "moved".
  const std::uint32_t current = core.mem_r8(object + kCurrentAnimOffset);
  const std::uint32_t previous = core.mem_r8(object + kPreviousAnimOffset);
  // The early return still executes the `beq`'s delay slot, `move $19,$5` at 0x80015EF8, and `$19` is
  // reloaded from the frame by the epilogue, so only the two compared bytes survive. Publishing them
  // is what makes the early return register-identical to the guest's.
  core.r[kCurrentAnimRegister] = current;
  core.r[kPreviousAnimRegister] = previous;
  if (current == previous) {
    return;
  }
  core.mem_w8(object + kPreviousAnimOffset, static_cast<std::uint8_t>(current));

  const std::uint32_t blob = core.mem_r32(object + kBlobOffset);
  const std::uint32_t word = core.mem_r32(blob + current * 4u);
  const std::int32_t bands = static_cast<std::int32_t>((word >> kBandCountShift) & kBandCountMask);
  const std::uint32_t stream = blob + (word & kStreamOffsetMask);
  const std::uint32_t buffer = decompressedBuffer(core, object);

  // `jal 0x80016FF4` at 0x80015F54 with `$0 = blob + (word & 0xFFFFF)` and `$1 = buffer`. The
  // decompressor is a leaf that owns the compression format, so it stays a guest call: this owner
  // owns what the queue DOES with the result, not the format.
  //
  // The return point is `jal + 8` = 0x80015F5C, because a `jal` links `$ra` to PC+8 (the delay slot).
  // It is the ONLY `jal` in the whole image that targets 0x80016FF4 - 1 site of 294,400 words
  // scanned - so this is the call being stood in for and not a choice among candidates.
  // Before this was supplied, `x4::guest::call` took the
  // boundary from `core->r[31]` and inherited 0x80022060, the return address of an unrelated
  // `jal 0x80015ecc`; the decompressor could not return there, ran 757,804 cycles past its own end
  // and faulted at a non-address.
  runGuest(core, kDecompressGfxGuest, kDecompressGfxReturn, stream, buffer, caller);

  emitBands(core, buffer, x, y, bands, record);

  if (record.refused != 0u) {
    stats.refused += record.refused;
    lastRefusalField = record.field;
    // ONE line per field, not one per refusal. A run that refuses 265 times would otherwise print
    // 265 identical lines, and a uniform block of identical output is the shape of an instrument
    // that has stopped discriminating — the run-end census carries the volume, and this line carries
    // the attribution that makes the refusals legible.
    if (!reportedThisField || record.field != reportedField) {
      reportedField = record.field;
      reportedThisField = true;
      lucent::warn("x4-vram-rect",
                   "field {}: the queue is FULL. The appender call from 0x{:08X} for object 0x{:08X} "
                   "at ({}, {}) wanted an entry and there was none: kQueueEnd=0x{:08X} is "
                   "item_objects[0], and the guest's own uploader reads exactly {} entries, so an "
                   "entry past kQueueEnd was never uploadable by retail either. Denominator: {} of "
                   "{} entries this run fit; the rest were refused rather than written over the next "
                   "guest structure. Further refusals in this field are counted, not printed",
                   record.field,
                   record.caller,
                   record.object,
                   record.x,
                   record.y,
                   kQueueEnd,
                   kEntryCapacity,
                   stats.emitted,
                   stats.emitted + stats.refused);
    }
  }
}

void install(Core &core) {
  psx::cpu::installNativeOverride(core, kClearQueueGuest, "vram_rect::clear", [](Core *active) {
    clear(*active);
  });
  psx::cpu::installNativeOverride(core, kUploadQueueGuest, "vram_rect::upload", [](Core *active) {
    upload(*active);
  });
  // The guest's three arguments are `$4` = object, `$5` = rectangle x, `$6` = rectangle y, read as
  // s16 by the two `sh` stores at 0x80015F7C and 0x80015F80. They are REGISTERS, not guest
  // addresses: `Core::mem_r16s` takes an address, so reading `$5` through it would name guest
  // address 5 and silently produce zero.
  psx::cpu::installNativeOverride(core, kAppendBandsGuest, "vram_rect::append", [](Core *active) {
    const std::uint32_t object = active->r[4];
    const std::int32_t x = static_cast<std::int16_t>(active->r[5]);
    const std::int32_t y = static_cast<std::int16_t>(active->r[6]);
    append(*active, object, x, y);
  });
}

Census census() {
  return stats;
}

void reportCensus(const char *why) {
  if (stats.calls == 0u && stats.clears == 0u && stats.uploads == 0u) {
    lucent::info("x4-vram-rect",
                 "run-end ({}): the queue was never touched — 0 clear(s), 0 upload(s), "
                 "0 append call(s). This run measured nothing about it",
                 why);
    return;
  }
  lucent::info("x4-vram-rect",
               "run-end ({}): {} clear(s), {} upload(s) publishing {} entry/entries, {} append "
               "call(s) emitting {} entry/entries; {} entry/entries REFUSED at kQueueEnd, last at "
               "field {}. Denominator: {} of {} emitted entries fit inside the {} the array holds",
               why,
               stats.clears,
               stats.uploads,
               stats.uploadedEntries,
               stats.calls,
               stats.emitted,
               stats.refused,
               lastRefusalField,
               stats.emitted,
               stats.emitted,
               kEntryCapacity);
  if (stats.refused == 0u) {
    lucent::info("x4-vram-rect",
                 "run-end ({}): the queue never filled in this run, so the bound "
                 "cost nothing",
                 why);
  }
}

} // namespace x4::vram_rect
