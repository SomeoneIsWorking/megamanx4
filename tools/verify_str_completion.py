#!/usr/bin/env python3
"""Verify SLUS_005.61's STR/MDEC streaming completion path in the authenticated executable.

The matching AGPL decomp (`external/mmx4`) leaves the whole STR path as addresses only
(`config/symbols.us.txt` names StGetNext 0x800E83F4, StFreeRing 0x800E8300, StSetStream
0x800E8278, CdRead2 0x800E801C, data_ready_callback 0x800E8188) and has no source for
0x80018000, 0x800182E8, 0x80018788, 0x80018AD0, 0x80018B88, 0x80018E50 or 0x80018EEC. Every
structure below is therefore read from the bytes of the image this port actually runs, and each
one is a fact a native owner or a CD binding depends on:

  * StGetNext has exactly two call sites, and they are the two DIFFERENT waits. The first
    (0x800189A0) is the STR startup's first-frame wait. The second (0x80018BAC) is the movie
    driver's per-field pull, whose failure arm waits on libetc VSync(0) at 0x80018BBC and retries
    at most 601 times. Which of the two a stall is parked in decides whether the guest is
    STARTING a stream or WAITING for the next frame of a running one.

  * The per-field pull's VSync(0) returns to 0x80018BC4, and 0x80018BC4 is the only instruction
    after it. A host that resumes the task anywhere else cannot advance the retry counter, so the
    601-retry wait becomes an unbounded no-op with no guest-visible write at all.

  * 0x80018EEC is the movie loop's ONLY continue condition apart from the per-movie skip mask: it
    spins while 0x80139634 (MDEC output outstanding) is nonzero, then returns 0x801395E8 and
    refreshes 0x801395E4 from it.

  * The completion owner is 0x80018E50, reached from exactly two call sites, and its order is
    fixed: CdControlB(CdlPause) retry, CdSync, CdReady, DecDCTOut, StUnSetRing, CdReset(0),
    CdControl(CdlSetmode) retry. That is the only path on which the drive stops reading the STR,
    so a stall before it is a stall on a LIVE stream and not a finished one.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"
TEXT_VADDR = 0x80010000
TEXT_FILE_OFFSET = 0x800

# libstr / libcd entries. Named by external/mmx4/config/symbols.us.txt and confirmed in these bytes.
ST_GET_NEXT = 0x800E83F4
ST_FREE_RING = 0x800E8300
ST_SET_STREAM = 0x800E8278
ST_UNSET_RING = 0x800E8130
ST_CD_INTERRUPT = 0x800E80B0
DATA_READY_CALLBACK = 0x800E8188
CD_READ2 = 0x800E801C
VSYNC = 0x800E4DB0
CD_CONTROL_B = 0x800E5FF4
CD_CONTROL = 0x800E5D90
CD_SYNC = 0x800E6178
CD_READY = 0x800E5D78
DEC_DCT_OUT = 0x800ED084
RESET_MOVIE_STATE = 0x800192F8

# Title STR/MDEC functions, all recovered from the authenticated bytes
STR_STARTUP = 0x80018788
STR_DRIVER_INDEXED = 0x80018000
STR_DRIVER_ENTRY_ONE = 0x800182E8
STR_START_AND_FIRST_FRAME = 0x80018AD0
STR_PULL_NEXT_FRAME = 0x80018B88
STR_CONTINUE_CONDITION = 0x80018EEC
STR_COMPLETION = 0x80018E50

# libstr ring cursors, the MDEC-output-outstanding flag, and the two words the startup publishes
RING_FRAME_CURSOR = 0x80173C8C
RING_WRITE_CURSOR = 0x80173C90
RING_READ_CURSOR = 0x80173C94
MDEC_OUTPUT_OUTSTANDING = 0x80139634
LOOP_KEEP = 0x801395E8
LOOP_KEEP_MIRROR = 0x801395E4
MOVIE_PARITY = 0x80139594
STREAM_FLAVOUR = 0x800F1D88
FRAME_NUMBER_MIRROR = 0x801441C0

CDL_PAUSE = 9
CDL_SETMODE = 14
WAIT_LIMIT = 601


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Inputs:
    exe: bytes


def word(image: bytes, address: int) -> int:
    offset = TEXT_FILE_OFFSET + address - TEXT_VADDR
    if offset < 0 or offset + 4 > len(image):
        raise VerificationError(f"0x{address:08X} lies outside the executable image")
    return struct.unpack_from("<I", image, offset)[0]


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def jal_target(instruction: int, pc: int) -> int:
    if instruction >> 26 != 0x03:
        raise VerificationError(f"0x{pc:08X} is not jal (word 0x{instruction:08X})")
    return ((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)


def branch_target(instruction: int, pc: int) -> int:
    if instruction >> 26 not in {0x04, 0x05}:
        raise VerificationError(f"0x{pc:08X} is not a branch (word 0x{instruction:08X})")
    return (pc + 4) + (signed16(instruction & 0xFFFF) << 2)


def all_jal_sites(image: bytes, target: int) -> list[int]:
    """Every instruction-aligned `jal` in the resident image whose destination is `target`."""
    sites: list[int] = []
    resident = len(image) - TEXT_FILE_OFFSET
    for index in range(resident // 4):
        instruction = struct.unpack_from("<I", image, TEXT_FILE_OFFSET + index * 4)[0]
        if instruction & 0xFC000000 != 0x0C000000:
            continue
        pc = TEXT_VADDR + index * 4
        if (((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)) == target:
            sites.append(pc)
    return sites


def expect_jal(image: bytes, pc: int, target: int, label: str) -> None:
    actual = jal_target(word(image, pc), pc)
    if actual != target:
        raise VerificationError(
            f"{label}: jal at 0x{pc:08X} targets 0x{actual:08X}, want 0x{target:08X}"
        )


def expect_word(image: bytes, pc: int, expected: int, label: str) -> None:
    actual = word(image, pc)
    if actual != expected:
        raise VerificationError(
            f"{label}: word at 0x{pc:08X} is 0x{actual:08X}, want 0x{expected:08X}"
        )


def expect_branch(image: bytes, pc: int, target: int, label: str) -> None:
    actual = branch_target(word(image, pc), pc)
    if actual != target:
        raise VerificationError(
            f"{label}: branch at 0x{pc:08X} goes to 0x{actual:08X}, want 0x{target:08X}"
        )


def expect_sites(image: bytes, target: int, expected: list[int], label: str) -> None:
    actual = all_jal_sites(image, target)
    if actual != expected:
        raise VerificationError(
            f"{label}: {len(actual)} call site(s) of 0x{target:08X} "
            f"{['0x%08X' % s for s in actual]}, want {['0x%08X' % s for s in expected]}"
        )


def expect_address(image: bytes, lui_pc: int, low_pc: int, expected: int, label: str) -> None:
    upper = word(image, lui_pc)
    lower = word(image, low_pc)
    if upper >> 26 != 0x0F:
        raise VerificationError(f"{label}: 0x{lui_pc:08X} is not lui")
    reg = (upper >> 16) & 0x1F
    opcode = lower >> 26
    base = (lower >> 21) & 0x1F
    if base != reg or opcode not in {0x09, 0x20, 0x21, 0x23, 0x28, 0x29, 0x2B}:
        raise VerificationError(f"{label}: 0x{low_pc:08X} does not consume the lui register")
    actual = (((upper & 0xFFFF) << 16) + signed16(lower & 0xFFFF)) & 0xFFFFFFFF
    if actual != expected:
        raise VerificationError(f"{label}: built 0x{actual:08X}, want 0x{expected:08X}")


def verify_stream_entries(inputs: Inputs) -> list[str]:
    """The libstr entries the STR path calls, and who calls them."""
    image = inputs.exe
    checks: list[str] = []

    expect_word(image, ST_GET_NEXT, 0x00803821, "StGetNext first instruction")
    expect_word(image, ST_SET_STREAM, 0x27BDFFE0, "StSetStream prologue")
    expect_sites(image, ST_SET_STREAM, [0x80018864], "StSetStream call site")
    expect_sites(image, ST_FREE_RING, [0x80018AA4, 0x80018E28], "StFreeRing call sites")
    expect_sites(image, ST_UNSET_RING, [0x80018E9C], "StUnSetRing call site")
    expect_sites(image, DATA_READY_CALLBACK, [0x800E8E30], "data-ready callback dispatch site")
    expect_sites(image, ST_CD_INTERRUPT, [], "StCdInterrupt is reached only through its slot")
    expect_sites(image, CD_READ2, [0x80018924], "CdRead2 call site")
    checks.append(
        "libstr entries: StSetStream from 0x80018864, CdRead2 from 0x80018924, StFreeRing from "
        "0x80018AA4/0x80018E28, StUnSetRing from 0x80018E9C, data_ready_callback dispatched once"
    )

    expect_sites(image, STR_STARTUP, [0x80018B4C], "STR startup call site")
    expect_sites(
        image, STR_START_AND_FIRST_FRAME, [0x800180E8, 0x800183D8], "STR start call sites"
    )
    expect_sites(
        image, STR_PULL_NEXT_FRAME, [0x80018154, 0x80018414], "per-field frame-pull call sites"
    )
    expect_sites(
        image, STR_CONTINUE_CONDITION, [0x8001815C, 0x8001841C], "continue-condition call sites"
    )
    checks.append(
        "STR startup 0x80018788 has one caller (0x80018B4C); both movie drivers reach the start, "
        "the per-field pull and the continue condition"
    )
    return checks


def verify_first_frame_wait(inputs: Inputs) -> list[str]:
    """The startup's own first-frame wait, the one that precedes a live stream."""
    image = inputs.exe
    expect_jal(image, 0x800189A0, ST_GET_NEXT, "startup first-frame StGetNext")
    expect_word(image, 0x800189A4, 0x27A5001C, "startup wait header out-parameter")
    expect_word(image, 0x800189A8, 0x10400009, "startup wait tests the StGetNext result")
    expect_branch(image, 0x800189A8, 0x800189D0, "startup wait success arm")
    expect_jal(image, 0x800189B0, VSYNC, "startup wait VSync")
    expect_word(image, 0x800189B4, 0x00002021, "startup wait VSync(0) argument")
    expect_word(image, 0x800189BC, 0x2E020259, "startup wait limit compare")
    expect_branch(image, 0x800189C0, 0x800189A0, "startup wait back-edge")
    expect_word(image, 0x800189CC, 0x24020001, "startup wait timeout result")
    return [
        "startup first-frame wait: StGetNext at 0x800189A0, VSync(0) at 0x800189B0, at most 601 "
        "retries, failure result 1 at 0x800189CC"
    ]


