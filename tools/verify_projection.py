#!/usr/bin/env python3
"""Measure every MMX4 write to the GTE projection registers from the retail executable.

RE-08 cannot safely attach widescreen behavior until every CR24 (OFX), CR25 (OFY), and CR26 (H)
writer is known. This verifier scans the complete loaded image for raw CTC2 instructions, scans every
JAL for calls to the three owning Psy-Q routines, and checks the boot call's immediate arguments.

The matching AGPL decomp supplied the names only. The addresses, call counts, arguments, and complete
writer census below are asserted against SLUS_005.61 itself. The remaining blind spot is runtime role:
the census proves there is no later static writer, but the boot scheduler must work before a wide
picture can be classified visually.
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
sys.path.insert(0, str(PSXPORT))

from tools.formats import psx_exe as psexe  # resolved exactly as the build resolves psxport

DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"

INIT_GEOM = 0x800E9040
SET_GEOM_OFFSET = 0x800E90C8
SET_GEOM_SCREEN = 0x800E90E8

# Complete retail CR24/25/26 writer set. The first three belong to InitGeom, the next two to
# SetGeomOffset, and the last to SetGeomScreen. Any added or missing address means the classification
# has changed and RE-08 must be revisited before a projection patch is trusted.
EXPECTED_WRITERS = (
    (0x800E908C, 8, 26),
    (0x800E90AC, 0, 24),
    (0x800E90B0, 0, 25),
    (0x800E90D0, 4, 24),
    (0x800E90D4, 5, 25),
    (0x800E90E8, 4, 26),
)

EXPECTED_CALLS = {
    INIT_GEOM: (0x80012164,),
    SET_GEOM_OFFSET: (0x80012170,),
    SET_GEOM_SCREEN: (0x80012178,),
}


class Refused(RuntimeError):
    """The input cannot support the assertion; never turn an empty scan into a pass."""


def load_image(path: Path) -> psexe.PsxExe:
    if not path.is_file():
        raise Refused(f"{path} does not exist; scanned 0 loaded words")
    try:
        return psexe.load(str(path))
    except (OSError, ValueError, struct.error) as exc:
        raise Refused(f"{path} is not a loadable PS-X EXE; scanned 0 loaded words: {exc}") from exc


def words(image: psexe.PsxExe):
    for offset in range(0, image.text_size, 4):
        yield image.load + offset, struct.unpack_from("<I", image.text, offset)[0]


def jump_target(pc: int, instruction: int) -> int:
    return ((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)


def projection_writer(instruction: int) -> tuple[int, int] | None:
    # COP2 CTC2: opcode 0x12, rs 0x06, rt is the source GPR, rd is the control register.
    if instruction >> 26 != 0x12 or (instruction >> 21) & 31 != 0x06:
        return None
    control = (instruction >> 11) & 31
    if control not in (24, 25, 26):
        return None
    return (instruction >> 16) & 31, control


def scan(image: psexe.PsxExe) -> tuple[tuple[tuple[int, int, int], ...], dict[int, tuple[int, ...]]]:
    found_writers: list[tuple[int, int, int]] = []
    found_calls = {target: [] for target in EXPECTED_CALLS}
    for pc, instruction in words(image):
        writer = projection_writer(instruction)
        if writer is not None:
            found_writers.append((pc, *writer))
        if instruction >> 26 == 3:
            target = jump_target(pc, instruction)
            if target in found_calls:
                found_calls[target].append(pc)
    return tuple(found_writers), {target: tuple(pcs) for target, pcs in found_calls.items()}


def expect_word(image: psexe.PsxExe, pc: int, expected: int, label: str) -> None:
    actual = image.word(pc)
    if actual != expected:
        raise Refused(f"{label} at 0x{pc:08X}: word 0x{actual:08X}, want 0x{expected:08X}")


def verify(image: psexe.PsxExe) -> list[str]:
    found_writers, found_calls = scan(image)
    if found_writers != EXPECTED_WRITERS:
        raise Refused(
            f"scanned {image.text_size // 4} loaded words; CR24/25/26 writers were "
            f"{found_writers}, want {EXPECTED_WRITERS}"
        )
    if found_calls != EXPECTED_CALLS:
        raise Refused(
            f"scanned {image.text_size // 4} loaded words; projection call sites were "
            f"{found_calls}, want {EXPECTED_CALLS}"
        )

    # addiu a0,zero,160; jal SetGeomOffset; addiu a1,zero,120 (delay slot);
    # jal SetGeomScreen; addiu a0,zero,512 (delay slot).
    expect_word(image, 0x8001216C, 0x240400A0, "boot OFX")
    expect_word(image, 0x80012170, 0x0C03A432, "SetGeomOffset call")
    expect_word(image, 0x80012174, 0x24050078, "boot OFY")
    expect_word(image, 0x80012178, 0x0C03A43A, "SetGeomScreen call")
    expect_word(image, 0x8001217C, 0x24040200, "boot H")

    return [
        f"scanned all {image.text_size // 4} loaded words ({image.text_size} bytes)",
        "found exactly 6 CR24/25/26 writers, all inside InitGeom/SetGeomOffset/SetGeomScreen",
        "found one call to each projection routine, all in func_8001213C",
        "boot projection arguments are OFX=160, OFY=120, H=512",
    ]


def mutate(image: psexe.PsxExe, pc: int, instruction: int) -> psexe.PsxExe:
    offset = pc - image.load
    changed = bytearray(image.text)
    struct.pack_into("<I", changed, offset, instruction)
    return dataclasses.replace(image, text=bytes(changed))


def selftest(image: psexe.PsxExe) -> None:
    cases = [
        ("retail positive", image, True),
        ("changed boot OFX", mutate(image, 0x8001216C, 0x240400A1), False),
        ("removed SetGeomOffset call", mutate(image, 0x80012170, 0), False),
        ("extra raw CR24 writer", mutate(image, 0x80012168, 0x48C4C000), False),
    ]
    passed = 0
    for name, fixture, should_pass in cases:
        try:
            verify(fixture)
            actual = True
        except Refused:
            actual = False
        if actual != should_pass:
            raise Refused(f"selftest {name}: expected {'PASS' if should_pass else 'FAIL'}")
        passed += 1
        print(f"[projection:selftest] PASS {name} -> {'accepted' if actual else 'rejected'}")
    print(f"[projection:selftest] PASS {passed}/{len(cases)} cases")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--check", action="store_true", help="verify the complete retail projection census")
    parser.add_argument("--selftest", action="store_true", help="prove the verifier accepts and rejects")
    args = parser.parse_args()

    try:
        if hashlib.sha1(args.exe.read_bytes()).hexdigest() != EXPECTED_SHA1:
            raise Refused(f"{args.exe} is not retail SLUS_005.61 (whole-file SHA-1 mismatch)")
        image = load_image(args.exe)
        if args.check or not args.selftest:
            for line in verify(image):
                print(f"[projection] PASS {line}")
            print("[projection] BLIND SPOT: static completeness does not classify the rendered picture; "
                  "the boot scheduler must run before widescreen pixels can be verified")
        if args.selftest:
            selftest(image)
        return 0
    except (OSError, Refused) as exc:
        print(f"[projection] REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
