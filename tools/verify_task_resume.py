#!/usr/bin/env python3
"""Verify that a retail task's field-boundary resume is distinguishable from its own return.

`x4::bios_threads::run_guest_entry` resumes a task at the typed exit's guest PC, so the activation's
return address must be fixed at task creation, not re-read from `$ra`: a title field boundary is a
`jal VSync` whose resume address is that `jal`'s own return address, and `LightrecExecutor::blockBoundary`
would classify it as `GuestReturn`. This gate pins the call-site identities in SLUS_005.61 and checks
the product ends a run with the task still scheduled and a picture advancing.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
DEFAULT_PRODUCT = ROOT / "build/ci/bin/megamanx4_port"
EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"
TEXT_VADDR = 0x80010000
TEXT_FILE_OFFSET = 0x800

VSYNC = 0x800E4DB0
OPEN_THREAD = 0x800EDD9C
ST_GET_NEXT = 0x800E83F4

# The continuations x4::movie::fieldBoundary accepts: continuation -> (jal VSync call site, word the resume executes).
FIELD_RETURN_ADDRESSES = {
    0x8001810C: (0x80018104, 0x3C028014),  # lui $2,0x8014
    0x8001842C: (0x80018424, 0x0C0048CA),  # jal 0x80018AD0 (the resume makes another call)
    0x800185D8: (0x800185D0, 0x0C03A883),  # jal 0x80018B88 (the resume makes another call)
    0x80018BC4: (0x80018BBC, 0x26100001),  # addiu $16,$16,1 — the per-field pull's retry increment
}
JAL_VSYNC = 0x0C03936C
MOVE_ZERO_A0 = 0x00002021
JAL_RET_RA = 0x03E00008

# OpenTh call sites and the a1/a2 (SP, GP) loads before each; a0 (entry) is not loaded from the descriptor, so it is not pinned.
OPEN_THREAD_SITES = {
    0x800126F8: {0x800126F0: 0x8C450010, 0x800126F4: 0x8C460044},
    0x80012788: {0x80012778: 0x8C258110, 0x80012784: 0x8C268144},
}
OPEN_THREAD_JAL = 0x0C03B767
MOVIE_DRIVER_RETURNS = (0x800182E0, 0x800185F0)

# The per-field pull's only route back to its VSync wait.
RETRY_INCREMENT = 0x80018BC4
RETRY_STGETNEXT = 0x80018BAC
RETRY_LIMIT_COMPARE = 0x80018BC8
RETRY_BACK_EDGE = 0x80018BCC
RETRY_LIMIT = 601

# A present counts as a picture when at least this share is non-black.
MIN_NON_BLACK_SHARE = 0.01
DEFAULT_FIELDS = (40, 80, 120, 160, 200)

PRESENT_RE = re.compile(r"present_shot\] wrote (\S+) .* non-black (\d+)/(\d+) \(([\d.]+)%\)")
RESUMED_RE = re.compile(r"x4-thread\] retail task entry (0x[0-9A-F]{8}) needed more than .* RESUMED at (0x[0-9A-F]{8})")
RETIRED_RE = re.compile(r"x4-thread\] retail task entry (0x[0-9A-F]{8}) reached .* RETIRED after (\d+) turn")
ERROR_RE = re.compile(r"\[x4-thread:error\]")


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


def expect_word(image: bytes, pc: int, expected: int, label: str) -> None:
    actual = word(image, pc)
    if actual != expected:
        raise VerificationError(f"{label}: word at 0x{pc:08X} is 0x{actual:08X}, want 0x{expected:08X}")


def expect_jal(image: bytes, pc: int, target: int, label: str) -> None:
    actual = jal_target(word(image, pc), pc)
    if actual != target:
        raise VerificationError(
            f"{label}: jal at 0x{pc:08X} targets 0x{actual:08X}, want 0x{target:08X}"
        )


def expect_branch(image: bytes, pc: int, target: int, label: str) -> None:
    actual = branch_target(word(image, pc), pc)
    if actual != target:
        raise VerificationError(
            f"{label}: branch at 0x{pc:08X} goes to 0x{actual:08X}, want 0x{target:08X}"
        )


def verify_continuations_are_return_addresses(inputs: Inputs) -> list[str]:
    """Each accepted continuation is a `jal VSync`'s OWN return address, so it is `r[31]`."""
    image = inputs.exe
    for continuation, (call_site, resumed) in sorted(FIELD_RETURN_ADDRESSES.items()):
        if call_site + 8 != continuation:
            raise VerificationError(
                f"accepted continuation 0x{continuation:08X} is not call_site+8 of 0x{call_site:08X}"
            )
        expect_jal(image, call_site, VSYNC, f"field wait at 0x{continuation:08X}")
        # call_site + 8 skips the delay slot, which carries the VSync(0) argument.
        expect_word(image, call_site + 4, MOVE_ZERO_A0, f"VSync(0) argument at 0x{call_site + 4:08X}")
        expect_word(image, continuation, resumed, f"instruction the resume executes at 0x{continuation:08X}")
    return [
        "the four continuations x4::movie::fieldBoundary accepts ("
        + ", ".join(f"0x{address:08X}" for address in sorted(FIELD_RETURN_ADDRESSES))
        + ") are each the return address of a measured `jal VSync(0)`: call site +4 is the argument "
        "delay slot and +8 is the continuation, so resuming there resumes at `r[31]` by construction. "
        "Two of the four continuations are themselves `jal` instructions (0x8001842C -> 0x80018AD0, "
        "0x800185D8 -> 0x80018B88), so the guest's live `$ra` is a DIFFERENT address after each resume"
    ]


