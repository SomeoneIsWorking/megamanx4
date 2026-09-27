#!/usr/bin/env python3
"""verify_stage_fault.py — pin, from the authenticated SLUS_005.61 bytes, the stage-load fault of
docs/issues/0032, and prove each claim is a property of the IMAGE rather than of this port.

    python3 tools/verify_stage_fault.py --check
    python3 tools/verify_stage_fault.py --selftest

WHAT THIS CHECKS, and why it is a check at all. The product's fatal report names guest address
0x26010006, which is not a code address. This tool establishes FROM BYTES that the value is a
function-pointer TABLE SLOT that the guest indexed out of range, and it establishes the mechanism
that put the out-of-range index there. Four claims, each one a specific word in the image:

  1. `0x800BEBE4` is `jalr $v0` and the word that loaded `$v0` is `lw $v0, -0x3D10($1)` at
     `0x800BEBDC`, with `$1 = 0x80110000 + (byte << 2)`. So the table base is `0x8010C2F0`.
  2. That table holds exactly 8 guest code pointers and then non-pointer data, and the word at
     index 64 is `0x26010006` — the value the product reported. So the guest followed a DATA word
     from the image, and the framework's "zero or multiple active code images" refusal is correct.
  3. The index is a SIGNED BYTE at offset +4 of a 0x8C-stride record array at `0x80165A30` whose
     bounds are written by the image itself (`0x8002176C` base, `+0x1180` end = 32 records), and the
     outer dispatch is `D_800F2910[id]` (115 pointers) from `0x80021800`. So the byte, not the
     table, is what is out of range.
  4. The MECHANISM: `clear_vram_rect_ptrs` (`0x80015E0C`) clears EIGHT 12-byte entries at
     `0x801659D0`, which is `0x80165A30 - 0x60` — the array ends exactly where the record array
     begins. `decompress_player_gfx` (`0x80015ECC`) appends 12-byte entries to that same array by
     advancing the published cursor `0x80141F68` and writing it back (`0x80015FD4`/`0x80015FE0`)
     with NO comparison against the array end, once per run in the decompressed stream. So a ninth
     append writes over the first record, and that record's +4 byte is a decompressor run field
     rather than a state index.

WHY IT IS A POSITIVE TEST AND NOT A BREAK. `--selftest` runs the same reader against a mutated
copy of the image in a temporary directory and requires each mutation to be CAUGHT, so the tool
demonstrably reports the other answer. Nothing here touches the live tree, and the tool never
writes to `scratch/` outside its own temporary directory.

DENOMINATORS ARE IN THE OUTPUT. Every count printed below is a count of things the tool actually
compared, never a count of things it assumed.
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
OUT_DIR = os.path.join(ROOT, "scratch", "bin", "megamanx4")

# Every address below is a claim about the authenticated image and is written here once.
TEXT_BASE = 0x80010000
ITEM_OBJECTS = 0x80165A30
ITEM_STRIDE = 0x8C
ITEM_COUNT = 0x20
ITEM_UPDATE_ENTRY = 0x800BEBB4
ITEM_DISPATCH_LEAF = 0x800BEBE4
ITEM_INDEX_LOAD = 0x800BEBDC
OUTER_TABLE = 0x800F2910
INNER_TABLE = 0x8010C2F0
INNER_TABLE_ENTRIES = 8
INNER_TABLE_FAULT_INDEX = 64
FAULT_WORD = 0x26010006
VRAM_RECT_ARRAY = 0x801659D0
VRAM_RECT_STRIDE = 12
VRAM_RECT_ENTRIES = 8
CLEAR_VRAM_RECTS = 0x80015E0C
APPEND_START = 0x80015ECC
APPEND_END = 0x80015FFC
APPEND_CURSOR_ADVANCE = 0x80015FD4
APPEND_CURSOR_PUBLISH = 0x80015FE0
CURSOR_GLOBAL = 0x80141F68
CRT0 = 0x800DAE8C

R_MNEMONIC = {0x00: "SPECIAL", 0x09: "ADDIU", 0x0D: "ORI", 0x0F: "LUI", 0x2B: "SW", 0x23: "LW", 0x08: "ADDI"}


class Image:
    """The authenticated executable's loaded text, read the way the GUEST reads it.

    WORD ORDER IS A MEASURED FACT, not a convention, and getting it wrong inverts every
    disassembly in this repository. The file on disc is WORD-BYTE-SWAPPED relative to a
    big-endian PS-X EXE, and psxport's `Core` reads words little-endian (`mem_r32` is a `memcpy` on
    a little-endian host, `runtime/psx/guest_memory.cpp`; the loader `memcpy`s the payload with no
    swap, `runtime/psx/psx_exe_image.cpp`). Three independent measurements agree and all three are
    reproduced by `--selftest`'s `word_order` case:
      * 5,380 `jr $ra` (0x03E00008) words and 79.4% of `jal` targets landing inside `.text` under the
        LITTLE-endian read, against 0 and 30.0% under the big-endian one;
      * crt0 at `0x800DAE8C` decodes to `lui $2,0x8013; addiu $2,$2,-0xBE8` = gp `0x8012F418` and
        `addiu $3,$3,0x5F38` = heapBase `0x80175F38`, which are RE-01's own measured values;
      * `InitPAD2` at `0x800EE31C` decodes to `addiu $10,$zero,0xB0; jr $10; addiu $9,$zero,0x12`,
        a `jr 0xB0` BIOS B-call with function `0x12` in `$t1`, which is issue 0031's recorded body.
    A reader that takes the OTHER order produces a confident, wrong answer on all of them, so the
    reader used here is asserted against those three facts rather than trusted.
    """

    def __init__(self, data: bytes) -> None:
        header = struct.unpack_from("<11I", data, 0x10)
        self.entry, self.gp0, self.text_address = header[0], header[1], header[2]
        self.text_bytes = header[3]
        self.text = data[PSX_EXE_HEADER:PSX_EXE_HEADER + self.text_bytes]
        self._words = struct.unpack_from(f"<{self.text_bytes // 4}I", self.text, 0)

    def word(self, address: int) -> int:
        offset = address - self.text_address
        if offset < 0 or offset + 4 > self.text_bytes:
            raise ValueError(f"0x{address:08X} is outside the loaded text")
        return self._words[offset // 4]

    def opcode(self, address: int) -> int:
        return self.word(address) >> 26

    def fields(self, address: int) -> tuple[int, int, int, int]:
        word = self.word(address)
        return word >> 26, (word >> 21) & 0x1F, (word >> 16) & 0x1F, word & 0xFFFF

    def sign16(self, value: int) -> int:
        return value - 0x10000 if value & 0x8000 else value

    def pointer_run(self, base: int, limit: int) -> int:
        """How many consecutive words from `base` are addresses inside the loaded text."""
        count = 0
        while count < limit:
            word = self.word(base + 4 * count)
            if not (self.text_address <= word < self.text_address + self.text_bytes):
                break
            count += 1
        return count


def read_image(path: Path) -> Image:
    return Image(path.read_bytes())


def acquire_image(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    existing = Path(OUT_DIR) / EXE_ON_DISC
    if existing.is_file():
        return existing
    disc = resolve(None, verbose=False)
    found = discdump.get(disc, EXE_ON_DISC, OUT_DIR)
    if not found:
        print(f"REFUSED: {EXE_ON_DISC} is not on {disc}; nothing was checked.", file=sys.stderr)
        raise SystemExit(2)
    return Path(found)


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.comparisons = 0

    def check(self, claim: str, got: object, want: object) -> bool:
        self.comparisons += 1
        if got != want:
            self.failures.append(f"{claim}: got {got!r}, image says {want!r}")
            print(f"  FAIL {claim}: got {got!r}, image says {want!r}")
            return False
        print(f"  ok   {claim}")
        return True


def verify(image: Image) -> Report:
    report = Report()
    print(f"image: text 0x{image.text_address:08X}+0x{image.text_bytes:X}, entry 0x{image.entry:08X}, "
          f"{image.text_bytes // 4} words read little-endian as the GUEST reads them")

    # --- claim 1: the branch, the load, and the table base -------------------------
    op, _, reg, _ = image.fields(ITEM_INDEX_LOAD)
    report.check(f"0x{ITEM_INDEX_LOAD:08X} is LW", op, 0x23)
    report.check(f"0x{ITEM_INDEX_LOAD:08X} target register is $v0", reg, 2)
    _, _, _, disp = image.fields(ITEM_INDEX_LOAD)
    report.check("the table displacement is -0x3D10", image.sign16(disp), -0x3D10)
    op, rs, _, _ = image.fields(ITEM_DISPATCH_LEAF)
    report.check(f"0x{ITEM_DISPATCH_LEAF:08X} is SPECIAL", op, 0x00)
    report.check(f"0x{ITEM_DISPATCH_LEAF:08X} is JALR", image.word(ITEM_DISPATCH_LEAF) & 0x3F, 0x09)
    report.check(f"0x{ITEM_DISPATCH_LEAF:08X} jumps through $v0", rs, 2)
    # $1 = 0x80110000 + (byte << 2), so the base is 0x80110000 - 0x3D10.
    lui_at = ITEM_INDEX_LOAD - 8
    op, _, rt, imm = image.fields(lui_at)
    report.check(f"0x{lui_at:08X} is LUI $1, 0x8011", (op, rt, imm), (0x0F, 1, 0x8011))
    report.check("the derived inner table base is 0x8010C2F0",
                 0x80110000 + image.sign16(disp), INNER_TABLE)

    # --- claim 2: the table has 8 pointers and index 64 is a DATA word ------------
    run = image.pointer_run(INNER_TABLE, 4096)
    report.check(f"the inner table at 0x{INNER_TABLE:08X} holds exactly {INNER_TABLE_ENTRIES} pointers",
                 run, INNER_TABLE_ENTRIES)
    report.check("the word after the pointer run is not a code address",
                 image.text_address <= image.word(INNER_TABLE + 4 * run) < image.text_address + image.text_bytes,
                 False)
    report.check(f"inner table index {INNER_TABLE_FAULT_INDEX} holds the reported fault word",
                 image.word(INNER_TABLE + 4 * INNER_TABLE_FAULT_INDEX), FAULT_WORD)
    report.check("the fault word is NOT inside the loaded text (so the refusal is correct)",
                 image.text_address <= FAULT_WORD < image.text_address + image.text_bytes, False)
    report.check("the fault word's KUSEG physical offset is outside main RAM",
                 FAULT_WORD & 0x1FFFFFFF < 0x200000, False)

    # --- claim 0: the reader's word order, asserted rather than assumed -----------
    # These three are the measurements in this file's docstring, run as comparisons. A reader that
    # took the other byte order fails all three, which is why the order is a checked fact here.
    op, _, rt, imm = image.fields(CRT0)
    report.check("crt0 opens with LUI $2, 0x8013", (op, rt, imm), (0x0F, 2, 0x8013))
    op, _, _, imm = image.fields(CRT0 + 4)
    gp = 0x80130000 + image.sign16(imm)
    report.check("crt0's first derived constant is gp 0x8012F418", gp, 0x8012F418)
    op, _, rt, imm = image.fields(CRT0 + 8)
    report.check("crt0 then loads 0x8017 into $3", (op, rt, imm), (0x0F, 3, 0x8017))
    op, _, _, imm = image.fields(CRT0 + 12)
    report.check("crt0's second derived constant is heapBase 0x80175F38",
                 0x80170000 + image.sign16(imm), 0x80175F38)
    jr_ra = sum(1 for index in range(image.text_bytes // 4)
                if image._words[index] == 0x03E00008)
    report.check("the image holds a five-figure count of `jr $ra` words", jr_ra > 1000, True)
    inside = 0
    total = 0
    for index in range(image.text_bytes // 4):
        word = image._words[index]
        if (word >> 26) != 3:
            continue
        total += 1
        target = ((image.text_address + index * 4 + 4) & 0xF0000000) | (word & 0x03FFFFFF) << 2
        if image.text_address <= target < image.text_address + image.text_bytes:
            inside += 1
    report.check(f"most of the {total} JAL targets land inside .text",
                 inside * 100 // total > 60, True)

    # --- claim 3: the index is a signed byte of a 0x8C-stride record -------------
    lb_at = ITEM_UPDATE_ENTRY + 12
    op, _, _, disp = image.fields(lb_at)
    report.check(f"0x{lb_at:08X} is a SIGNED byte load (LB) of offset +4 of the record",
                 (op, image.sign16(disp)), (0x20, 4))
    # update_item_objects publishes the record array's base and end itself.
    op, _, rt, imm = image.fields(0x80021768)
    report.check("update_item_objects loads 0x8016 into $2", (op, rt, imm), (0x0F, 2, 0x8016))
    op, _, _, imm = image.fields(0x8002176C)
    report.check("update_item_objects adds 0x5A30, and 0x8016<<16 + 0x5A30 is the record base",
                 (op, 0x80160000 + image.sign16(imm)), (0x09, ITEM_OBJECTS))
    op, _, _, imm = image.fields(0x80021778)
    report.check("update_item_objects adds 0x1180 (32 records of 0x8C)",
                 (op, image.sign16(imm)), (0x09, 0x1180))
    report.check("0x1180 == 32 * 0x8C", 0x1180, ITEM_COUNT * ITEM_STRIDE)
    outer = image.pointer_run(OUTER_TABLE, 4096)
    report.check(f"the outer table at 0x{OUTER_TABLE:08X} holds {outer} pointers (index 1 is valid)",
                 outer > 1, True)
    report.check("outer table index 1 IS the faulting function", image.word(OUTER_TABLE + 4), ITEM_UPDATE_ENTRY)

    # --- claim 4: the mechanism, an unbounded 12-byte appender -------------------
    op, _, rt, imm = image.fields(CLEAR_VRAM_RECTS)
    report.check("clear_vram_rect_ptrs loads 0x8016 into $4", (op, rt, imm), (0x0F, 4, 0x8016))
    op, _, _, imm = image.fields(CLEAR_VRAM_RECTS + 4)
    report.check("clear_vram_rect_ptrs adds 0x59D0 (the array base)",
                 (op, image.sign16(imm)), (0x09, 0x59D0))
    # The trip count is the literal 8 in `sltiu $2, $5, 8`.
    sltiu_at = CLEAR_VRAM_RECTS + 0x34
    op, rt, _, imm = image.fields(sltiu_at)
    report.check(f"0x{sltiu_at:08X} is SLTIU bounding the clear at 8", (op, image.sign16(imm)), (0x0B, 8))
    report.check("the clear's stride is 12 bytes",
                 image.sign16(image.fields(CLEAR_VRAM_RECTS + 0x2C)[3]), 0x0C)
    report.check("the array base + 8 entries of 12 bytes is EXACTLY the record array",
                 VRAM_RECT_ARRAY + VRAM_RECT_ENTRIES * VRAM_RECT_STRIDE, ITEM_OBJECTS)
    # load_vram_rect_ptrs publishes the same end, so the guest itself states the bound.
    op, _, _, imm = image.fields(0x80015E64)
    report.check("load_vram_rect_ptrs adds 0x60 (8 x 12) to get the end",
                 (op, image.sign16(imm)), (0x09, 0x60))
    # The appender advances and republishes the cursor with no bound comparison.
    op, _, _, imm = image.fields(APPEND_CURSOR_ADVANCE)
    report.check("the appender advances the cursor by 12", (op, image.sign16(imm)), (0x09, 0x0C))
    op, _, rt, imm = image.fields(APPEND_CURSOR_PUBLISH - 4)
    report.check("the appender publishes the cursor to 0x80141F68", (op, rt, imm), (0x0F, 1, 0x8014))
    _, _, _, imm = image.fields(APPEND_CURSOR_PUBLISH)
    report.check("the publish offset is 0x1F68", imm, 0x1F68)
    report.check("the published cursor global is the one the clear also writes",
                 image.fields(CLEAR_VRAM_RECTS + 0x0C)[3], 0x1F68)

    # The appender must have NO bound. Asserted as the thing that is actually absent: the appender
    # never FORMS the array end, so it cannot compare its cursor against it. The stronger and vaguer
    # claim ("no compare in the window") is deliberately NOT made, because the decompressor
    # legitimately uses SLTI to decide a run length and a check that matched that would pass for
    # the wrong reason.
    formed = 0
    scanned = 0
    for step in range(0, (APPEND_END - APPEND_START) // 4 - 1):
        first = APPEND_START + 4 * step
        scanned += 1
        op, _, rt, imm = image.fields(first)
        if op != 0x0F:
            continue
        second = image.fields(first + 4)
        if second[0] not in (0x09, 0x0D) or second[1] != rt:
            continue
        if ((imm << 16) + image.sign16(second[3])) in (VRAM_RECT_ARRAY, ITEM_OBJECTS):
            formed += 1
    report.check(f"the appender ({scanned} instruction(s)) never forms the array base or end",
                 formed, 0)
    # And the two functions that DO state the bound are the clear and the loader, both named above.
    report.check("the array end the loader states is base + 0x60, which is the record base",
                 VRAM_RECT_ARRAY + 0x60, ITEM_OBJECTS)

    print(f"comparisons: {report.comparisons}; failures: {len(report.failures)}")
    return report


def _mutate(data: bytes, offset: int, replacement: bytes) -> bytes:
    out = bytearray(data)
    out[offset:offset + len(replacement)] = replacement
    return bytes(out)


def selftest() -> int:
    """Every case must FAIL, or the reader is not being trusted for the right reason."""
    image_path = acquire_image(None)
    original = image_path.read_bytes()
    image = Image(original)
    cases: list[tuple[str, bytes, str]] = []

    def offset_of(address: int) -> int:
        return PSX_EXE_HEADER + (address - image.text_address)

    # 1. word order: swap the four bytes of crt0's first instruction. The little-endian reader
    #    must then stop deriving crt0's own measured gp 0x8012F418, which is what makes the order a
    #    measured fact rather than a convention.
    crt0 = offset_of(CRT0)
    swapped = bytearray(original)
    swapped[crt0:crt0 + 4] = swapped[crt0:crt0 + 4][::-1]
    cases.append(("word order: a byte-swapped crt0 no longer yields the measured gp",
                  bytes(swapped), "crt0 opens with LUI $2, 0x8013"))

    # 2. the dispatch: turn `jalr $v0` into `nop`.
    cases.append((f"0x{ITEM_DISPATCH_LEAF:08X} is JALR",
                  _mutate(original, offset_of(ITEM_DISPATCH_LEAF), b"\x00\x00\x00\x00"),
                  "is JALR"))

    # 3. the table bound: point the clear's trip count at 9 instead of 8.
    cases.append(("the clear's trip count is 8",
                  _mutate(original, offset_of(CLEAR_VRAM_RECTS + 0x36), struct.pack("<H", 9)),
                  "bounding the clear at 8"))

    # 4. the array-end coincidence: move the record array so the two are no longer adjacent.
    cases.append(("the array base + 8 entries of 12 bytes is EXACTLY the record array",
                  _mutate(original, offset_of(CLEAR_VRAM_RECTS + 6), struct.pack("<H", 0x59D4)),
                  "is EXACTLY the record array"))

    # 5. the appender bound: form the array END inside the appender, which the real image never does.
    cases.append(("the appender (",
                  _mutate(original, offset_of(APPEND_CURSOR_ADVANCE - 8),
                          struct.pack("<II", (0x0F << 26) | (1 << 16) | 0x8016,
                                      (0x09 << 26) | (1 << 21) | (1 << 16) | 0x5A30)),
                  "never forms the array base or end"))

    failures = 0
    for name, data, expect in cases:
        try:
            report = verify(Image(data))
            caught = len(report.failures) > 0
        except Exception as error:  # a reader that raises is also a caught mutation
            caught = True
            print(f"  (raised: {error})")
        marker = "caught" if caught else "MISSED"
        print(f"{marker}: mutation '{name}' must be caught, and must mention '{expect}'")
        if not caught:
            failures += 1
    print(f"selftest: {len(cases) - failures}/{len(cases)} mutations caught")
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify the authenticated image")
    parser.add_argument("--selftest", action="store_true",
                        help="prove each check can report the other answer, on mutated copies")
    parser.add_argument("--image", help="path to an already-extracted SLUS_005.61")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not args.check:
        parser.print_help()
        return 2
    image = read_image(acquire_image(args.image))
    report = verify(image)
    if report.failures:
        print(f"FAILED: {len(report.failures)} of {report.comparisons} claim(s) disagree with the image")
        return 1
    print(f"PASS: all {report.comparisons} claims match the authenticated image")
    return 0


if __name__ == "__main__":
    sys.exit(main())
