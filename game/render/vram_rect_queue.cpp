// SPDX-License-Identifier: AGPL-3.0-or-later
// derived from external/mmx4

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

// Band loop of 0x80015F74-0x80015FD4; the cursor advances in the delay slot at 0x80015FD4, so it moves
// once per entry, not per call.
void emitBands(
    Core &core, std::uint32_t source, std::int32_t x, std::int32_t y, std::int32_t remaining, Append &record) {
  std::uint32_t cursor = core.mem_r32(kCursorGlobal);
  std::int32_t top = y;
  // v1 at loop exit is the band count the last head read (`sra` @ 0x80015F74).
  std::int32_t lastHeadCount = remaining;
  while (remaining != 0) {
    lastHeadCount = remaining;
    // The guest has no capacity test and the cursor is a guest-written global, so test membership.
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

  // Terminator `sw zero,8($5)` @ 0x80015FD8 at cursor + 8; skipped when it would leave the array.
  if (cursor >= kQueueBase && cursor + kEntryStride <= kQueueEnd) {
    core.mem_w32(cursor + 8, 0u);
  }
  core.mem_w32(kCursorGlobal, cursor);

  // At exit v0 is zero (`sll` @ 0x80015FCC) and $4/$5 equal the advanced cursor.
  core.r[1] = kGuestPage8014;
  core.r[2] = kAppendFinalV0;
  core.r[3] = static_cast<std::uint32_t>(lastHeadCount);
  core.r[4] = cursor;
  core.r[5] = cursor;
  core.r[6] = kAppendFinalA2;
  core.r[7] = kAppendFinalA3;
}

// Slot 3 uses the shared buffer (0x80015F24); others index by the signed slot byte (`sll 0xc` @ 0x80015F34), so a
// negative slot wraps below the base as in the guest.
std::uint32_t decompressedBuffer(Core &core, std::uint32_t object) {
  const std::int32_t slot = core.mem_r8s(object + kGfxSlotOffset);
  if (slot == kSharedGfxSlot) {
    return kSharedGfxBuffer;
  }
  return kPerSlotGfxBuffer + static_cast<std::uint32_t>(slot * static_cast<std::int32_t>(kGfxBufferStride));
}

void runGuest(
    Core &core, std::uint32_t entry, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1, std::uint32_t caller) {
  // The guest body leaves $31 as it found it (`sw/lw ra,0x20(sp)` @ 0x80015ED8/0x80015FE4).
  const std::uint32_t savedLink = core.r[31];
  core.r[4] = a0;
  core.r[5] = a1;
  // Callee returns to the override entry link so `jr $ra` lands on the dispatcher boundary.
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
    // LoadImage @ 0x80015E8C reads the RECT from guest memory.
    runGuest(core, kLoadImageGuest, kLoadImageGuestReturn, entry, pixels, caller);
    stats.uploadedEntries += 1;
  }
  core.mem_w32(kCursorGlobal, kQueueBase);
  // at/v0 from 0x80015EA4-0x80015EAC, v1 from 0x80015E64; a0/a1 stay as LoadImage left them.
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

  // Unchanged animation index returns before decompressing; `sb` @ 0x80015F04 latches the new one.
  const std::uint32_t current = core.mem_r8(object + kCurrentAnimOffset);
  const std::uint32_t previous = core.mem_r8(object + kPreviousAnimOffset);
  // The delay slot @ 0x80015EF8 is reloaded by the epilogue, so only the compared bytes survive.
  core.r[kCurrentAnimRegister] = current;
  core.r[kPreviousAnimRegister] = previous;
  if (current == previous) {
    return;
  }
  core.mem_w8(object + kPreviousAnimOffset, static_cast<std::uint8_t>(current));

  const std::uint32_t blob = core.mem_r32(object + kBlobOffset);
  const std::uint32_t word = core.mem_r32(blob + current * 4u);
  const std::int32_t bands = bandCount(word);
  const std::uint32_t stream = streamAddress(blob, word);
  const std::uint32_t buffer = decompressedBuffer(core, object);

  // `jal 0x80016FF4` @ 0x80015F54, the only call to it; returns to 0x80015F5C.
  runGuest(core, kDecompressGfxGuest, kDecompressGfxReturn, stream, buffer, caller);

  emitBands(core, buffer, x, y, bands, record);

  if (record.refused != 0u) {
    stats.refused += record.refused;
    lastRefusalField = record.field;
    // One line per field; the census carries the volume.
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
  // Arguments are registers: $4 object, $5/$6 x/y as s16 (`sh` @ 0x80015F7C / 0x80015F80).
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