def verify_retry_needs_the_pull(inputs: Inputs) -> list[str]:
    """0x80018BC4 is only reachable after `jal StGetNext`, so a stalled pull never re-enters it."""
    image = inputs.exe
    expect_jal(image, RETRY_STGETNEXT, ST_GET_NEXT, "per-field pull StGetNext")
    expect_word(image, RETRY_INCREMENT, 0x26100001, "per-field pull retry increment")
    expect_word(image, RETRY_LIMIT_COMPARE, 0x2E020259, "per-field pull limit compare")
    if (word(image, RETRY_LIMIT_COMPARE) & 0xFFFF) != RETRY_LIMIT:
        raise VerificationError("per-field pull retry limit is not 601")
    expect_branch(image, RETRY_BACK_EDGE, RETRY_STGETNEXT, "per-field pull back-edge")
    return [
        "the per-field pull's VSync wait is reached only from 0x80018BCC `bnez -> 0x80018BAC`, which "
        "is only reachable after `jal StGetNext` (0x800E83F4) — so a host that does not execute "
        "0x80018BC4 on resume never re-enters the pull, and the guest ring fills with nothing reading it"
    ]


def verify_activation_has_no_return_address(inputs: Inputs) -> list[str]:
    """OpenTh receives entry/SP/GP and nothing else, and a task body can still return."""
    image = inputs.exe
    for site, loads in sorted(OPEN_THREAD_SITES.items()):
        expect_jal(image, site, OPEN_THREAD, f"OpenTh call at 0x{site:08X}")
        if word(image, site) != OPEN_THREAD_JAL:
            raise VerificationError(f"OpenTh call at 0x{site:08X} is not the expected jal word")
        for at, expected in sorted(loads.items()):
            expect_word(image, at, expected, f"OpenTh argument load at 0x{at:08X}")
            if word(image, at) >> 26 != 0x23:
                raise VerificationError(
                    f"0x{at:08X} is not a `lw`, so the three-argument claim is unproven"
                )
    for return_site in MOVIE_DRIVER_RETURNS:
        expect_word(image, return_site, JAL_RET_RA, f"movie driver return at 0x{return_site:08X}")
    return [
        "both guest OpenTh (0x800EDD9C) call sites (0x800126F8, 0x80012788) pass exactly three "
        "arguments — entry, SP (a1), GP (a2) — and neither stores a return address beforehand, so "
        "the activation the host creates carries no guest return address to adopt; both movie "
        "drivers still end in `jr $ra` (0x800182E0, 0x800185F0), so a task body can return and the "
        "owner must be able to observe that"
    ]