def verify_per_field_wait(inputs: Inputs) -> list[str]:
    """The movie driver's per-field pull — the wait a running stream spends its life in."""
    image = inputs.exe
    expect_word(image, STR_PULL_NEXT_FRAME, 0x27BDFFD0, "per-field pull prologue")
    expect_word(image, 0x80018BA0, 0x00008021, "per-field pull retry counter cleared")
    expect_jal(image, 0x80018BAC, ST_GET_NEXT, "per-field pull StGetNext")
    expect_word(image, 0x80018BB0, 0x27A50014, "per-field pull header out-parameter")
    expect_word(image, 0x80018BB4, 0x10400009, "per-field pull tests the StGetNext result")
    expect_branch(image, 0x80018BB4, 0x80018BDC, "per-field pull success arm")
    expect_jal(image, 0x80018BBC, VSYNC, "per-field pull wait VSync")
    expect_word(image, 0x80018BC0, 0x00002021, "per-field pull VSync(0) argument")
    expect_word(image, 0x80018BC4, 0x26100001, "per-field pull retry increment")
    expect_word(image, 0x80018BC8, 0x2E020259, "per-field pull limit compare")
    expect_branch(image, 0x80018BCC, 0x80018BAC, "per-field pull back-edge")
    expect_word(image, 0x80018BD4, 0x0800638D, "per-field pull timeout jump")
    expect_word(image, 0x80018BD8, 0x24020001, "per-field pull timeout result")
    if (word(image, 0x80018BC8) & 0xFFFF) != WAIT_LIMIT:
        raise VerificationError("per-field pull retry limit is not 601")
    return [
        "per-field pull 0x80018B88: StGetNext at 0x80018BAC, success arm 0x80018BDC, VSync(0) at "
        "0x80018BBC returning to 0x80018BC4, at most 601 retries, timeout result 1 at 0x80018BD8 — "
        "so 0x80018BC4 is the only instruction that can advance the wait"
    ]


