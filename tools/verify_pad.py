#!/usr/bin/env python3
"""Verify Mega Man X4's two InitPAD buffers from the retail PS-X EXE.

The matching decomp is a locator only: its US symbol map identifies InitPAD at 0x800EE0D0 and its
boot initializer identifies the call worth inspecting. This tool independently scans every loaded
instruction in SLUS_005.61, requires exactly one call to that target, symbolically evaluates the four
argument registers at the call (including its delay slot), and compares them with the constants that
actually ship in game/core/game_config.cpp.

Blind spots: this proves the static call arguments and call count, not runtime mutation of either
buffer. It also relies on the matching decomp's identity for the InitPAD target; the executable-side
evidence is the target's own argument-preserving wrapper and the unique call shape, not SDK symbols in
the stripped retail image.
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import sys
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EXE = os.path.join(ROOT, "scratch", "bin", "megamanx4", "SLUS_005.61")
SHIPPED_FILE = os.path.join(ROOT, "game", "core", "game_config.cpp")
INIT_PAD = 0x800EE0D0
WANTED_CONSTANTS = ("kPadSlot0Buf", "kPadSlot1Buf", "kPadCapacity")


class Refused(Exception):
    """The input cannot support the claim; never turn an empty scan into a pass."""


@dataclass(frozen=True)
class Image:
    load: int
    words: tuple[int, ...]


@dataclass(frozen=True)
class Measurement:
    call_pc: int
    args: tuple[int | None, int | None, int | None, int | None]
    evidence: tuple[tuple[int, int], ...]
    words_scanned: int
    call_count: int


@dataclass(frozen=True)
class Shipping:
    constants: dict[str, int]
    config_failures: tuple[str, ...]


def load_image(path: str) -> Image:
    try:
        with open(path, "rb") as stream:
            data = stream.read()
    except OSError as exc:
        raise Refused(f"cannot read {path}: {exc}") from exc
    if len(data) < 0x800 or data[:8] != b"PS-X EXE":
        raise Refused(f"{path} is not a PS-X EXE ({len(data)} bytes; scanned nothing)")
    load, size = struct.unpack_from("<II", data, 0x18)
    if size == 0 or size % 4 or len(data) < 0x800 + size:
        raise Refused(
            f"invalid loaded image: load=0x{load:08X}, size={size}, file={len(data)} bytes"
        )
    return Image(load, struct.unpack_from(f"<{size // 4}I", data, 0x800))


def jump_target(pc: int, word: int) -> int:
    return ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def written_reg(word: int) -> int | None:
    op = word >> 26
    if op in (0x08, 0x09, 0x0C, 0x0D, 0x0E, 0x0F, 0x20, 0x21, 0x23, 0x24, 0x25):
        return (word >> 16) & 31
    if op == 0:
        funct = word & 63
        if funct in (
            0x00,
            0x02,
            0x03,
            0x20,
            0x21,
            0x22,
            0x23,
            0x24,
            0x25,
            0x26,
            0x27,
            0x2A,
            0x2B,
        ):
            return (word >> 11) & 31
    return None


def apply_constant(word: int, regs: list[int | None]) -> None:
    op = word >> 26
    rs, rt = (word >> 21) & 31, (word >> 16) & 31
    imm = word & 0xFFFF
    out: int | None = None
    dest = written_reg(word)
    if op == 0x0F:
        out = imm << 16
    elif op in (0x08, 0x09) and regs[rs] is not None:
        out = (regs[rs] + signed16(imm)) & 0xFFFFFFFF
    elif op == 0x0D and regs[rs] is not None:
        out = regs[rs] | imm
    elif (
        op == 0
        and (word & 63) in (0x20, 0x21)
        and regs[rs] is not None
        and regs[rt] is not None
    ):
        out = (regs[rs] + regs[rt]) & 0xFFFFFFFF
    elif (
        op == 0
        and (word & 63) == 0x25
        and regs[rs] is not None
        and regs[rt] is not None
    ):
        out = regs[rs] | regs[rt]
    if dest not in (None, 0):
        regs[dest] = out
    regs[0] = 0


def measure(image: Image) -> Measurement:
    calls = []
    for index, word in enumerate(image.words):
        pc = image.load + index * 4
        if word >> 26 == 3 and jump_target(pc, word) == INIT_PAD:
            calls.append(index)
    if len(calls) != 1:
        raise Refused(
            f"scanned {len(image.words)} loaded words and found {len(calls)} calls to "
            f"InitPAD target 0x{INIT_PAD:08X}; exactly one is required"
        )

    call_index = calls[0]
    previous_call = call_index - 1
    while previous_call >= 0 and image.words[previous_call] >> 26 not in (2, 3):
        previous_call -= 1
    start = previous_call + 2 if previous_call >= 0 else max(0, call_index - 16)
    regs: list[int | None] = [None] * 32
    regs[0] = 0
    evidence = []
    for index in range(start, call_index + 2):
        word = image.words[index]
        pc = image.load + index * 4
        before = tuple(regs[4:8])
        if index != call_index:
            apply_constant(word, regs)
        if tuple(regs[4:8]) != before:
            evidence.append((pc, word))
    return Measurement(
        image.load + call_index * 4,
        tuple(regs[4:8]),
        tuple(evidence),
        len(image.words),
        len(calls),
    )


CONST_RE = re.compile(
    r"^\s*static\s+constexpr\s+uint32_t\s+(kPad\w+)\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)u?\s*;",
    re.MULTILINE,
)


def shipping_state(path: str = SHIPPED_FILE) -> Shipping:
    try:
        with open(path, encoding="utf-8") as stream:
            text = stream.read()
    except OSError as exc:
        raise Refused(f"cannot read shipping file {path}: {exc}") from exc
    values = {name: int(value, 0) for name, value in CONST_RE.findall(text)}
    missing = [name for name in WANTED_CONSTANTS if name not in values]
    if missing:
        raise Refused(
            f"shipping file does not define {', '.join(missing)} in a parseable form"
        )
    source = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.DOTALL)
    config_at = source.find("static const GameConfig g_x4_cfg")
    if config_at < 0:
        raise Refused("shipping file has no parseable g_x4_cfg initializer")
    config = source[config_at:]
    bindings = {
        "padSlot0Buf": "kPadSlot0Buf",
        "padSlot1Buf": "kPadSlot1Buf",
        "padDriverFn": "0",
        "padSlotPtrTable": "0",
        "padSlotPtrStride": "0",
    }
    failures = []
    for field, expected in bindings.items():
        match = re.search(rf"\.{field}\s*=\s*([^,\n]+)", config)
        actual = match.group(1).strip() if match else "<absent>"
        if actual != expected:
            failures.append(f"GameConfig .{field} ships {actual}, expected {expected}")
    return Shipping(values, tuple(failures))


def compare(measured: Measurement, shipped: dict[str, int]) -> list[str]:
    expected = (
        shipped["kPadSlot0Buf"],
        shipped["kPadCapacity"],
        shipped["kPadSlot1Buf"],
        shipped["kPadCapacity"],
    )
    names = ("slot0 buffer", "slot0 capacity", "slot1 buffer", "slot1 capacity")
    return [
        f"{name}: measured {actual!r}, shipping 0x{want:08X}"
        for name, actual, want in zip(names, measured.args, expected)
        if actual != want
    ]


def print_measurement(measured: Measurement) -> None:
    args = ["?" if value is None else f"0x{value:08X}" for value in measured.args]
    print(
        f"scanned {measured.words_scanned} loaded words; found {measured.call_count} InitPAD call "
        f"at 0x{measured.call_pc:08X}"
    )
    for pc, word in measured.evidence:
        print(f"  0x{pc:08X}: 0x{word:08X}")
    print(f"  arguments a0..a3 = {', '.join(args)}")


def check(image: Image, shipping: Shipping, verbose: bool = True) -> list[str]:
    measured = measure(image)
    failures = [*shipping.config_failures, *compare(measured, shipping.constants)]
    if verbose:
        print_measurement(measured)
        if failures:
            for failure in failures:
                print(f"MISMATCH: {failure}")
        else:
            print("MATCH: 4/4 InitPAD arguments agree with the shipping constants")
        print(
            "blind spot: static call arguments only; runtime buffer mutation is not observed, and "
            "the stripped target's InitPAD identity comes from the matching decomp symbol map"
        )
    return failures


def selftest(image: Image, shipping: Shipping) -> bool:
    cases: list[tuple[str, bool]] = []
    cases.append(
        (
            "positive: retail image matches shipping config",
            not check(image, shipping, False),
        )
    )

    measured = measure(image)
    writer_pc = next(pc for pc, _ in measured.evidence if pc == measured.call_pc - 0x10)
    words = list(image.words)
    writer_index = (writer_pc - image.load) // 4
    words[writer_index] ^= 1
    mutated = Image(image.load, tuple(words))
    cases.append(
        (
            "negative: changed slot-0 immediate is rejected",
            bool(check(mutated, shipping, False)),
        )
    )

    broken = Shipping(shipping.constants, ("GameConfig .padSlot0Buf ships 0",))
    cases.append(
        ("negative: unwired GameConfig is rejected", bool(check(image, broken, False)))
    )

    words = list(image.words)
    call_index = (measured.call_pc - image.load) // 4
    words[call_index] ^= 1
    try:
        measure(Image(image.load, tuple(words)))
        cases.append(("negative: removed InitPAD call is refused", False))
    except Refused:
        cases.append(("negative: removed InitPAD call is refused", True))

    for name, passed in cases:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"selftest: {sum(passed for _, passed in cases)}/{len(cases)} cases")
    return all(passed for _, passed in cases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", default=DEFAULT_EXE, help="retail PS-X EXE to inspect")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check",
        action="store_true",
        help="compare retail call arguments to shipping constants",
    )
    group.add_argument(
        "--selftest",
        action="store_true",
        help="prove the checker shows match and mismatch",
    )
    args = parser.parse_args()
    try:
        image = load_image(args.exe)
        shipping = shipping_state()
        if args.selftest:
            return 0 if selftest(image, shipping) else 1
        return 1 if check(image, shipping) else 0
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
