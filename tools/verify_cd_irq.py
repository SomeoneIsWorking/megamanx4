#!/usr/bin/env python3
"""Verify MMX4's retail CD IRQ delivery and callback/result-state contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
SEEDS = ROOT / "game/recomp_seeds.json"

EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"
TEXT_VADDR = 0x80010000
TEXT_FILE_OFFSET = 0x800

IRQ_ELEMENT = 0x8013BBF8
PAD_HANDLER = 0x800EE274
PAD_VERIFIER = 0x800EE2DC
SETJMP = 0x800EDC8C
HOOK_ENTRY_INT = 0x800EDDEC
ENTRY_BUFFER = 0x8011CBCC
INTERRUPT_REENTRY = 0x800E5194
TRAP_INTR = 0x800E5208
INTERRUPT_CALLBACK = 0x800E4FC4
INTERRUPT_TABLE = 0x8011CB98
CD_CALLBACK = 0x800E7944


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Inputs:
    exe: bytes
    seeds: str


def word(image: bytes, address: int) -> int:
    offset = TEXT_FILE_OFFSET + address - TEXT_VADDR
    if offset < 0 or offset + 4 > len(image):
        raise VerificationError(f"0x{address:08X} lies outside the executable image")
    return struct.unpack_from("<I", image, offset)[0]


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


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
    return (((upper & 0xFFFF) << 16) + signed16(lower & 0xFFFF)) & 0xFFFFFFFF


def expect_address(
    image: bytes, lui_pc: int, low_pc: int, expected: int, label: str
) -> None:
    actual = built_address(image, lui_pc, low_pc)
    if actual != expected:
        raise VerificationError(f"{label}: 0x{actual:08X}, want 0x{expected:08X}")


def expect_word(image: bytes, pc: int, expected: int, label: str) -> None:
    actual = word(image, pc)
    if actual != expected:
        raise VerificationError(
            f"{label}: word at 0x{pc:08X} is 0x{actual:08X}, want 0x{expected:08X}"
        )


def parse_seeds(text: str) -> dict[str, object]:
    without_comments = re.sub(r"//[^\n]*", "", text)
    try:
        parsed = json.loads(without_comments)
    except json.JSONDecodeError as exc:
        raise VerificationError(f"cannot parse recomp seeds: {exc}") from exc
    if not isinstance(parsed, dict):
        raise VerificationError("recomp seeds are not a JSON object")
    return parsed


def expect_reentry_seed(text: str) -> None:
    parsed = parse_seeds(text)
    wanted = f"0x{INTERRUPT_REENTRY:08X}"
    reentries = parsed.get("main_reentry")
    if not isinstance(reentries, list) or reentries.count(wanted) != 1:
        raise VerificationError(
            f"recomp seeds 'main_reentry' must contain {wanted} exactly once"
        )
    main = parsed.get("main")
    if not isinstance(main, list) or wanted in main:
        raise VerificationError(
            f"recomp seeds 'main' must not duplicate re-entry {wanted}"
        )


def verify(inputs: Inputs, *, check_digest: bool = True) -> list[str]:
    digest = hashlib.sha1(inputs.exe).hexdigest()
    if check_digest and digest != EXPECTED_SHA1:
        raise VerificationError(
            f"executable SHA-1 {digest}, want retail {EXPECTED_SHA1}"
        )

    checks: list[str] = []

    # InitPAD constructs one priority-1 BIOS chain element. Its two function fields independently
    # identify the element as pad/VBlank rather than CD service.
    expect_address(inputs.exe, 0x800EE1D0, 0x800EE1D4, IRQ_ELEMENT + 4, "element field base")
    expect_word(inputs.exe, 0x800EE1D8, 0x2470FFFC, "element base from field base")
    expect_address(inputs.exe, 0x800EE1DC, 0x800EE1E0, PAD_HANDLER, "element handler")
    expect_word(inputs.exe, 0x800EE1E4, 0xAC620000, "element handler store")
    expect_address(inputs.exe, 0x800EE1E8, 0x800EE1EC, PAD_VERIFIER, "element verifier")
    expect_word(inputs.exe, 0x800EE1F4, 0xAC22BC00, "element verifier store")
    expect_word(inputs.exe, 0x800EE1FC, 0xAC20BBF8, "element next clear")
    expect_word(inputs.exe, 0x800EE204, 0xAC20BC04, "element tail clear")
    expect_jal(inputs.exe, 0x800EE208, 0x800EE36C, "SysEnqIntRP wrapper")
    expect_word(inputs.exe, 0x800EE20C, 0x02002821, "SysEnqIntRP element argument")
    checks.append("InitPAD enqueues the measured pad/VBlank element at priority 1")

    # The verifier requires IRQ mask bit 0 and status bit 0. Non-zero is therefore the positive
    # claim result, while an asserted CD IRQ2 must return zero and continue to the custom exit.
    expect_address(inputs.exe, 0x800EE2DC, 0x800EE2E0, 0x8012F414, "IRQ register pointer")
    expect_word(inputs.exe, 0x800EE2E8, 0x8C620004, "I_MASK load")
    expect_word(inputs.exe, 0x800EE2F0, 0x30420001, "I_MASK VBlank bit")
    expect_word(inputs.exe, 0x800EE2FC, 0x8C620000, "I_STAT load")
    expect_word(inputs.exe, 0x800EE304, 0x30420001, "I_STAT VBlank bit")
    expect_word(inputs.exe, 0x800EE30C, 0x24020001, "positive verifier result")
    checks.append("the registered verifier claims only IRQ0 and correctly declines IRQ2")

    # setjmp records a mid-function continuation. HookEntryInt installs that buffer, and a non-zero
    # exception return reaches trapIntr. This is the static-recompiler entry the shipping seeds owe.
    expect_jal(inputs.exe, 0x800E518C, SETJMP, "startIntr setjmp")
    expect_word(inputs.exe, 0x800E5190, 0x26040038, "setjmp buffer argument")
    expect_word(inputs.exe, INTERRUPT_REENTRY, 0x10400003, "non-zero exception return branch")
    expect_jal(inputs.exe, 0x800E519C, TRAP_INTR, "exception continuation -> trapIntr")
    expect_address(inputs.exe, 0x800E51A4, 0x800E51A8, ENTRY_BUFFER + 4, "entry buffer cursor")
    expect_word(inputs.exe, 0x800E51AC, 0x2604FFFC, "HookEntryInt buffer argument")
    expect_jal(inputs.exe, 0x800E51B4, HOOK_ENTRY_INT, "HookEntryInt call")
    expect_reentry_seed(inputs.seeds)
    checks.append("HookEntryInt resumes the measured 0x800E5194 continuation into trapIntr")

    # trapIntr starts at callback table - 4, scans the eleven hardware interrupt bits, acknowledges
    # each asserted bit, then calls table[index]. IRQ2 therefore maps to the third word.
    expect_address(inputs.exe, 0x800E5210, 0x800E5214, INTERRUPT_TABLE - 4, "IRQ table anchor")
    expect_word(inputs.exe, 0x800E52A4, 0x26340004, "IRQ callback table start")
    expect_word(inputs.exe, 0x800E52B4, 0x2A22000B, "eleven IRQ sources")
    expect_word(inputs.exe, 0x800E52D4, 0xA4620000, "I_STAT acknowledgement")
    expect_word(inputs.exe, 0x800E52D8, 0x8E420000, "indexed IRQ callback load")
    expect_word(inputs.exe, 0x800E52E8, 0x0040F809, "indexed IRQ callback call")
    if INTERRUPT_TABLE + 2 * 4 != 0x8011CBA0:
        raise VerificationError("internal IRQ2 callback-slot arithmetic is inconsistent")
    checks.append("trapIntr acknowledges IRQ2 and dispatches callback slot 0x8011CBA0")

    # CD_init registers its actual IRQ2 callback through the generic InterruptCallback API.
    expect_address(inputs.exe, 0x800E7544, 0x800E7548, CD_CALLBACK, "CD IRQ callback")
    expect_jal(inputs.exe, 0x800E754C, INTERRUPT_CALLBACK, "CD InterruptCallback call")
    expect_word(inputs.exe, 0x800E7550, 0x24040002, "CD IRQ index")
    checks.append("CD_init registers 0x800E7944 in generic interrupt slot 2")

    # The registered callback drains controller result flags and routes the guest result buffers to
    # the ready/sync callbacks. On completion it stores the low two status bits back to libcd state.
    expect_address(inputs.exe, 0x800E7944, 0x800E7948, 0x8011DFE0, "CD status pointer")
    expect_address(inputs.exe, 0x800E7954, 0x800E7958, 0x8011DFF9, "CD result cursor")
    expect_address(inputs.exe, 0x800E7994, 0x800E7998, 0x8011DD20, "ready callback pointer")
    expect_address(inputs.exe, 0x800E79AC, 0x800E79B0, 0x8013BA80, "ready result buffer")
    expect_address(inputs.exe, 0x800E79C8, 0x800E79CC, 0x8011DD1C, "sync callback pointer")
    expect_address(inputs.exe, 0x800E79E0, 0x800E79E4, 0x8013BA78, "sync result buffer")
    expect_word(inputs.exe, 0x800E7A04, 0xA0520000, "libcd status update")
    checks.append("CD IRQ callback drains ready/sync results and updates libcd status")
    return checks


def load_inputs(exe_path: Path) -> Inputs:
    if not exe_path.is_file():
        raise VerificationError(f"missing executable: {exe_path}")
    return Inputs(exe_path.read_bytes(), SEEDS.read_text())


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
    results.append(
        expect_refusal(
            "IRQ2 verifier claim",
            Inputs(mutate_word(inputs.exe, 0x800EE2F0, 0x30420004), inputs.seeds),
        )
    )
    results.append(
        expect_refusal(
            "missing trapIntr edge",
            Inputs(mutate_word(inputs.exe, 0x800E519C, 0), inputs.seeds),
        )
    )
    wrong_seed = inputs.seeds.replace(
        '"main_reentry": ["0x800E5194"]', '"main_reentry": []', 1
    )
    results.append(expect_refusal("missing re-entry seed", Inputs(inputs.exe, wrong_seed)))
    duplicate_seed = inputs.seeds.replace(
        '"main": []', '"main": ["0x800E5194"]', 1
    )
    results.append(
        expect_refusal("duplicated re-entry ownership", Inputs(inputs.exe, duplicate_seed))
    )
    results.append(
        expect_refusal(
            "wrong CD callback slot",
            Inputs(mutate_word(inputs.exe, 0x800E7550, 0x24040003), inputs.seeds),
        )
    )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--check", action="store_true", help="verify retail and shipping wiring")
    parser.add_argument("--selftest", action="store_true", help="prove acceptance and refusal")
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
        print(f"PASS — {len(checks)} retail CD IRQ contract groups; SHA-1 {EXPECTED_SHA1}")
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