def verify_continue_condition(inputs: Inputs) -> list[str]:
    """The movie loop's continue condition and the words it reads."""
    image = inputs.exe
    expect_word(image, STR_CONTINUE_CONDITION, 0x3C028014, "continue-condition prologue")
    expect_address(
        image,
        STR_CONTINUE_CONDITION,
        STR_CONTINUE_CONDITION + 4,
        MDEC_OUTPUT_OUTSTANDING,
        "continue condition reads the MDEC-output-outstanding flag",
    )
    expect_branch(
        image, STR_CONTINUE_CONDITION + 12, STR_CONTINUE_CONDITION, "continue-condition spin"
    )
    expect_address(
        image,
        STR_CONTINUE_CONDITION + 20,
        STR_CONTINUE_CONDITION + 24,
        LOOP_KEEP,
        "continue condition returns the loop-keep word",
    )
    expect_address(
        image,
        STR_CONTINUE_CONDITION + 28,
        STR_CONTINUE_CONDITION + 32,
        LOOP_KEEP_MIRROR,
        "continue condition refreshes the loop-keep mirror",
    )
    expect_word(image, STR_CONTINUE_CONDITION + 36, 0x03E00008, "continue condition returns")
    return [
        "0x80018EEC spins on 0x80139634 (MDEC output outstanding), returns 0x801395E8 and refreshes "
        "0x801395E4 — the movie loop continues only while no strip is still being output"
    ]