def run_product(product: Path, fields: tuple[int, ...], log: Path) -> int:
    """Run the product headless for `fields` display fields; return its exit code.

    The log is truncated first because PSXPORT_LOG_FILE appends.
    """
    environment = dict(os.environ)
    environment.update(
        {
            "PSXPORT_NATIVE_FRAMES": str(max(fields)),
            "PSXPORT_NOAUDIO": "1",
            "PSXPORT_NOPACE": "1",
            "PSXPORT_VK_HEADLESS": "1",
            "PSXPORT_PRESENT_SHOT_AT": ",".join(str(field) for field in fields),
            "PSXPORT_LOG_FILE": str(log),
        }
    )
    log.write_text("", encoding="utf-8")
    completed = subprocess.run(
        [str(product)],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    print(f"[verify-resume] product exit={completed.returncode} log={log}")
    return completed.returncode


def verify_product_picture(product: Path, exe: Path, fields: tuple[int, ...], work: Path) -> list[str]:
    """The product half: a task that is still scheduled, and a picture that is advancing."""
    if not product.is_file():
        raise VerificationError(
            f"{product} does not exist — build the product first "
            f"(cmake --build build --target megamanx4_port). This gate refuses to skip."
        )
    if not exe.is_file():
        raise VerificationError(
            f"{exe} does not exist — provision the executable first "
            f"(python3 tools/extract_exe.py). This gate refuses to skip."
        )
    work.mkdir(parents=True, exist_ok=True)
    log = work / "product.log"
    exit_code = run_product(product, fields, log)
    if exit_code != 0:
        raise VerificationError(f"the product exited {exit_code}; the log is at {log}")

    text = log.read_text(encoding="utf-8", errors="replace")
    errors = ERROR_RE.findall(text)
    if errors:
        raise VerificationError(
            f"the task owner reported {len(errors)} error line(s); first: {errors[0]!r}. "
            f"A task that cannot be scheduled is a product failure, not a black frame."
        )
    retired = RETIRED_RE.findall(text)
    if retired:
        raise VerificationError(
            f"the retail task RETIRED {len(retired)} time(s) (first at {retired[0][0]} after "
            f"{retired[0][1]} turn(s)). A retired task is never rescheduled, so no later present can "
            f"be trusted to advance."
        )
    resumed = RESUMED_RE.findall(text)
    if not resumed:
        raise VerificationError(
            "no task turn was resumed at a host-turn budget. Retail DecDCTvlc (0x800ED574) needs "
            "1.082 display fields, so at least one must appear in a run that decodes STR frames; "
            "0 means the budget path was never reached, which is 'not measured', not 'fine'."
        )

    presents = [
        (path, int(black_free), int(total))
        for path, black_free, total, _percent in PRESENT_RE.findall(text)
    ]
    if len(presents) != len(fields):
        raise VerificationError(
            f"asked for {len(fields)} sampled present(s) {list(fields)} and the product reported "
            f"{len(presents)}: {[(p[0], p[1], p[2]) for p in presents]}"
        )
    for (name, black_free, total), field in zip(presents, fields):
        share = black_free / total if total else 0.0
        print(f"[verify-resume]   field {field:>4}: non-black {black_free}/{total} ({100.0 * share:.2f}%)")
    final_name, final_free, final_total = presents[-1]
    final_share = final_free / final_total if final_total else 0.0
    if final_share < MIN_NON_BLACK_SHARE:
        raise VerificationError(
            f"the last sampled present ({final_name}) is {100.0 * final_share:.2f}% non-black, under "
            f"the {100.0 * MIN_NON_BLACK_SHARE:.1f}% floor. A task that retired reproduces this."
        )

    def digest(name: str) -> str:
        return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()

    penultimate = digest(presents[-2][0])
    last = digest(final_name)
    if penultimate == last:
        raise VerificationError(
            f"the last two sampled presents are byte-identical ({final_name}), so the picture is "
            f"FROZEN rather than advancing. A non-black still frame does not satisfy this gate."
        )

    return [
        f"{len(resumed)} task turn(s) resumed at a host-turn budget and 0 retired over "
        f"{max(fields)} display fields",
        f"last sampled present {final_name}: {final_free}/{final_total} non-black "
        f"({100.0 * final_share:.2f}%), and the two last presents differ "
        f"({penultimate[:12]} vs {last[:12]}) so the picture is advancing",
    ]


def selftest(image: bytes) -> list[str]:
    """Corrupt one word per rule and require a refusal."""
    cases: list[tuple[str, int, int, object]] = [
        (
            "a continuation that is not a jal's return address",
            RETRY_INCREMENT,
            0x00000000,
            verify_continuations_are_return_addresses,
        ),
        (
            "a per-field pull with no StGetNext on its back-edge",
            RETRY_BACK_EDGE,
            0x1000FFFF,
            verify_retry_needs_the_pull,
        ),
        (
            "an OpenTh call that takes a fourth argument",
            0x800126F0,
            0x00000000,
            verify_activation_has_no_return_address,
        ),
        (
            "a movie driver that never returns",
            MOVIE_DRIVER_RETURNS[0],
            0x00000000,
            verify_activation_has_no_return_address,
        ),
    ]
    for label, address, replacement, rule in cases:
        damaged = bytearray(image)
        offset = TEXT_FILE_OFFSET + address - TEXT_VADDR
        struct.pack_into("<I", damaged, offset, replacement)
        try:
            rule(Inputs(exe=bytes(damaged)))
        except VerificationError:
            continue
        raise VerificationError(f"selftest: the gate ACCEPTED {label} (0x{address:08X})")
    return [f"selftest: all {len(cases)} negative case(s) were refused, so the rules can fail"]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--product", type=Path, default=DEFAULT_PRODUCT)
    parser.add_argument(
        "--fields",
        default=",".join(str(field) for field in DEFAULT_FIELDS),
        help="comma-separated display fields to sample a present at (the last one must be a picture)",
    )
    parser.add_argument(
        "--skip-product",
        action="store_true",
        help="run only the guest-byte rules and the selftest; refuses to report a product verdict",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    try:
        fields = tuple(int(token) for token in options.fields.split(",") if token)
        if len(fields) < 2:
            raise VerificationError("--fields needs at least two samples: one is not 'advancing'")
        exe = options.exe.resolve()
        if not exe.is_file():
            raise VerificationError(f"{exe} does not exist — provision it (python3 tools/extract_exe.py)")
        image = exe.read_bytes()
        digest = hashlib.sha1(image).hexdigest()
        if digest != EXPECTED_SHA1:
            raise VerificationError(
                f"{exe} sha1 {digest} is not the authenticated SLUS_005.61 {EXPECTED_SHA1}"
            )
        inputs = Inputs(exe=image)
        print(f"[verify-resume] SLUS_005.61 sha1 {digest} verified")
        for rule in (
            verify_continuations_are_return_addresses,
            verify_retry_needs_the_pull,
            verify_activation_has_no_return_address,
        ):
            for line in rule(inputs):
                print(f"[verify-resume]   {line}")
        for line in selftest(image):
            print(f"[verify-resume]   {line}")
        if options.skip_product:
            print("[verify-resume] --skip-product: no product verdict was produced")
            return 0
        for line in verify_product_picture(
            options.product.resolve(), exe, fields, ROOT / "scratch" / "verify_task_resume"
        ):
            print(f"[verify-resume]   {line}")
    except VerificationError as error:
        print(f"[verify-resume] FAILED: {error}", file=sys.stderr)
        return 1
    print("[verify-resume] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
