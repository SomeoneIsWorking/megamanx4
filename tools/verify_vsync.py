#!/usr/bin/env python3
"""Verify MMX4's VBlank wait/IRQ contract directly from the retail executable."""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
SYNC_HEADER = ROOT / "game/core/vsync_sync.h"
SYNC_SOURCE = ROOT / "game/core/vsync_sync.cpp"
CONFIG_SOURCE = ROOT / "game/core/game_config.cpp"

EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"
TEXT_VADDR = 0x80010000
TEXT_FILE_OFFSET = 0x800

VSYNC = 0x800E4DB0
WAIT = 0x800E4EF8
WAIT_END = 0x800E4F94
IRQ_INIT = 0x800E56A4
IRQ_HANDLER = 0x800E56FC
IRQ_TABLE = 0x8011DC30
VBLANK_COUNTER = 0x8011DC50


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Inputs:
    exe: bytes
    header: str
    source: str
    config: str


def word(image: bytes, address: int) -> int:
    offset = TEXT_FILE_OFFSET + address - TEXT_VADDR
    if offset < 0 or offset + 4 > len(image):
        raise VerificationError(f"0x{address:08X} lies outside the executable image")
    return struct.unpack_from("<I", image, offset)[0]


def jal_target(instruction: int, pc: int) -> int:
    if instruction >> 26 != 3:
        raise VerificationError(f"0x{pc:08X} is not jal (word 0x{instruction:08X})")
    return ((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)


def expect_jal(image: bytes, pc: int, target: int, label: str) -> None:
    actual = jal_target(word(image, pc), pc)
    if actual != target:
        raise VerificationError(
            f"{label}: jal at 0x{pc:08X} targets 0x{actual:08X}, want 0x{target:08X}"
        )


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def built_address(image: bytes, lui_pc: int, low_pc: int) -> int:
    upper = word(image, lui_pc)
    lower = word(image, low_pc)
    if upper >> 26 != 0x0F:
        raise VerificationError(f"0x{lui_pc:08X} is not lui")
    reg = (upper >> 16) & 0x1F
    opcode = lower >> 26
    base = (lower >> 21) & 0x1F
    if base != reg or opcode not in {0x09, 0x20, 0x21, 0x23, 0x28, 0x29, 0x2B}:
        raise VerificationError(f"0x{low_pc:08X} does not consume the lui register")
    return ((upper & 0xFFFF) << 16) + signed16(lower & 0xFFFF)


def expect_address(
    image: bytes, lui_pc: int, low_pc: int, expected: int, label: str
) -> None:
    actual = built_address(image, lui_pc, low_pc) & 0xFFFFFFFF
    if actual != expected:
        raise VerificationError(f"{label}: 0x{actual:08X}, want 0x{expected:08X}")


def expect_immediate(
    image: bytes, pc: int, opcode: int, rt: int, rs: int, imm: int, label: str
) -> None:
    instruction = word(image, pc)
    fields = (
        instruction >> 26,
        (instruction >> 16) & 0x1F,
        (instruction >> 21) & 0x1F,
        instruction & 0xFFFF,
    )
    expected = (opcode, rt, rs, imm & 0xFFFF)
    if fields != expected:
        raise VerificationError(
            f"{label}: word 0x{instruction:08X} has fields {fields}, want {expected}"
        )


def c_string(image: bytes, address: int) -> str:
    offset = TEXT_FILE_OFFSET + address - TEXT_VADDR
    end = image.find(b"\0", offset)
    if end < 0:
        raise VerificationError(f"unterminated string at 0x{address:08X}")
    return image[offset:end].decode("ascii")


def source_constant(text: str, name: str) -> int:
    match = re.search(rf"\b{name}\s*=\s*(0x[0-9A-Fa-f]+)u?\s*;", text)
    if not match:
        raise VerificationError(f"source constant {name} is missing")
    return int(match.group(1), 16)


def verify(inputs: Inputs, *, check_digest: bool = True) -> list[str]:
    digest = hashlib.sha1(inputs.exe).hexdigest()
    if check_digest and digest != EXPECTED_SHA1:
        raise VerificationError(
            f"executable SHA-1 {digest}, want retail {EXPECTED_SHA1}"
        )

    checks: list[str] = []

    # VSync retains its own guest-visible policy and calls only the narrow wait helper twice.
    expect_address(
        inputs.exe, 0x800E4DF0, 0x800E4DF4, VBLANK_COUNTER, "VSync(-1) counter query"
    )
    expect_jal(inputs.exe, 0x800E4E40, WAIT, "VSync first wait")
    expect_jal(inputs.exe, 0x800E4E64, WAIT, "VSync next-field wait")
    checks.append("VSync calls the same counter wait twice and keeps its query path")

    # The helper's entire reason to exist is the counter wait. Its timeout string provides an
    # independent retail classification; no matching-decomp symbol is consulted.
    expect_address(
        inputs.exe, 0x800E4F04, 0x800E4F08, VBLANK_COUNTER, "wait initial counter load"
    )
    expect_address(
        inputs.exe, 0x800E4F6C, 0x800E4F70, VBLANK_COUNTER, "wait loop counter load"
    )
    expect_address(
        inputs.exe, 0x800E4F40, 0x800E4F44, 0x80011900, "wait timeout string"
    )
    if c_string(inputs.exe, 0x80011900) != "VSync: timeout\n":
        raise VerificationError("retail wait diagnostic is not 'VSync: timeout\\n'")
    if word(inputs.exe, 0x800E4F8C) != 0x03E00008 or word(inputs.exe, 0x800E4F90) != 0:
        raise VerificationError(
            "wait helper does not end in jr ra / nop at measured boundary"
        )
    checks.append(
        "wait helper spins on the IRQ counter and occupies [0x800E4EF8,0x800E4F94)"
    )

    # IRQ init: zero the same counter, clear exactly 8 callbacks, register handler for IRQ 0.
    expect_address(inputs.exe, 0x800E56A8, 0x800E56AC, IRQ_TABLE, "IRQ callback table")
    expect_address(
        inputs.exe, 0x800E56C4, 0x800E56C8, VBLANK_COUNTER, "IRQ counter clear"
    )
    expect_jal(inputs.exe, 0x800E56CC, 0x800E57A0, "IRQ callback-table clear")
    expect_immediate(inputs.exe, 0x800E56D0, 0x09, 5, 0, 8, "callback count")
    expect_address(
        inputs.exe, 0x800E56D4, 0x800E56D8, IRQ_HANDLER, "IRQ handler address"
    )
    expect_jal(inputs.exe, 0x800E56DC, 0x800E4FC4, "IRQ registrar call")
    if word(inputs.exe, 0x800E56E0) != 0x00002021:
        raise VerificationError(
            "IRQ registrar delay slot does not set a0 = 0 (IRQ VBlank)"
        )
    checks.append("init registers 0x800E56FC for IRQ 0 after clearing 8 callback slots")

    # IRQ handler: one tick, then an exact eight-entry indirect callback walk.
    expect_address(
        inputs.exe, 0x800E56FC, 0x800E5700, VBLANK_COUNTER, "handler counter read"
    )
    expect_immediate(inputs.exe, 0x800E5720, 0x09, 2, 2, 1, "handler counter increment")
    expect_address(
        inputs.exe, 0x800E5724, 0x800E5728, VBLANK_COUNTER, "handler counter write"
    )
    expect_address(
        inputs.exe, 0x800E5714, 0x800E5718, IRQ_TABLE, "handler callback cursor"
    )
    if word(inputs.exe, 0x800E5744) & 0x3F != 9:
        raise VerificationError("handler callback site is not jalr")
    expect_immediate(inputs.exe, 0x800E5750, 0x0A, 2, 17, 8, "handler callback bound")
    checks.append("IRQ-0 handler increments once and walks exactly 8 callbacks")

    # Independently classify the observed runtime chain. The retail literal says CD_init, while
    # the actual call edges lead from the retry wrapper to CD initialization/command code and then
    # to VSync(-1) for a 960-field deadline.
    expect_jal(inputs.exe, 0x800E5ADC, 0x800E5C14, "observed retry -> reset edge")
    expect_jal(inputs.exe, 0x800E5C3C, 0x800E74DC, "observed reset -> CD init edge")
    expect_address(inputs.exe, 0x800E74E0, 0x800E74E4, 0x80011BF4, "CD init diagnostic")
    if c_string(inputs.exe, 0x80011BF4) != "CD_init:":
        raise VerificationError(
            "0x800E74DC does not reference the retail 'CD_init:' literal"
        )
    expect_jal(inputs.exe, 0x800E7638, 0x800E6E14, "CD init -> command edge")
    expect_jal(inputs.exe, 0x800E6FDC, VSYNC, "CD command -> VSync query edge")
    expect_immediate(inputs.exe, 0x800E6FE0, 0x09, 4, 0, -1, "VSync(-1) mode")
    checks.append(
        "retail bodies reproduce the observed CD-init -> command -> VSync chain"
    )

    # Shipping wiring must use the same constants and exact window, with no vsyncTrap.
    if (
        source_constant(inputs.header, "kWait") != WAIT
        or source_constant(inputs.header, "kWaitEnd") != WAIT_END
    ):
        raise VerificationError(
            "shipping wait/window constants disagree with retail boundaries"
        )
    for token in (
        "kVblankCounter = 0x8011DC50u",
        "kVblankHandler = 0x800E56FCu",
        "c->r[5] <<= 15",
        "c->r[3] = UINT32_MAX",
        "c->r[2] = 0",
        "c->game->fps60.frame_commit(c, 1)",
        "register_(kWait",
    ):
        if token not in inputs.source:
            raise VerificationError(
                f"shipping synchronization source is missing {token!r}"
            )
    config_shape = (
        ".windowLo = {x4::vsync::kWait, 0}, .windowHi = {x4::vsync::kWaitEnd, 0}"
    )
    if config_shape not in inputs.config:
        raise VerificationError(
            "GameConfig does not declare the exact wait-helper executable window"
        )
    if ".vsyncTrap" in inputs.config:
        raise VerificationError(
            "GameConfig sets vsyncTrap even though the guest owns VSync"
        )
    if "gpu_present(c)" in inputs.source or "gpu_pace_frame(c)" in inputs.source:
        raise VerificationError(
            "shipping wait helper bypasses or duplicates the authoritative frame_commit fence"
        )
    checks.append(
        "shipping handler and exact PlatformHle window match the measured contract"
    )
    return checks


def load_inputs(exe_path: Path) -> Inputs:
    if not exe_path.is_file():
        raise VerificationError(f"missing executable: {exe_path}")
    return Inputs(
        exe_path.read_bytes(),
        SYNC_HEADER.read_text(),
        SYNC_SOURCE.read_text(),
        CONFIG_SOURCE.read_text(),
    )


def mutate_word(image: bytes, address: int, replacement: int) -> bytes:
    changed = bytearray(image)
    offset = TEXT_FILE_OFFSET + address - TEXT_VADDR
    struct.pack_into("<I", changed, offset, replacement)
    return bytes(changed)


def expect_refusal(name: str, inputs: Inputs) -> str:
    try:
        verify(inputs, check_digest=False)
    except VerificationError as exc:
        return f"PASS negative {name}: {exc}"
    raise VerificationError(f"negative {name} was accepted")


def selftest(inputs: Inputs) -> list[str]:
    results = [f"PASS positive retail: {len(verify(inputs))} contract groups"]
    wrong_edge = Inputs(
        mutate_word(inputs.exe, 0x800E5ADC, 0),
        inputs.header,
        inputs.source,
        inputs.config,
    )
    results.append(expect_refusal("broken observed call edge", wrong_edge))
    wrong_bound = Inputs(
        mutate_word(inputs.exe, 0x800E5750, 0x2A220007),
        inputs.header,
        inputs.source,
        inputs.config,
    )
    results.append(expect_refusal("seven callback slots", wrong_bound))
    wrong_config = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source,
        inputs.config.replace("kWaitEnd, 0", "kWait, 0", 1),
    )
    results.append(expect_refusal("collapsed executable window", wrong_config))
    raw_present = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source.replace(
            "c->game->fps60.frame_commit(c, 1)", "gpu_present(c)", 1
        ),
        inputs.config,
    )
    results.append(expect_refusal("raw present without frame fence", raw_present))
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify retail evidence and shipping wiring",
    )
    parser.add_argument(
        "--selftest", action="store_true", help="prove the verifier accepts and refuses"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.check and not args.selftest:
        raise VerificationError("choose --check and/or --selftest")
    inputs = load_inputs(args.exe)
    if args.check:
        checks = verify(inputs)
        for check in checks:
            print(f"PASS: {check}")
        print(
            f"PASS — {len(checks)} retail VBlank contract groups; SHA-1 {EXPECTED_SHA1}"
        )
    if args.selftest:
        results = selftest(inputs)
        print("\n".join(results))
        print(f"PASS — selftest {len(results)}/{len(results)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