def verify_movie_drivers(inputs: Inputs) -> list[str]:
    """Both movie drivers: the loop back-edge, and the completion call only after the loop."""
    image = inputs.exe
    expect_word(image, STR_DRIVER_INDEXED, 0x27BDFFC0, "indexed movie driver prologue")
    expect_branch(image, 0x80018194, 0x80018104, "indexed movie loop back-edge")
    expect_jal(image, 0x8001815C, STR_CONTINUE_CONDITION, "indexed driver reads the condition")
    expect_jal(image, 0x800181D4, STR_COMPLETION, "indexed driver completion call")
    expect_word(image, STR_DRIVER_ENTRY_ONE, 0x27BDFFC0, "entry-one movie driver prologue")
    expect_branch(image, 0x80018484, 0x800183F4, "entry-one movie loop back-edge")
    expect_jal(image, 0x80018414, STR_PULL_NEXT_FRAME, "entry-one driver pulls the next frame")
    expect_jal(image, 0x8001841C, STR_CONTINUE_CONDITION, "entry-one driver reads the condition")
    expect_jal(image, 0x800184BC, STR_COMPLETION, "entry-one driver completion call")
    expect_sites(image, STR_COMPLETION, [0x800181D4, 0x800184BC], "completion call sites")
    return [
        "both movie drivers (0x80018000, 0x800182E8) loop on 0x80018EEC and reach the completion "
        "owner 0x80018E50 only after that loop exits; the entry-one driver flips its parity word "
        "0x80139594 only inside the loop"
    ]


