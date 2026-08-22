#!/usr/bin/env python3
"""Derive X4's retail task/Bios-thread handoff and diff the shipping owner against it."""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from config_windows import platform_hle_windows


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"

SCHEDULER = 0x80012600
CREATE_TASK = 0x80012740
YIELD_TASKS = (0x800127C8, 0x800127FC, 0x800128B8)
OPEN_THREAD = 0x800EDD9C
CLOSE_THREAD = 0x800EDDAC
CHANGE_THREAD = 0x800EDDBC


class VerifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PsExe:
    data: bytes
    text_addr: int
    text_size: int

    @classmethod
    def load(cls, path: Path) -> "PsExe":
        data = path.read_bytes()
        if data[:8] != b"PS-X EXE":
            raise VerifyError(f"{path}: not a PS-X EXE")
        text_addr, text_size = struct.unpack_from("<II", data, 0x18)
        return cls(data, text_addr, text_size)

    def word(self, address: int) -> int:
        offset = 0x800 + address - self.text_addr
        if offset < 0 or offset + 4 > len(self.data):
            raise VerifyError(f"0x{address:08X}: outside loaded executable")
        return struct.unpack_from("<I", self.data, offset)[0]

    def words(self, address: int, count: int) -> list[int]:
        return [self.word(address + index * 4) for index in range(count)]


def op(word: int) -> int:
    return word >> 26


def rs(word: int) -> int:
    return (word >> 21) & 31


def rt(word: int) -> int:
    return (word >> 16) & 31


def rd(word: int) -> int:
    return (word >> 11) & 31


def imm(word: int) -> int:
    value = word & 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def jal_target(pc: int, word: int) -> int:
    return ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def expect(condition: bool, description: str) -> None:
    if not condition:
        raise VerifyError(description)


def verify_thunk(exe: PsExe, address: int, service: int) -> None:
    words = exe.words(address, 4)
    expect(words[0] == 0x240A00B0, f"0x{address:08X}: not an addiu t2,zero,0xB0 BIOS thunk")
    expect(words[1] == 0x01400008, f"0x{address + 4:08X}: not jr t2")
    expect(
        words[2] == 0x24090000 | service,
        f"0x{address + 8:08X}: BIOS service is not B0:{service:02X}",
    )
    expect(words[3] == 0, f"0x{address + 12:08X}: BIOS thunk padding is not nop")


def verify_create_task(exe: PsExe) -> None:
    words = exe.words(CREATE_TASK, 34)
    expect(0x001081C0 in words, "func_80012740 does not scale its task index by 128 bytes")
    expect(0x3C11801F in words and 0x36318100 in words, "func_80012740 does not form task base 0x801F8100")
    expect(0x8C258110 in words, "func_80012740 does not load task SP from record +0x10")
    expect(0x8C268144 in words, "func_80012740 does not load task GP from record +0x44")
    call_index = next(
        (
            index
            for index, word in enumerate(words)
            if op(word) == 3 and jal_target(CREATE_TASK + index * 4, word) == OPEN_THREAD
        ),
        -1,
    )
    expect(call_index >= 0, "func_80012740 does not call the measured OpenTh thunk")
    expect(words[call_index + 1] == 0x02402021, "OpenTh delay slot does not pass the requested entry in a0")
    expect(0xAC228108 in words, "func_80012740 does not store the returned handle at task record +8")
    expect(0x24020002 in words and 0xA6220000 in words, "func_80012740 does not arm the task with state 2")


def verify_scheduler(exe: PsExe) -> None:
    words = exe.words(SCHEDULER, 80)
    expect(0x3C02801F in words and 0x34428100 in words, "func_80012600 does not form task base 0x801F8100")
    expect(0x3C10801F in words and 0x36108300 in words, "func_80012600 does not form current-task pointer 0x801F8300")
    expect(0x8C440008 in words, "func_80012600 does not load a task handle from record +8")
    expect(0x24420080 in words, "func_80012600 does not advance by the measured 128-byte task stride")
    expect(0x346382FF in words, "func_80012600 does not stop after task record 2")
    call_index = next(
        (
            index
            for index, word in enumerate(words)
            if op(word) == 3 and jal_target(SCHEDULER + index * 4, word) == CHANGE_THREAD
        ),
        -1,
    )
    expect(call_index >= 0, "func_80012600 does not call the measured ChangeTh thunk")
    expect(words[call_index + 1] == 0xA4510000, "ChangeTh delay slot does not mark the selected task state 0x7F")


def verify_task_yields(exe: PsExe) -> None:
    for address in YIELD_TASKS:
        words = exe.words(address, 24)
        has_call = any(
            op(word) == 3 and jal_target(address + index * 4, word) == CHANGE_THREAD
            for index, word in enumerate(words)
        )
        expect(has_call, f"0x{address:08X}: task helper does not call ChangeTh")
        expect(0x3C04FF00 in words, f"0x{address:08X}: task helper does not switch to main handle 0xFF000000")


