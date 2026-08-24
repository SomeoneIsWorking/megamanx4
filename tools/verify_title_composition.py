#!/usr/bin/env python3
"""Derive Mega Man X4's fixed-screen title owner from retail SLUS_005.61.

The matching decomp supplied labels only. This verifier reads the retail state/object dispatch tables,
the title loop's update edges, and the complete direct-call census for the common object renderer. It
exists to prevent a widescreen fix from treating that shared renderer as a title-specific patch site.
It does not claim that every primitive produced by the title loop has been semantically classified;
matched title/gameplay captures remain the visual gate.
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
MISC_OBJECT_TABLE = 0x800F2980
QUAD_OBJECT_TABLE = 0x800F2A70
COMMON_OBJECT_RENDERER = 0x80024334

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


class Refused(RuntimeError):
    """The input cannot support the assertion; empty or partial evidence never passes."""


def load_image(path: Path) -> psexe.PsxExe:
    if not path.is_file():
        raise Refused(f"{path} does not exist; inspected 0 retail bytes")
    try:
        return psexe.load(str(path))
    except (OSError, ValueError, struct.error) as exc:
        raise Refused(f"{path} is not a loadable PS-X EXE; inspected 0 retail bytes: {exc}") from exc


def jump_target(pc: int, instruction: int) -> int:
    return ((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)


def expect_word(image: psexe.PsxExe, address: int, expected: int, label: str) -> None:
    actual = image.word(address)
    if actual != expected:
        raise Refused(f"{label} at 0x{address:08X}: word 0x{actual:08X}, want 0x{expected:08X}")


def expect_jal(image: psexe.PsxExe, pc: int, expected: int, label: str) -> None:
    instruction = image.word(pc)
    if instruction >> 26 != 3:
        raise Refused(f"{label} at 0x{pc:08X}: word 0x{instruction:08X} is not jal")
    actual = jump_target(pc, instruction)
    if actual != expected:
        raise Refused(f"{label} at 0x{pc:08X}: target 0x{actual:08X}, want 0x{expected:08X}")


def direct_callers(image: psexe.PsxExe, target: int) -> tuple[int, ...]:
    callers: list[int] = []
    for offset in range(0, image.text_size, 4):
        pc = image.load + offset
        instruction = struct.unpack_from("<I", image.text, offset)[0]
        if instruction >> 26 == 3 and jump_target(pc, instruction) == target:
            callers.append(pc)
    return tuple(callers)


def verify(image: psexe.PsxExe) -> list[str]:
    expect_word(image, GAME_STATE_TABLE + TITLE_STATE * 4, TITLE_LOOP, "front-end state 1 owner")

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
        f"scanned all {image.text_size // 4} loaded words and found 14 direct callers of shared renderer 0x80024334",
    ]


def mutate(image: psexe.PsxExe, pc: int, instruction: int) -> psexe.PsxExe:
    offset = pc - image.load
    changed = bytearray(image.text)
    struct.pack_into("<I", changed, offset, instruction)
    return dataclasses.replace(image, text=bytes(changed))


def selftest(image: psexe.PsxExe) -> None:
    cases = [
        ("retail positive", image, True),
        ("removed title state owner", mutate(image, GAME_STATE_TABLE + 4, 0), False),
        ("wrong title logo object", mutate(image, MISC_OBJECT_TABLE + 0x1D * 4, 0x800CB848), False),
        ("removed title misc update", mutate(image, 0x8001E818, 0), False),
        ("removed shared-renderer caller", mutate(image, COMMON_RENDER_CALLERS[0], 0), False),
    ]
    for name, fixture, should_pass in cases:
        try:
            verify(fixture)
            actual = True
        except Refused:
            actual = False
        if actual != should_pass:
            raise Refused(f"selftest {name}: expected {'PASS' if should_pass else 'FAIL'}")
        print(f"[title-composition:selftest] PASS {name} -> {'accepted' if actual else 'rejected'}")
    print(f"[title-composition:selftest] PASS {len(cases)}/{len(cases)} cases")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--check", action="store_true", help="verify the retail title-owner boundary")
    parser.add_argument("--selftest", action="store_true", help="prove the verifier accepts and rejects")
    args = parser.parse_args()

    try:
        if hashlib.sha1(args.exe.read_bytes()).hexdigest() != EXPECTED_SHA1:
            raise Refused(f"{args.exe} is not retail SLUS_005.61 (whole-file SHA-1 mismatch)")
        image = load_image(args.exe)
        if args.check or not args.selftest:
            for line in verify(image):
                print(f"[title-composition] PASS {line}")
            print(
                "[title-composition] BLIND SPOT: static ownership does not classify every emitted "
                "primitive or prove visual placement; matched title/gameplay captures remain required"
            )
        if args.selftest:
            selftest(image)
        return 0
    except (OSError, Refused) as exc:
        print(f"[title-composition] REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