def verify_completion(inputs: Inputs) -> list[str]:
    """The completion owner and its ordered transaction — the only stream teardown."""
    image = inputs.exe
    expect_word(image, STR_COMPLETION, 0x27BDFFE0, "completion prologue")
    expect_jal(image, 0x80018E5C, RESET_MOVIE_STATE, "completion resets movie state")
    expect_word(image, 0x80018E64, 0x24040009, "completion first command is CdlPause")
    expect_jal(image, 0x80018E6C, CD_CONTROL_B, "completion issues CdControlB")
    expect_branch(image, 0x80018E74, 0x80018E68, "completion retries CdlPause")
    expect_jal(image, 0x80018E7C, VSYNC, "completion first field fence")
    expect_word(image, 0x80018E80, 0x00002021, "completion first fence is VSync(0)")
    expect_jal(image, 0x80018E84, CD_SYNC, "completion calls CdSync after the fence")
    expect_jal(image, 0x80018E8C, CD_READY, "completion calls CdReady")
    expect_jal(image, 0x80018E94, DEC_DCT_OUT, "completion calls DecDCTOut")
    expect_jal(image, 0x80018E9C, ST_UNSET_RING, "completion calls StUnSetRing")
    expect_jal(image, 0x80018EB4, VSYNC, "completion second field fence")
    expect_word(image, 0x80018EB8, 0x24040003, "completion second fence is VSync(3)")
    expect_word(image, 0x80018EBC, 0x2404000E, "completion second command is CdlSetmode")
    expect_jal(image, 0x80018EC4, CD_CONTROL, "completion issues CdControl")
    expect_branch(image, 0x80018ECC, 0x80018EC0, "completion retries CdlSetmode")
    expect_jal(image, 0x80018ED4, VSYNC, "completion third field fence")
    expect_word(image, 0x80018ED8, 0x24040003, "completion third fence is VSync(3)")
    if (word(image, 0x80018E64) & 0xFFFF) != CDL_PAUSE:
        raise VerificationError("completion first command id is not CdlPause 9")
    if (word(image, 0x80018EBC) & 0xFFFF) != CDL_SETMODE:
        raise VerificationError("completion second command id is not CdlSetmode 14")
    return [
        "completion 0x80018E50 = CdlPause retry, VSync(0), CdSync, CdReady, DecDCTOut, "
        "StUnSetRing, VSync(3), CdlSetmode retry, VSync(3) — the only path that stops the drive"
    ]


def verify_published_words(inputs: Inputs) -> list[str]:
    """The words the startup publishes once and the ring cursors the guest then moves."""
    image = inputs.exe
    expect_address(image, 0x80018804, 0x80018808, LOOP_KEEP_MIRROR, "startup loop-keep mirror")
    expect_address(image, 0x8001880C, 0x80018810, LOOP_KEEP, "startup loop-keep word")
    expect_address(image, 0x80018814, 0x80018818, STREAM_FLAVOUR, "startup stream flavour")
    expect_address(image, 0x80018C18, 0x80018C1C, FRAME_NUMBER_MIRROR, "pull frame-number mirror")
    expect_address(image, 0x800183E0, 0x800183E4, MOVIE_PARITY, "entry-one driver parity reset")
    expect_address(image, 0x8001840C, 0x80018410, MOVIE_PARITY, "entry-one driver parity flip")
    expect_address(image, 0x800E8188, 0x800E818C, RING_WRITE_CURSOR, "data-ready write cursor")
    expect_address(image, 0x800E81D0, 0x800E81D4, RING_FRAME_CURSOR, "data-ready frame cursor")
    expect_address(image, 0x800E81E8, 0x800E81EC, RING_WRITE_CURSOR, "data-ready write-cursor store")
    expect_address(image, 0x800E83F8, 0x800E83FC, RING_READ_CURSOR, "StGetNext read cursor")
    return [
        "the startup publishes 0x801395E8 once from its tenth argument (0x80018810) and "
        "0x800F1D88 (0x80018818); the entry-one driver flips its parity 0x80139594 only inside "
        "the loop; data_ready_callback advances 0x80173C90 from 0x80173C8C and StGetNext reads "
        "0x80173C94"
    ]