def parse_header_constants(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for name in ("kOpenThread", "kCloseThread", "kChangeThread", "kThreadWindowEnd", "kMainThreadHandle"):
        match = re.search(rf"{name}\s*=\s*(0x[0-9A-Fa-f]+)u?", text)
        if not match:
            raise VerifyError(f"bios_threads.h does not declare {name} as a hexadecimal constant")
        values[name] = int(match.group(1), 16)
    return values


def verify_shipping_constants(header_text: str, config_text: str) -> None:
    values = parse_header_constants(header_text)
    expected = {
        "kOpenThread": OPEN_THREAD,
        "kCloseThread": CLOSE_THREAD,
        "kChangeThread": CHANGE_THREAD,
        "kThreadWindowEnd": CHANGE_THREAD + 0x10,
        "kMainThreadHandle": 0xFF000000,
    }
    for name, value in expected.items():
        expect(values[name] == value, f"shipping {name}=0x{values[name]:08X}, retail evidence requires 0x{value:08X}")
    try:
        window_lo, window_hi = platform_hle_windows(config_text)
    except ValueError as exc:
        raise VerifyError(str(exc)) from exc
    expect(
        window_lo[1] == "x4::bios_threads::kOpenThread"
        and window_hi[1] == "x4::bios_threads::kThreadWindowEnd",
        "GameConfig does not declare the exact BIOS-thread thunk window",
    )


def verify(exe: PsExe, header_text: str, config_text: str) -> None:
    verify_thunk(exe, OPEN_THREAD, 0x0E)
    verify_thunk(exe, CLOSE_THREAD, 0x0F)
    verify_thunk(exe, CHANGE_THREAD, 0x10)
    verify_create_task(exe)
    verify_scheduler(exe)
    verify_task_yields(exe)
    verify_shipping_constants(header_text, config_text)


def mutated(exe: PsExe, address: int, word: int) -> PsExe:
    data = bytearray(exe.data)
    offset = 0x800 + address - exe.text_addr
    struct.pack_into("<I", data, offset, word)
    return PsExe(bytes(data), exe.text_addr, exe.text_size)


def expect_failure(label: str, action) -> None:
    try:
        action()
    except VerifyError:
        print(f"  PASS negative: {label}")
        return
    raise VerifyError(f"negative control unexpectedly passed: {label}")


def selftest(exe: PsExe, header_text: str, config_text: str) -> None:
    verify(exe, header_text, config_text)
    print("  PASS positive: exact retail binary + shipping constants/window")
    expect_failure(
        "wrong CloseTh BIOS service",
        lambda: verify(mutated(exe, CLOSE_THREAD + 8, 0x24090010), header_text, config_text),
    )
    expect_failure(
        "wrong task stride",
        lambda: verify(mutated(exe, CREATE_TASK + 0x28, 0x00108180), header_text, config_text),
    )
    expect_failure(
        "wrong main-thread handle",
        lambda: verify(mutated(exe, 0x800127C8 + 0x18, 0x3C04FE00), header_text, config_text),
    )
    expect_failure(
        "shipping ChangeTh constant drift",
        lambda: verify(exe, header_text.replace("0x800EDDBCu", "0x800EDDCCu"), config_text),
    )
    expect_failure(
        "collapsed BIOS-thread thunk window",
        lambda: verify(
            exe,
            header_text,
            config_text.replace(
                "x4::bios_threads::kThreadWindowEnd",
                "x4::bios_threads::kOpenThread",
                1,
            ),
        ),
    )
    print("thread evidence selftest: 6/6")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if not args.check and not args.selftest:
        parser.error("select --check and/or --selftest")

    try:
        exe = PsExe.load(args.exe)
        digest = hashlib.sha1(exe.data).hexdigest()
        if digest != EXPECTED_SHA1:
            raise VerifyError(f"{args.exe}: SHA-1 {digest}, expected retail SLUS_005.61 {EXPECTED_SHA1}")
        header_text = (ROOT / "game/core/bios_threads.h").read_text()
        config_text = (ROOT / "game/core/game_config.cpp").read_text()
        if args.check:
            verify(exe, header_text, config_text)
            print(
                "thread evidence: 3/3 BIOS thunks, 7/7 create/scheduler facts, "
                "3/3 task->main yield helpers, 5/5 shipping constants, exact HLE window"
            )
        if args.selftest:
            selftest(exe, header_text, config_text)
        print(
            "BLIND SPOT: static evidence proves the retail ownership/ABI graph, not host context-switch "
            "execution; mmx4_runtime_test and the bounded real-disc reach trace are separate runtime controls."
        )
        return 0
    except (OSError, VerifyError) as exc:
        print(f"thread evidence: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
