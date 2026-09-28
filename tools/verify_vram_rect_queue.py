#!/usr/bin/env python3
"""verify_vram_rect_queue.py — pin, from the authenticated SLUS_005.61 bytes, every constant the
native rectangle-queue owner (game/core/vram_rect_queue.{h,cpp}) is built on.

    python3 tools/verify_vram_rect_queue.py --check
    python3 tools/verify_vram_rect_queue.py --selftest

WHY A SEPARATE GATE AND NOT A COMMENT. `vram_rect_queue.h` is a native owner: it REPLACES three guest
functions, so every address and immediate in it is a decision rather than a copy. docs/issues/0032,
0033 and 0034 each added a claim to `verify_stage_fault.py`; this tool covers the owner's own surface
— the queue's layout, the three guest entries, the appender's arithmetic, and the structural claim
the mitigation rests on (the array's end IS the next guest structure, and the uploader reads exactly
as many entries as the array holds).

WHAT MAKES IT A POSITIVE TEST. `--selftest` mutates a copy of the image nine ways and requires every
mutation to be caught, including two that are the specific ways a reader of this file could be wrong:
moving the array base so the eight entries no longer end on `item_objects[0]`, and widening the
guest's own trip count to nine.

WORD ORDER IS A MEASURED FACT, not a convention. This image is stored word-byte-swapped relative to a
big-endian PS-X EXE and the port reads it little-endian, which is what `llvm-objdump -d` (NEVER
`--triple=mips`, which decodes this image silently wrong) agrees with. `assert_word_order` re-derives
the three independent facts `verify_stage_fault.py` established, so a reader that took the other
order fails here rather than producing confident garbage.

DENOMINATORS ARE IN THE OUTPUT. Every count below counts something the tool actually compared.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from resolve_disc import resolve  # noqa: E402
import discdump  # noqa: E402

EXE_ON_DISC = "SLUS_005.61"
PSX_EXE_HEADER = 0x800
OUT_DIR = ROOT / "scratch" / "bin" / "megamanx4"

# ── the queue ─────────────────────────────────────────────────────────────────────────────────
QUEUE_BASE = 0x801659D0
QUEUE_STRIDE = 12
QUEUE_CAPACITY = 8
QUEUE_END = QUEUE_BASE + QUEUE_STRIDE * QUEUE_CAPACITY
ITEM_OBJECTS = 0x80165A30
CURSOR_GLOBAL = 0x80141F68
FIELD_COUNTER = 0x80141BD8

CLEAR_GUEST = 0x80015E0C
UPLOAD_GUEST = 0x80015E54
APPEND_GUEST = 0x80015ECC
DECOMPRESS_GUEST = 0x80016FF4
LOAD_IMAGE_GUEST = 0x800EA4D0
ITEM_DISPATCH = 0x8002174C
ITEM_DISPATCH_CALLER = 0x80021FE8          # the `jal` inside the same update pass
APPEND_PLAYER_CALL = 0x80022058            # the one call site this title ever reaches
APPEND_PLAYER_RETURN = 0x80022060

# ── the appender's arithmetic ─────────────────────────────────────────────────────────────────
CURRENT_ANIM = 0x47
PREVIOUS_ANIM = 0x48
GFX_SLOT = 0x49
BLOB = 0x38
BAND_COUNT_SHIFT_INSN = 0x80015F20
BAND_COUNT_SHIFT = 20
BAND_COUNT_WIDTH = 12                      # (word >> 20) & 0xFFF: twelve bits, so never negative
STREAM_MASK_INSN = 0x80015F4C
STREAM_OFFSET_MASK = 0xFFFF
SHARED_BUFFER_INSN_A = 0x80015F24
SHARED_BUFFER_INSN_B = 0x80015F28
SHARED_BUFFER = 0x8016DEA8
PER_SLOT_BUFFER_INSN_A = 0x80015F38
PER_SLOT_BUFFER_INSN_B = 0x80015F3C
PER_SLOT_BUFFER = 0x8016EEA8
GFX_BUFFER_SHIFT_INSN = 0x80015F34
GFX_BUFFER_SHIFT = 12
GFX_BUFFER_STRIDE = 0x1000
SHARED_SLOT_LITERAL = 0x80015F18
SHARED_SLOT = 3
BAND_HEIGHT_INSN = 0x80015F64
BAND_HEIGHT = 16
FULL_BAND_WIDTH_INSN = 0x80015F68
FULL_BAND_WIDTH = 0x40
FULL_BAND_SOURCE_INSN = 0x80015FC4
FULL_BAND_SOURCE = 0x800
TRAILING_TEST_INSN = 0x80015F78
TRAILING_TEST = 0x10
CURSOR_ADVANCE_INSN = 0x80015FD4
CURSOR_ADVANCE = 0xC
LOOP_BRANCH_INSN = 0x80015FD0
TERMINATOR_INSN = 0x80015FD8
CURSOR_PUBLISH_INSN = 0x80015FE0
EARLY_RETURN_INSN = 0x80015EF4
EARLY_RETURN_TARGET = 0x80015FE4
LATCH_INSN = 0x80015F04

# ── the uploader's and the clearer's own bound ────────────────────────────────────────────────
CLEAR_BASE_INSN = 0x80015E10
CLEAR_PUBLISH_INSN = 0x80015E18
CLEAR_TRIP_INSN = 0x80015E40
CLEAR_TRIP = 8
CLEAR_STRIDE_INSN = 0x80015E38
UPLOAD_BASE_INSN = 0x80015E60
UPLOAD_END_INSN = 0x80015E64
UPLOAD_END_OFFSET = 0x60
UPLOAD_TEST_INSN = 0x80015E68
UPLOAD_STRIDE_INSN = 0x80015E94
UPLOAD_LOADIMAGE_CALL = 0x80015E8C
UPLOAD_SOURCE_LOAD_INSN = 0x80015E7C

R_MNEMONIC = {0x00: "SPECIAL", 0x09: "ADDIU", 0x0D: "ORI", 0x0F: "LUI", 0x2B: "SW", 0x23: "LW",
              0x28: "SB", 0x29: "SH", 0x24: "LBU", 0x20: "LB", 0x0A: "SLTI", 0x0B: "SLTIU", 0x2A: "J"}


class Image:
    """The authenticated executable's loaded text, read the way the GUEST reads it."""

    def __init__(self, data: bytes) -> None:
        header = struct.unpack_from("<11I", data, 0x10)
        self.text_address = header[2]
        self.text_bytes = header[3]
        self.text = data[PSX_EXE_HEADER:PSX_EXE_HEADER + self.text_bytes]
        self._words = struct.unpack_from(f"<{self.text_bytes // 4}I", self.text, 0)

    def word(self, address: int) -> int:
        offset = address - self.text_address
        if offset < 0 or offset + 4 > self.text_bytes:
            raise ValueError(f"0x{address:08X} is outside the loaded text")
        return self._words[offset // 4]

    def decode(self, address: int) -> str:
        word = self.word(address)
        op, rs, rt, imm = word >> 26, (word >> 21) & 0x1F, (word >> 16) & 0x1F, word & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        name = R_MNEMONIC.get(op, f"op{op:02X}")
        return f"0x{word:08X} {name} rs={rs} rt={rt} imm={imm}({simm})"

    def is_op(self, address: int, op: int) -> bool:
        return self.word(address) >> 26 == op

    def imm(self, address: int) -> int:
        return self.word(address) & 0xFFFF

    def s16(self, address: int) -> int:
        imm = self.imm(address)
        return imm - 0x10000 if imm & 0x8000 else imm

    def field(self, address: int, index: int) -> int:
        """rs at index 0, rt at 1, rd at 2 — the R-type register fields at bits [25:21], [20:16]
        and [15:11], i.e. a shift of 21 MINUS 5 per index. Adding instead puts index 1 on the
        opcode, which is the second way to read `sltu $v0,$s0,$v1` as an op-0 word."""
        return (self.word(address) >> (21 - 5 * index)) & 0x1F

    def rd(self, address: int) -> int:
        return (self.word(address) >> 11) & 0x1F

    def rt(self, address: int) -> int:
        return (self.word(address) >> 16) & 0x1F

    def sa(self, address: int) -> int:
        """The SPECIAL shift-amount field. A shift's amount is here, NOT in rd: reading rd is the
        mistake that makes a `srl $s0,$a1,0x14` look like a shift by 16."""
        return (self.word(address) >> 6) & 0x1F

    def funct(self, address: int) -> int:
        return self.word(address) & 0x3F

    def target(self, address: int) -> int:
        return (address & 0xF0000000) | ((self.word(address) & 0x3FFFFFF) << 2)

    def branch_target(self, address: int) -> int:
        return address + 4 + self.s16(address) * 4


class Report:
    def __init__(self) -> None:
        self.comparisons = 0
        self.failures: list[str] = []
        self.notes: list[str] = []

    def check(self, ok: bool, what: str, detail: str = "") -> bool:
        self.comparisons += 1
        if not ok:
            self.failures.append(f"{what}{': ' + detail if detail else ''}")
        return ok

    def note(self, text: str) -> None:
        self.notes.append(text)


def assert_word_order(image: Image, report: Report) -> None:
    """The three facts that make the little-endian read the right one, re-derived here."""
    returns = 0
    inside = 0
    total_jal = 0
    for address in range(image.text_address, image.text_address + image.text_bytes, 4):
        word = image.word(address)
        if word == 0x03E00008:
            returns += 1
        if word >> 26 == 0x03:
            total_jal += 1
            if image.text_address <= image.target(address) < image.text_address + image.text_bytes:
                inside += 1
    report.check(returns == 5380, "5,380 `jr $ra` words under the little-endian read", f"found {returns}")
    ratio = 100.0 * inside / total_jal if total_jal else 0.0
    report.check(ratio > 70.0, "most `jal` targets land inside .text under the little-endian read",
                 f"{inside} of {total_jal} = {ratio:.1f}%")


def verify(image: Image) -> Report:
    report = Report()
    assert_word_order(image, report)

    # ── 1. the queue's layout, and the structural claim the mitigation rests on ────────────────
    report.check(QUEUE_END == ITEM_OBJECTS,
                 "kQueueEnd is item_objects[0]", f"0x{QUEUE_END:08X} vs 0x{ITEM_OBJECTS:08X}")
    report.check(image.is_op(CLEAR_BASE_INSN, 0x09) and image.s16(CLEAR_BASE_INSN) == QUEUE_BASE - 0x80160000,
                 "the clearer materialises kQueueBase", image.decode(CLEAR_BASE_INSN))
    report.check(image.is_op(CLEAR_STRIDE_INSN, 0x09) and image.s16(CLEAR_STRIDE_INSN) == QUEUE_STRIDE,
                 "the clearer steps kEntryStride", image.decode(CLEAR_STRIDE_INSN))
    report.check(image.is_op(CLEAR_TRIP_INSN, 0x0B) and image.imm(CLEAR_TRIP_INSN) == CLEAR_TRIP,
                 "the clearer states kEntryCapacity itself", image.decode(CLEAR_TRIP_INSN))
    report.check(image.is_op(UPLOAD_BASE_INSN, 0x09) and image.s16(UPLOAD_BASE_INSN) == QUEUE_BASE - 0x80160000,
                 "the uploader materialises kQueueBase", image.decode(UPLOAD_BASE_INSN))
    report.check(image.is_op(UPLOAD_END_INSN, 0x09) and image.imm(UPLOAD_END_INSN) == UPLOAD_END_OFFSET,
                 "the uploader states the array end as base+0x60", image.decode(UPLOAD_END_INSN))
    report.check(image.is_op(UPLOAD_TEST_INSN, 0x00) and image.funct(UPLOAD_TEST_INSN) == 0x2B
                 and image.field(UPLOAD_TEST_INSN, 0) == 16 and image.field(UPLOAD_TEST_INSN, 1) == 3,
                 "the uploader's loop test is an UNSIGNED compare of the entry pointer against the end",
                 image.decode(UPLOAD_TEST_INSN))
    report.check(image.is_op(UPLOAD_STRIDE_INSN, 0x09) and image.s16(UPLOAD_STRIDE_INSN) == QUEUE_STRIDE,
                 "the uploader steps kEntryStride", image.decode(UPLOAD_STRIDE_INSN))
    report.check(image.is_op(UPLOAD_SOURCE_LOAD_INSN, 0x23) and image.s16(UPLOAD_SOURCE_LOAD_INSN) == 8,
                 "the uploader reads the source pointer at entry+8", image.decode(UPLOAD_SOURCE_LOAD_INSN))
    report.check(image.word(UPLOAD_LOADIMAGE_CALL) >> 26 == 0x03
                 and image.target(UPLOAD_LOADIMAGE_CALL) == LOAD_IMAGE_GUEST,
                 "the uploader calls the BIOS LoadImage entry this owner calls", image.decode(UPLOAD_LOADIMAGE_CALL))

    # The count the mitigation depends on: the uploader reads exactly kEntryCapacity entries and the
    # store that can cross the array's end lives in the appender, which has no count at all.
    append_words = [image.word(a) for a in range(APPEND_GUEST, APPEND_GUEST + 0x134, 4)]
    append_addrs = list(range(APPEND_GUEST, APPEND_GUEST + 0x134, 4))
    capacity_compares = [a for a, w in zip(append_addrs, append_words)
                         if w >> 26 in (0x0A, 0x0B) and (w & 0xFFFF) in (QUEUE_CAPACITY, UPLOAD_END_OFFSET)]
    report.check(len(capacity_compares) == 0,
                 "the appender contains NO capacity-shaped compare at all — none against the "
                 "array's size, none against its end — which is why this owner has to supply the bound",
                 f"found {len(capacity_compares)}")
    band_thresholds = [a for a, w in zip(append_addrs, append_words)
                       if w >> 26 in (0x0A, 0x0B) and (w & 0xFFFF) == TRAILING_TEST]
    report.check(band_thresholds == [TRAILING_TEST_INSN],
                 "the appender's ONLY immediate compare is the band threshold, not a capacity",
                 ", ".join(f"0x{a:08X}" for a in band_thresholds))

    # ── 2. the appender's early return, latch, and band count ────────────────────────────────
    report.check(image.is_op(EARLY_RETURN_INSN, 0x04)
                 and image.branch_target(EARLY_RETURN_INSN) == EARLY_RETURN_TARGET,
                 "the appender returns before decompressing when the animation index has not moved",
                 image.decode(EARLY_RETURN_INSN))
    report.check(image.is_op(0x80015EE8, 0x24) and image.s16(0x80015EE8) == CURRENT_ANIM,
                 "the appender reads the current animation index UNSIGNED at +0x47",
                 image.decode(0x80015EE8))
    report.check(image.s16(0x80015EEC) == PREVIOUS_ANIM,
                 "the appender reads the previous animation index at +0x48", image.decode(0x80015EEC))
    report.check(image.s16(0x80015EFC) == CURRENT_ANIM,
                 "the appender re-reads the current animation index for the table index",
                 image.decode(0x80015EFC))
    report.check(image.s16(LATCH_INSN) == PREVIOUS_ANIM and image.is_op(LATCH_INSN, 0x28),
                 "the appender latches the current index into +0x48", image.decode(LATCH_INSN))
    report.check(image.s16(0x80015F00) == BLOB,
                 "the appender reads the object's compressed blob at +0x38", image.decode(0x80015F00))
    report.check(image.s16(0x80015F08) == GFX_SLOT and image.is_op(0x80015F08, 0x20),
                 "the appender reads the graphics slot as a SIGNED byte at +0x49", image.decode(0x80015F08))
    # MIPS R-type, the trap in this ISA: a SHIFT puts its SOURCE in the rt slot (bits [20:16]) and
    # its destination in rd, while every other SPECIAL operation puts its source in the rs slot
    # (bits [25:21]). So `srl $s0,$a1,0x14` has rs == 0 and rt == 5, and a reader that looks in rs
    # concludes the source is $zero.
    report.check(image.funct(BAND_COUNT_SHIFT_INSN) == 0x02 and image.rd(BAND_COUNT_SHIFT_INSN) == 16
                 and image.rt(BAND_COUNT_SHIFT_INSN) == 5 and image.field(BAND_COUNT_SHIFT_INSN, 0) == 0,
                 "the band count is `srl $s0,$a1,sa`: source in rt, destination in rd, amount in sa",
                 image.decode(BAND_COUNT_SHIFT_INSN))
    report.check(image.sa(BAND_COUNT_SHIFT_INSN) == BAND_COUNT_SHIFT,
                 "the band count comes from bits 20..31", image.decode(BAND_COUNT_SHIFT_INSN))
    report.check(1 << BAND_COUNT_WIDTH == (1 << (32 - BAND_COUNT_SHIFT)),
                 "the band count is exactly twelve bits, so the sign test at 0x80015FA4 is dead",
                 f"width {BAND_COUNT_WIDTH} vs {32 - BAND_COUNT_SHIFT}")
    report.check(image.is_op(STREAM_MASK_INSN - 4, 0x0D) and image.imm(STREAM_MASK_INSN - 4) == 0xFFFF,
                 "the stream mask is materialised as 0xFFFF", image.decode(STREAM_MASK_INSN - 4))
    report.check(image.funct(STREAM_MASK_INSN) == 0x24 and image.field(STREAM_MASK_INSN, 0) == 5,
                 "the compressed-stream offset is ANDed with it, in a register AND not an ANDI",
                 image.decode(STREAM_MASK_INSN))
    report.check(image.imm(STREAM_MASK_INSN - 4) == STREAM_OFFSET_MASK,
                 "so the mask is 0xFFFF, sixteen bits — NOT the 0xFFFFF the reference "
                 "decompilation prints. A 20-bit mask would let the stream offset run a megabyte "
                 "past the object's blob, so this constant is load-bearing, not cosmetic",
                 f"0x{image.imm(STREAM_MASK_INSN - 4):04X}")

    # ── 3. the two decompressed buffers ──────────────────────────────────────────────────────
    for a, b, want, what in ((SHARED_BUFFER_INSN_A, SHARED_BUFFER_INSN_B, SHARED_BUFFER, "kSharedGfxBuffer"),
                             (PER_SLOT_BUFFER_INSN_A, PER_SLOT_BUFFER_INSN_B, PER_SLOT_BUFFER,
                              "kPerSlotGfxBuffer")):
        report.check(image.is_op(a, 0x0F), f"{what} is materialised by a LUI", image.decode(a))
        page = image.imm(a) << 16
        report.check(page + image.s16(b) == want, f"{what} is 0x{want:08X}",
                     f"0x{page:08X} + {image.s16(b)} = 0x{page + image.s16(b):08X}")
    report.check(image.sa(GFX_BUFFER_SHIFT_INSN) == GFX_BUFFER_SHIFT
                 and image.funct(GFX_BUFFER_SHIFT_INSN) == 0x00,
                 "the per-slot buffer is indexed by a shift of 12, i.e. 0x1000-byte slots",
                 image.decode(GFX_BUFFER_SHIFT_INSN))
    report.check(1 << GFX_BUFFER_SHIFT == GFX_BUFFER_STRIDE, "kGfxBufferStride matches that shift")
    report.check(image.imm(SHARED_SLOT_LITERAL) == SHARED_SLOT and image.is_op(SHARED_SLOT_LITERAL, 0x09),
                 "the shared slot literal is 3", image.decode(SHARED_SLOT_LITERAL))

    # ── 4. the band geometry ────────────────────────────────────────────────────────────────
    report.check(image.imm(BAND_HEIGHT_INSN) == BAND_HEIGHT and image.is_op(BAND_HEIGHT_INSN, 0x09),
                 "kBandHeight is 16", image.decode(BAND_HEIGHT_INSN))
    report.check(image.imm(FULL_BAND_WIDTH_INSN) == FULL_BAND_WIDTH and image.is_op(FULL_BAND_WIDTH_INSN, 0x09),
                 "kFullBandWidth is 0x40", image.decode(FULL_BAND_WIDTH_INSN))
    report.check(image.imm(FULL_BAND_SOURCE_INSN) == FULL_BAND_SOURCE
                 and image.is_op(FULL_BAND_SOURCE_INSN, 0x09),
                 "a full band advances the source by 0x800 bytes", image.decode(FULL_BAND_SOURCE_INSN))
    report.check(image.imm(TRAILING_TEST_INSN) == TRAILING_TEST and image.is_op(TRAILING_TEST_INSN, 0x0A),
                 "the trailing-band test is the signed SLTI against 0x10", image.decode(TRAILING_TEST_INSN))

    # ── 5. the cursor advance, and the reading issues 0033/0034 got wrong ────────────────────
    # 0x80015FD4 is the DELAY SLOT of the loop branch at 0x80015FD0, so it runs once per ENTRY, not
    # once per call. Two prior issues read it as a post-loop store and concluded the cursor advances
    # per call; the gate pins the branch target so that reading cannot come back.
    report.check(image.is_op(LOOP_BRANCH_INSN, 0x05), "0x80015FD0 is a BNE, the band loop's back edge",
                 image.decode(LOOP_BRANCH_INSN))
    report.check(image.branch_target(LOOP_BRANCH_INSN) == 0x80015F74,
                 "the loop branch targets the band loop head at 0x80015F74",
                 f"0x{image.branch_target(LOOP_BRANCH_INSN):08X}")
    report.check(image.s16(CURSOR_ADVANCE_INSN) == CURSOR_ADVANCE and image.is_op(CURSOR_ADVANCE_INSN, 0x09),
                 "the cursor advances 12 per iteration", image.decode(CURSOR_ADVANCE_INSN))
    report.check(image.is_op(TERMINATOR_INSN, 0x2B) and image.s16(TERMINATOR_INSN) == 8,
                 "the terminator nulls the source pointer of entry+8 at the advanced cursor",
                 image.decode(TERMINATOR_INSN))
    report.check(image.is_op(CURSOR_PUBLISH_INSN, 0x2B) and image.s16(CURSOR_PUBLISH_INSN) == 0x1F68,
                 "the appender publishes kCursorGlobal", image.decode(CURSOR_PUBLISH_INSN))
    report.check(image.s16(CLEAR_PUBLISH_INSN) == 0x1F68 and image.is_op(CLEAR_PUBLISH_INSN, 0x2B),
                 "the clearer publishes kCursorGlobal", image.decode(CLEAR_PUBLISH_INSN))

    # The cursor global's writers, exhaustively: a MIPS store is one word, so a store that can reach
    # the cursor is found by matching the displacement and then checking the base register's page.
    displacement_window = [a for a in range(image.text_address, image.text_address + image.text_bytes, 4)
                           if image.is_op(a, 0x2B) and 0x1F60 <= image.imm(a) <= 0x1F70]
    on_cursor = [a for a in displacement_window if image.imm(a) == 0x1F68]
    report.check(len(displacement_window) == 12,
                 "twelve stores have a displacement in [0x1F60,0x1F70]", f"found {len(displacement_window)}")
    report.check(len(on_cursor) == 3, "exactly three of them write the cursor word",
                 f"found {len(on_cursor)}: " + ", ".join(f"0x{a:08X}" for a in on_cursor))
    report.check(set(on_cursor) == {CLEAR_PUBLISH_INSN, 0x80015EB0, CURSOR_PUBLISH_INSN},
                 "and they are the clearer, the uploader and the appender",
                 ", ".join(f"0x{a:08X}" for a in on_cursor))

    # ── 6. the ordering that makes the overflow fatal one pass later ─────────────────────────
    # The update pass dispatches item objects BEFORE it appends the player's rectangles, so the ninth
    # entry cannot fault on the pass that wrote it: it is read by the NEXT pass's dispatch. This is
    # the guest's own order, and it is why retail corrupts the same record on the same pass.
    report.check(image.word(ITEM_DISPATCH_CALLER) >> 26 == 0x03
                 and image.target(ITEM_DISPATCH_CALLER) == ITEM_DISPATCH,
                 "the update pass dispatches item objects", image.decode(ITEM_DISPATCH_CALLER))
    # The ordering is a fact about ONE guest function, so the gate reads that function's own
    # boundaries out of the image and places both sites inside them. Comparing two constants in
    # Python would pass no matter what the image said, which is the failure mode the mutation
    # "swap the two call sites" is there to catch.
    pass_start = 0x80021F34
    report.check(image.is_op(pass_start, 0x09) and image.rt(pass_start) == 29
                 and image.s16(pass_start) == -0x18,
                 "the update pass opens its frame at 0x80021F34", image.decode(pass_start))
    report.check(pass_start <= ITEM_DISPATCH_CALLER < APPEND_PLAYER_CALL <= 0x8002206C,
                 "the item dispatch and the appender call are BOTH inside that one function, and the "
                 "dispatch comes first — so the ninth entry is read by the NEXT pass, not the one "
                 "that wrote it",
                 f"pass 0x{pass_start:08X}, dispatch 0x{ITEM_DISPATCH_CALLER:08X}, "
                 f"append 0x{APPEND_PLAYER_CALL:08X}, return 0x8002206C")
    report.check(image.is_op(0x8002206C, 0x00) and image.funct(0x8002206C) == 0x08
                 and image.field(0x8002206C, 0) == 31,
                 "and that function returns at 0x8002206C", image.decode(0x8002206C))
    report.check(image.word(APPEND_PLAYER_CALL) >> 26 == 0x03 and image.target(APPEND_PLAYER_CALL) == APPEND_GUEST,
                 "0x80022058 is a call to the appender", image.decode(APPEND_PLAYER_CALL))
    report.check(image.funct(APPEND_PLAYER_CALL - 8) == 0x21 and image.field(APPEND_PLAYER_CALL - 8, 0) == 16
                 and image.rd(APPEND_PLAYER_CALL - 8) == 4,
                 "that call's object argument is $s0, and $s0 is g_Player",
                 image.decode(APPEND_PLAYER_CALL - 8))
    report.check(image.s16(APPEND_PLAYER_CALL - 4) == 320,
                 "and its x argument is 320", image.decode(APPEND_PLAYER_CALL - 4))
    report.check(image.funct(APPEND_PLAYER_CALL + 4) == 0x21 and image.rd(APPEND_PLAYER_CALL + 4) == 6
                 and image.field(APPEND_PLAYER_CALL + 4, 1) == 0,
                 "and its y argument is 0", image.decode(APPEND_PLAYER_CALL + 4))
    report.check(APPEND_PLAYER_RETURN == APPEND_PLAYER_CALL + 8
                 and image.is_op(APPEND_PLAYER_RETURN, 0x23) and image.rt(APPEND_PLAYER_RETURN) == 31,
                 "its return address is the instruction after its delay slot, 0x80022060 — which is "
                 "the value the run measured in $31", image.decode(APPEND_PLAYER_RETURN))

    # ── 7. the call-site census, so the "seventeen sites" number stays a measurement ──────────
    sites = [a for a in range(image.text_address, image.text_address + image.text_bytes, 4)
             if image.word(a) >> 26 == 0x03 and image.target(a) == APPEND_GUEST]
    report.check(len(sites) == 17, "seventeen `jal` sites reach the appender", f"found {len(sites)}")
    report.note(f"append call sites: {len(sites)}, of which 0x80022058 is the one this title reaches")

    # ── 8. the guest's other two entries the owner replaces ─────────────────────────────────
    report.check(image.is_op(CLEAR_GUEST, 0x0F) and image.imm(CLEAR_GUEST) == 0x8016,
                 "kClearQueueGuest is the function that starts with the queue's page",
                 image.decode(CLEAR_GUEST))
    report.check(image.word(UPLOAD_GUEST) >> 26 == 0x09 and image.rt(UPLOAD_GUEST) == 29,
                 "kUploadQueueGuest is the function with the frame allocation the uploader has",
                 image.decode(UPLOAD_GUEST))
    report.check(image.word(APPEND_GUEST) >> 26 == 0x09 and image.s16(APPEND_GUEST) == -0x28,
                 "kAppendBandsGuest opens the appender's frame", image.decode(APPEND_GUEST))
    report.check(image.word(DECOMPRESS_GUEST) >> 26 == 0x25
                 and image.word(APPEND_GUEST + 0x88) >> 26 == 0x03
                 and image.target(APPEND_GUEST + 0x88) == DECOMPRESS_GUEST,
                 "kDecompressGfxGuest is the 16-bit-load leaf the appender calls",
                 image.decode(DECOMPRESS_GUEST) + " / " + image.decode(APPEND_GUEST + 0x88))
    report.check(image.word(0x80015F9C) >> 26 == 0x29 and image.rt(0x80015F9C) == 7
                 and image.s16(0x80015F9C) == 0,
                 "the trailing band stores $a3 — the literal 0x10 — as the rectangle height",
                 image.decode(0x80015F9C))
    report.check(image.word(0x80015F7C) >> 26 == 0x29 and image.s16(0x80015F7C) == 0
                 and image.word(0x80015F88) >> 26 == 0x2B and image.s16(0x80015F88) == 2,
                 "the record is RECT at +0 and the source pointer at +8, i.e. 12 bytes",
                 image.decode(0x80015F7C) + " / " + image.decode(0x80015F88))
    report.check(FIELD_COUNTER == 0x80141BD8, "kFieldCounter is the guest's own field word")
    return report


def read_image(path: Path) -> bytes:
    return path.read_bytes()


def acquire_image(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    target = OUT_DIR / EXE_ON_DISC
    if target.is_file():
        return target
    disc = resolve(None, quiet=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    discdump.extract(str(disc), str(OUT_DIR))
    if not target.is_file():
        print(f"REFUSED: {target} does not exist after extraction; NOTHING WAS CHECKED", file=sys.stderr)
        raise SystemExit(2)
    return target


def mutate(data: bytes, address: int, word: bytes) -> bytes:
    out = bytearray(data)
    # PS-X EXE: 0x10 entry, 0x14 gp, 0x18 t_addr, 0x1C t_size. Reading the load address from 0x20
    # — one word too far — offsets every mutation by 8 and the selftest then reports 0 of 9 caught
    # on an image that passes 62 of 62, which is the shape of a broken instrument rather than a
    # broken image.
    offset = PSX_EXE_HEADER + (address - struct.unpack_from("<I", data, 0x18)[0])
    out[offset:offset + 4] = word
    return bytes(out)


def selftest() -> int:
    original = read_image(acquire_image(None))
    base = verify(Image(original))
    print(f"baseline: {base.comparisons - len(base.failures)}/{base.comparisons} claims match the image")
    if base.failures:
        print("  the unmutated image does not pass, so a selftest here would be meaningless:")
        for failure in base.failures:
            print(f"    {failure}")
        return 1

    def word(address: int, value: int) -> bytes:
        return struct.pack("<I", value)

    def lui(reg: int, imm: int) -> bytes:  # noqa: ARG001 - kept for readability of the cases
        return struct.pack("<I", (0x0F << 26) | (reg << 16) | imm)

    def addiu(rs: int, rt: int, imm: int) -> bytes:
        return struct.pack("<I", (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF))

    cases = [
        # 1. move the array base so its eight entries no longer end on item_objects[0]. This is the
        #    mutation the whole mitigation rests on, so it is the one that must be caught first.
        #    It is caught by the two claims that READ the base out of the image, which is the point:
        #    the relation `kQueueEnd == item_objects[0]` is a property of this repository's own
        #    constants and is a static_assert in the header, not something the image can refute.
        ("the clearer still materialises kQueueBase",
         mutate(original, CLEAR_BASE_INSN, addiu(4, 4, 0x59C0)),
         "materialises kQueueBase"),
        # 2. widen the guest's own trip count to nine.
        ("the clearer still states kEntryCapacity itself",
         mutate(original, CLEAR_TRIP_INSN, struct.pack("<I", (0x0B << 26) | (5 << 21) | (2 << 16) | 9)),
         "kEntryCapacity"),
        # 3. the uploader stops stating the end.
        ("the uploader still states the array end as base+0x60",
         mutate(original, UPLOAD_END_INSN, addiu(0, 3, 0x40)),
         "array end"),
        # 4. plant a FOURTH writer of the cursor word: proves the scan counts writers.
        ("exactly three of them write the cursor word",
         mutate(original, 0x80015E50, word(0x80015E50, 0xAC241F68)),
         "exactly three of them write the cursor word"),
        # 5. break the cursor advance's per-iteration placement by turning the loop branch into a
        #    forward branch, i.e. the reading issues 0033/0034 made.
        ("the loop branch targets the band loop head at 0x80015F74",
         mutate(original, LOOP_BRANCH_INSN, struct.pack("<I", (0x05 << 26) | (0 << 21) | (2 << 16) | 0x0004)),
         "band loop head"),
        # 6. plant a capacity compare INSIDE the appender, which the "exactly one capacity-shaped
        #    compare" claim must notice — the same claim in the other direction.
        ("the appender contains exactly ONE capacity-shaped compare",
         mutate(original, 0x80015FEC, struct.pack("<I", (0x0B << 26) | (2 << 21) | (2 << 16) | 8)),
         "capacity-shaped compare"),
        # 7. move the shared buffer, so the record's source pointer is no longer the one the owner
        #    writes. This is the constant the measured fatal record's +8 word carries.
        ("kSharedGfxBuffer is 0x8016DEA8",
         mutate(original, SHARED_BUFFER_INSN_B, addiu(17, 17, 0xDE98)),
         "kSharedGfxBuffer"),
        # 8. move the update pass's frame allocation. This is the mutation that would make the two
        #    call sites straddle a function boundary, so the fatal-pass ordering argument would stop
        #    following from the image. The claim it breaks is the one that reads the frame push.
        ("the update pass opens its frame at 0x80021F34",
         mutate(original, 0x80021F34, addiu(29, 29, -0x20)),
         "opens its frame at 0x80021F34"),
        # 9. remove the appender call from the pass, which is the only way the two sites could stop
        #    being in the order the fault argument depends on.
        ("0x80022058 is a call to the appender",
         mutate(original, APPEND_PLAYER_CALL, word(APPEND_PLAYER_CALL, 0x00000000)),
         "0x80022058 is a call to the appender"),
        # 10. plant a FOURTH appender call site, so "seventeen" becomes a recognised list.
        ("seventeen `jal` sites reach the appender",
         mutate(original, 0x80015E50, word(0x80015E50, 0x0C0057B3)),
         "seventeen"),
    ]

    failures = 0
    for name, data, expect in cases:
        try:
            report = verify(Image(data))
            caught = any(expect in failure for failure in report.failures)
        except Exception as error:  # a reader that raises is also a caught mutation
            caught = True
            print(f"  (raised: {error})")
        print(f"{'caught' if caught else 'MISSED'}: mutation '{name}' must be caught, "
              f"and the failure must mention '{expect}'")
        if not caught:
            failures += 1
    print(f"selftest: {len(cases) - failures}/{len(cases)} mutations caught")
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify the authenticated image")
    parser.add_argument("--selftest", action="store_true",
                        help="prove each claim can report the other answer, on mutated copies")
    parser.add_argument("--image", help="path to an already-extracted SLUS_005.61")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not args.check:
        parser.print_help()
        return 2
    report = verify(Image(read_image(acquire_image(args.image))))
    for note in report.notes:
        print(f"note: {note}")
    if report.failures:
        print(f"FAILED: {len(report.failures)} of {report.comparisons} claim(s) disagree with the image")
        for failure in report.failures:
            print(f"  {failure}")
        return 1
    print(f"PASS: all {report.comparisons} claims match the authenticated image")
    return 0


if __name__ == "__main__":
    sys.exit(main())