GROUPS = (
    verify_stream_entries,
    verify_first_frame_wait,
    verify_per_field_wait,
    verify_continue_condition,
    verify_movie_drivers,
    verify_completion,
    verify_published_words,
)


def verify(inputs: Inputs, *, check_digest: bool = True) -> list[str]:
    digest = hashlib.sha1(inputs.exe).hexdigest()
    if check_digest and digest != EXPECTED_SHA1:
        raise VerificationError(f"executable SHA-1 {digest}, want retail {EXPECTED_SHA1}")
    checks: list[str] = []
    for group in GROUPS:
        checks.extend(group(inputs))
    return checks


def mutate_word(image: bytes, pc: int, value: int) -> bytes:
    out = bytearray(image)
    struct.pack_into("<I", out, TEXT_FILE_OFFSET + pc - TEXT_VADDR, value)
    return bytes(out)


def load_inputs(exe: Path) -> Inputs:
    if not exe.is_file():
        raise VerificationError(f"{exe} is missing; provision the executable first")
    return Inputs(exe.read_bytes())


def expect_refusal(label: str, inputs: Inputs) -> str:
    try:
        verify(inputs, check_digest=False)
    except VerificationError:
        return f"PASS: refused {label}"
    raise VerificationError(f"selftest accepted a mutation: {label}")


def selftest(inputs: Inputs) -> list[str]:
    results = [
        expect_refusal(
            "a third StGetNext call site",
            Inputs(mutate_word(inputs.exe, 0x80018000, 0x0C03A0FD)),
        ),
        expect_refusal(
            "a per-field pull wait limit other than 601",
            Inputs(mutate_word(inputs.exe, 0x80018BC8, 0x2E020258)),
        ),
        expect_refusal(
            "a per-field pull whose wait is not VSync",
            Inputs(mutate_word(inputs.exe, 0x80018BBC, 0x0C03936C + 4)),
        ),
        expect_refusal(
            "a per-field pull whose post-VSync instruction is not the retry increment",
            Inputs(mutate_word(inputs.exe, 0x80018BC4, 0x00000000)),
        ),
        expect_refusal(
            "a continue condition that does not spin on the MDEC flag",
            Inputs(mutate_word(inputs.exe, 0x80018EF0, 0x8C429630)),
        ),
        expect_refusal(
            "a completion that skips StUnSetRing",
            Inputs(mutate_word(inputs.exe, 0x80018E9C, 0x0C03A04C + 4)),
        ),
        expect_refusal(
            "a completion whose first command is not CdlPause",
            Inputs(mutate_word(inputs.exe, 0x80018E64, 0x2404000E)),
        ),
        expect_refusal(
            "an entry-one loop back-edge that leaves the loop body",
            Inputs(mutate_word(inputs.exe, 0x80018484, 0x1200FFDA)),
        ),
        expect_refusal(
            "a data-ready callback reading the wrong ring cursor",
            Inputs(mutate_word(inputs.exe, 0x800E818C, 0x8C423C94)),
        ),
        expect_refusal(
            "a startup that publishes no loop-keep word",
            Inputs(mutate_word(inputs.exe, 0x80018810, 0xAC2295E4)),
        ),
    ]
    verify(inputs)
    results.append(f"PASS: accepted the retail image (SHA-1 {hashlib.sha1(inputs.exe).hexdigest()})")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--check", action="store_true", help="verify the retail STR completion path")
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
        print(f"PASS — {len(checks)} STR completion path groups; SHA-1 {EXPECTED_SHA1}")
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
