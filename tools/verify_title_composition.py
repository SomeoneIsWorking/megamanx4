#!/usr/bin/env python3
"""Derive Mega Man X4's fixed-screen title coordinate owners from retail SLUS_005.61.

The matching decomp supplied labels only. This verifier reads the retail state/object dispatch tables,
the title loop's update edges, the two title-only coordinate publication chains, and the complete
direct-call census for the common object renderer. It exists to prevent a widescreen fix from treating
that shared renderer as a title-specific patch site. It does not claim that every primitive produced by
the title loop has been semantically classified; matched title/gameplay captures remain the visual gate.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PSXPORT = Path(os.environ.get("PSXPORT_DIR", ROOT / "external/psxport"))
sys.path.insert(0, str(PSXPORT / "tools/recomp"))

import psexe  # resolved through PSXPORT exactly as the build resolves the framework

DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"

GAME_STATE_TABLE = 0x800F21B0
TITLE_STATE = 1
TITLE_LOOP = 0x8001E708
TITLE_MODE_TABLE = 0x800F2294
TITLE_SETUP = 0x8001DCCC
TITLE_MENU_SPAWNER = 0x8001E54C
MISC_OBJECT_TABLE = 0x800F2980
QUAD_OBJECT_TABLE = 0x800F2A70
COMMON_OBJECT_RENDERER = 0x80024334
TITLE_MENU_VARIANTS = 0x800F21F8
TITLE_LAYOUT_TABLE = 0x8010E71C
TITLE_QUAD_STATE_TABLE = 0x8010FDD0
WHITE_QUAD_INITIALIZER = 0x800D6F94
WHITE_QUAD_PRESETS = 0x8010FCCC

EXPECTED_MENU_VARIANTS = bytes((0x12, 0x13, 0x00, 0x0B, 0x0C, 0x04, 0x07, 0x09, 0x11))
EXPECTED_MENU_LAYOUT = {
    0x00: (144, 72, 0x00, 0x00),
    0x04: (160, 160, 0x04, 0x0A),
    0x07: (160, 216, 0x07, 0x0A),
    0x09: (288, 120, 0x09, 0x0A),
    0x0B: (208, 72, 0x1B, 0x04),
    0x0C: (248, 72, 0x1C, 0x04),
    0x11: (176, 216, 0x1F, 0x0A),
    0x12: (128, 72, 0x1A, 0x00),
    0x13: (176, 72, 0x20, 0x00),
}
EXPECTED_WHITE_QUAD = (319, 0, 319, 239, 0, 239, 0, 0)

TITLE_OBJECTS = {
    MISC_OBJECT_TABLE + 0x13 * 4: 0x800CB848,
    MISC_OBJECT_TABLE + 0x1D * 4: 0x800CDC84,
    QUAD_OBJECT_TABLE + 0x0B * 4: 0x800D76F8,
}

# Title loop calls after its mode-specific handler: effect, misc and quad updates, then the remaining
# front-end composition and draw steps. These are retail edges, not names borrowed from the decomp.
TITLE_LOOP_EDGES = {
    0x8001E7EC: 0x8002A7D0,
    0x8001E810: 0x8002166C,
    0x8001E818: 0x80021858,
    0x8001E820: 0x80021A20,
    0x8001E828: 0x8002A484,
    0x8001E830: 0x80023D68,
}

# All direct retail callers. Thirteen are in the object-pool draw walk; one is a separate caller.
# This denominator is what proves 0x80024334 is shared machinery rather than a title-specific seam.
COMMON_RENDER_CALLERS = (
    0x80023E88,
    0x80023EC8,
    0x80023EF8,
    0x80023F14,
    0x80023F48,
    0x80023F8C,
    0x80023FD0,
    0x80024014,
    0x80024058,
    0x8002409C,
    0x800240E0,
    0x80024124,
    0x80024158,
    0x80025D68,
)

# Exact instructions that connect title modes to their title-only coordinate tables. The tables carry
# the measurements; these words prove which variant selects them and where their x/y values publish.
TITLE_COORDINATE_PUBLICATION_WORDS = {
    # mode 0: func_8001DCCC spawns quad ID 0x0B, variant 0x0A
    0x8001DD40: 0x2404000B,
    0x8001DD74: 0x0C00771F,
    0x8001DD78: 0x2405000A,
    # mode 12: func_8001E54C spawns nine misc ID 0x13 variants from D_800F21F8
    0x8001E5AC: 0x00008021,
    0x8001E5B0: 0x24130001,
    0x8001E5B4: 0x24120013,
    0x8001E5B8: 0x0C00AB94,
    0x8001E5CC: 0xA0730000,
    0x8001E5D0: 0xA0720001,
    0x8001E5D4: 0x3C01800F,
    0x8001E5D8: 0x00300821,
    0x8001E5DC: 0x902221F8,
    0x8001E5E4: 0xA0620002,
    0x8001E5E8: 0x26100001,
    0x8001E5EC: 0x2E020009,
    0x8001E5F0: 0x1440FFF1,
    # misc ID 0x13 state 0 indexes six-byte D_8010E71C records and publishes x/y as s16.16
    0x800CB654: 0x90860002,
    0x800CB670: 0x00062840,
    0x800CB674: 0x00A62821,
    0x800CB680: 0x00052840,
    0x800CB6B4: 0x3C018011,
    0x800CB6B8: 0x00250821,
    0x800CB6BC: 0x8422E71C,
    0x800CB6C4: 0x00021400,
    0x800CB6C8: 0xAC820008,
    0x800CB6CC: 0x3C018011,
    0x800CB6D0: 0x00250821,
    0x800CB6D4: 0x8422E71E,
    0x800CB6DC: 0x00021400,
    0x800CB6E0: 0xAC82000C,
    # quad ID 0x0B state 0 indexes 16-byte D_8010FCCC records by variant
    0x800D6F9C: 0x80820002,
    0x800D6FAC: 0x3C058011,
    0x800D6FB0: 0x24A5FCCC,
    0x800D6FBC: 0x00021100,
    0x800D6FC0: 0x00451021,
    0x800D6FCC: 0x94430000,
    0x800D6FD4: 0xA4830016,
    0x800D7020: 0x94420002,
    0x800D7028: 0xA4820032,
}


class Refused(RuntimeError):
    """The input cannot support the assertion; empty or partial evidence never passes."""


def load_image(path: Path) -> psexe.PsxExe:
    if not path.is_file():
        raise Refused(f"{path} does not exist; inspected 0 retail bytes")
    try:
        return psexe.load(str(path))
    except (OSError, ValueError, struct.error) as exc:
        raise Refused(
            f"{path} is not a loadable PS-X EXE; inspected 0 retail bytes: {exc}"
        ) from exc


def jump_target(pc: int, instruction: int) -> int:
    return ((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)


def expect_word(image: psexe.PsxExe, address: int, expected: int, label: str) -> None:
    actual = image.word(address)
    if actual != expected:
        raise Refused(
            f"{label} at 0x{address:08X}: word 0x{actual:08X}, want 0x{expected:08X}"
        )


def read_bytes(image: psexe.PsxExe, address: int, size: int) -> bytes:
    offset = address - image.load
    if offset < 0 or offset + size > len(image.text):
        raise Refused(
            f"read [0x{address:08X},0x{address + size:08X}) is outside loaded retail text"
        )
    return image.text[offset : offset + size]


def expect_bytes(
    image: psexe.PsxExe, address: int, expected: bytes, label: str
) -> None:
    actual = read_bytes(image, address, len(expected))
    if actual != expected:
        raise Refused(
            f"{label} at 0x{address:08X}: bytes {actual.hex()}, want {expected.hex()}"
        )


def expect_jal(image: psexe.PsxExe, pc: int, expected: int, label: str) -> None:
    instruction = image.word(pc)
    if instruction >> 26 != 3:
        raise Refused(f"{label} at 0x{pc:08X}: word 0x{instruction:08X} is not jal")
    actual = jump_target(pc, instruction)
    if actual != expected:
        raise Refused(
            f"{label} at 0x{pc:08X}: target 0x{actual:08X}, want 0x{expected:08X}"
        )


def direct_callers(image: psexe.PsxExe, target: int) -> tuple[int, ...]:
    callers: list[int] = []
    for offset in range(0, image.text_size, 4):
        pc = image.load + offset
        instruction = struct.unpack_from("<I", image.text, offset)[0]
        if instruction >> 26 == 3 and jump_target(pc, instruction) == target:
            callers.append(pc)
    return tuple(callers)


def verify(image: psexe.PsxExe) -> list[str]:
    expect_word(
        image, GAME_STATE_TABLE + TITLE_STATE * 4, TITLE_LOOP, "front-end state 1 owner"
    )

    # func_8001DAF8 materializes 0x80173C7D, subtracts 13 to get game_info=0x80173C70,
    # reads byte 0, and indexes D_800F21B0 before its indirect call.
    dispatch_words = {
        0x8001DB00: 0x3C108017,
        0x8001DB04: 0x26103C7D,
        0x8001DB30: 0x2610FFF3,
        0x8001DB34: 0x3C12800F,
        0x8001DB38: 0x265221B0,
        0x8001DB40: 0x82020000,
        0x8001DB48: 0x00021080,
        0x8001DB4C: 0x00521021,
        0x8001DB50: 0x8C420000,
        0x8001DB58: 0x0040F809,
        0x8001DB5C: 0x02002021,
    }
    for pc, instruction in dispatch_words.items():
        expect_word(image, pc, instruction, "game_info state-table dispatch")

    for slot, owner in TITLE_OBJECTS.items():
        expect_word(image, slot, owner, "title object dispatch")
    for pc, target in TITLE_LOOP_EDGES.items():
        expect_jal(image, pc, target, "title-loop update/draw edge")

    expect_word(image, TITLE_MODE_TABLE, TITLE_SETUP, "title mode 0 setup")
    expect_word(
        image,
        TITLE_MODE_TABLE + 12 * 4,
        TITLE_MENU_SPAWNER,
        "title mode 12 menu spawner",
    )
    for pc, instruction in TITLE_COORDINATE_PUBLICATION_WORDS.items():
        expect_word(image, pc, instruction, "title coordinate publication")

    expect_bytes(
        image,
        TITLE_MENU_VARIANTS,
        EXPECTED_MENU_VARIANTS,
        "title menu variant list",
    )
    for variant, expected in EXPECTED_MENU_LAYOUT.items():
        record = read_bytes(image, TITLE_LAYOUT_TABLE + variant * 6, 6)
        actual = struct.unpack("<hhBB", record)
        if actual != expected:
            raise Refused(
                f"title layout variant 0x{variant:02X}: {actual}, want {expected}"
            )

    expect_word(
        image,
        TITLE_QUAD_STATE_TABLE,
        WHITE_QUAD_INITIALIZER,
        "title quad state-0 owner",
    )
    white_quad = struct.unpack(
        "<8h", read_bytes(image, WHITE_QUAD_PRESETS + 0x0A * 16, 16)
    )
    if white_quad != EXPECTED_WHITE_QUAD:
        raise Refused(
            f"title white-quad variant 0x0A: {white_quad}, want {EXPECTED_WHITE_QUAD}"
        )

    callers = direct_callers(image, COMMON_OBJECT_RENDERER)
    if callers != COMMON_RENDER_CALLERS:
        raise Refused(
            f"scanned {image.text_size // 4} loaded words; common renderer callers were {callers}, "
            f"want {COMMON_RENDER_CALLERS}"
        )

    return [
        "game_info byte 0 indexes the retail front-end state table, whose state 1 owner is 0x8001E708",
        "misc IDs 0x13/0x1D and quad ID 0x0B resolve to the three title object owners",
        "title state 1 retains all six measured effect/misc/quad/composition edges",
        "title mode 12 publishes nine measured logo/menu records through title-only table 0x8010E71C",
        "title mode 0 spawns quad ID 0x0B variant 0x0A, whose title-only row is the 320x240 edge quad",
        f"scanned all {image.text_size // 4} loaded words and found 14 direct callers of shared renderer 0x80024334",
    ]


def mutate(image: psexe.PsxExe, pc: int, instruction: int) -> psexe.PsxExe:
    offset = pc - image.load
    changed = bytearray(image.text)
    struct.pack_into("<I", changed, offset, instruction)
    return dataclasses.replace(image, text=bytes(changed))


def mutate_bytes(
    image: psexe.PsxExe, address: int, changed_bytes: bytes
) -> psexe.PsxExe:
    offset = address - image.load
    changed = bytearray(image.text)
    changed[offset : offset + len(changed_bytes)] = changed_bytes
    return dataclasses.replace(image, text=bytes(changed))


def selftest(image: psexe.PsxExe) -> None:
    cases = [
        ("retail positive", image, True),
        ("removed title state owner", mutate(image, GAME_STATE_TABLE + 4, 0), False),
        (
            "wrong title logo object",
            mutate(image, MISC_OBJECT_TABLE + 0x1D * 4, 0x800CB848),
            False,
        ),
        ("removed title misc update", mutate(image, 0x8001E818, 0), False),
        (
            "removed shared-renderer caller",
            mutate(image, COMMON_RENDER_CALLERS[0], 0),
            False,
        ),
        (
            "changed menu variant list",
            mutate_bytes(image, TITLE_MENU_VARIANTS, bytes((0x00,))),
            False,
        ),
        (
            "changed menu coordinate publication",
            mutate(image, 0x800CB6C8, 0),
            False,
        ),
        (
            "changed title menu coordinate",
            mutate_bytes(image, TITLE_LAYOUT_TABLE + 0x12 * 6, struct.pack("<h", 129)),
            False,
        ),
        (
            "changed white-quad spawn variant",
            mutate(image, 0x8001DD78, 0x24050009),
            False,
        ),
        (
            "changed white-quad edge",
            mutate_bytes(
                image,
                WHITE_QUAD_PRESETS + 0x0A * 16,
                struct.pack("<h", 318),
            ),
            False,
        ),
    ]
    for name, fixture, should_pass in cases:
        try:
            verify(fixture)
            actual = True
        except Refused:
            actual = False
        if actual != should_pass:
            raise Refused(
                f"selftest {name}: expected {'PASS' if should_pass else 'FAIL'}"
            )
        print(
            f"[title-composition:selftest] PASS {name} -> {'accepted' if actual else 'rejected'}"
        )
    print(f"[title-composition:selftest] PASS {len(cases)}/{len(cases)} cases")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument(
        "--check", action="store_true", help="verify the retail title-owner boundary"
    )
    parser.add_argument(
        "--selftest", action="store_true", help="prove the verifier accepts and rejects"
    )
    args = parser.parse_args()

    try:
        if hashlib.sha1(args.exe.read_bytes()).hexdigest() != EXPECTED_SHA1:
            raise Refused(
                f"{args.exe} is not retail SLUS_005.61 (whole-file SHA-1 mismatch)"
            )
        image = load_image(args.exe)
        if args.check or not args.selftest:
            for line in verify(image):
                print(f"[title-composition] PASS {line}")
            print(
                "[title-composition] BLIND SPOT: the two measured title coordinate publications do "
                "not classify every emitted primitive or prove visual placement; matched "
                "title/gameplay captures remain required"
            )
        if args.selftest:
            selftest(image)
        return 0
    except (OSError, Refused) as exc:
        print(f"[title-composition] REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
