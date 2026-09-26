#!/usr/bin/env python3
"""verify_cull.py — bind the visibility-cull owner to SLUS_005.61's own bytes.

WHY THIS EXISTS. game/core/visibility_cull.{h,cpp} states SLUS_005.61's visibility windows, and every
number in it is an immediate in the executable. A native owner that hard-codes a constant the image does
not carry is not a port; it is a guess that happens to compile. This gate re-derives each one FROM the
image and fails when the repository disagrees, and it does the reverse check as well: the owner's header
is PARSED, so the binding is to the shipped constant rather than to a copy of it that can drift.

It also re-runs the census with a denominator, and the caller-saved leaf measurement that licenses the
adapters to publish only the flag byte and $v0. Both print what they scanned and what they matched, and
the selftest mutates an expected value so the gate is known to be capable of failing.

BLIND SPOT, STATED. The census decodes the whole text section, which also holds data tables, so a data
word can be reported as a window. Every window this gate ASSERTS is a specific address whose bytes it
prints on mismatch, and the classified owners were each confirmed by disassembling their enclosing
function rather than by the sweep alone.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"
OWNER_HEADER = ROOT / "game/core/visibility_cull.h"

# ── the measured windows, as the image states them ───────────────────────────────────────────────
# (addend, bound) per axis, from the `addiu` and the `sltiu`/`sltu` bound. A parametric site computes
# its bound in a register, so its bound is expressed as the register form 2*half + extent.
@dataclasses.dataclass(frozen=True)
class Window:
    addend_x: int
    bound_x: int
    addend_y: int
    bound_y: int
    parametric: bool = False


# Every owner, with the ADDRESSES the immediates were read at, so a failure names the instruction.
OWNERS: dict[int, Window] = {
    # func_8002B160: addiu 0x40 @ 0x8002B1BC, sltiu 0x1C0 @ 0x8002B1C4; addiu 0x40 @ 0x8002B1D0,
    # sltiu 0x170 @ 0x8002B1D8. Registered here, out of scope: its callers read the return value.
    0x8002B160: Window(0x40, 0x1C0, 0x40, 0x170),
    # func_8002B1E8: bound in registers, `sll $3,$8,1` @ 0x8002B248 + addiu 0x140 @ 0x8002B24C and
    # `sll $3,$6,1` @ 0x8002B268 + addiu 0xF0 @ 0x8002B26C, so bound = 2*half + 320 / 2*half + 240.
    0x8002B1E8: Window(0x00, 2 * 0x00 + 320, 0x00, 2 * 0x00 + 240, parametric=True),
    # is_on_screen: addiu 0x20 @ 0x8002B2E8, sltiu 0x180 @ 0x8002B2F0; addiu 0x20 @ 0x8002B2F8,
    # sltiu 0x130 @ 0x8002B300.
    0x8002B288: Window(0x20, 0x180, 0x20, 0x130),
    # func_8002B318: bound in registers, `sll $3,$8,1` @ 0x8002B37C + addiu 0x140 @ 0x8002B37C.
    0x8002B318: Window(0x00, 2 * 0x00 + 320, 0x00, 2 * 0x00 + 240, parametric=True),
    # func_8002B3C0: addiu 0x60 @ 0x8002B420, sltiu 0x200 @ 0x8002B428; addiu 0x50 @ 0x8002B430,
    # sltiu 0x190 @ 0x8002B438.
    0x8002B3C0: Window(0x60, 0x200, 0x50, 0x190),
    # 0x800B8490: addiu 0x40 @ 0x800B84B0, sltiu 0x1C0 @ 0x800B84B8; addiu 0x40 @ 0x800B84C4,
    # sltiu 0x170 @ 0x800B84CC.
    0x800B8490: Window(0x40, 0x1C0, 0x40, 0x170),
    # quad_is_on_screen: no addend at all; sltiu 0x140 @ 0x800D4774 / 0x800D4804 / 0x800D4894 /
    # 0x800D4924 and sltiu 0xF0 @ 0x800D4780 / 0x800D4810 / 0x800D48A0 / 0x800D4930.
    0x800D46F4: Window(0x00, 0x140, 0x00, 0x0F0),
}

# The four quad corners, as the eight `lhu` offsets the body reads them at.
QUAD_CORNERS = ((0x16, 0x1A), (0x1E, 0x22), (0x26, 0x2A), (0x2E, 0x32))
# The two layouts' header offsets, and the camera array the world-to-screen recovery indexes.
BASE_BACKGROUND_OFFSET = 0x14
QUAD_BACKGROUND_OFFSET = 0x37
X_INTEGER = 0x0A
Y_INTEGER = 0x0E
CAMERA_LAYERS = 0x801419B0
CAMERA_STRIDE = 0x54
CAMERA_SCROLL_X = 0x0A
CAMERA_SCROLL_Y = 0x0E
ON_SCREEN = 0x03

# The seven sites the owner registers, and the call-site census that must hold for each.
EXPECTED_CALL_SITES = {
    0x8002B160: 57,
    0x8002B1E8: 122,
    0x8002B288: 279,
    0x8002B318: 403,
    0x8002B3C0: 9,
    0x800B8490: 1,
    0x800D46F4: 22,
}
# Reported, not registered: the two intro-effect AABB windows in search_light.c and C594C.c.
OUT_OF_SCOPE_CALL_SITES = {0x800D4024: 1, 0x800D57A8: 1}


class Image:
    """The executable's text section, addressed by guest virtual address."""

    def __init__(self, path: Path) -> None:
        data = path.read_bytes()
        self.sha1 = hashlib.sha1(data).hexdigest()
        t_addr, t_size = struct.unpack_from("<II", data, 0x18)
        self.base = t_addr
        self.words = [
            struct.unpack_from("<I", data, 0x800 + 4 * i)[0] for i in range(t_size // 4)
        ]

    def word(self, address: int) -> int:
        if not self.base <= address < self.base + 4 * len(self.words) or address % 4:
            raise LookupError(f"0x{address:08X} is not a word in the text section")
        return self.words[(address - self.base) // 4]

    def simm(self, address: int) -> int:
        raw = self.word(address) & 0xFFFF
        return raw - 0x10000 if raw & 0x8000 else raw

    def uimm(self, address: int) -> int:
        return self.word(address) & 0xFFFF

    def call_sites(self, target: int) -> int:
        count = 0
        for word in self.words:
            if word >> 26 == 0x03 and ((word & 0x03FFFFFF) << 2) + (self.base & 0xF0000000) == target:
                count += 1
        return count


def find_window_instructions(
    image: Image, site: int, window: Window, span: int = 0x60, want: str = "any"
) -> list[str]:
    """The `addiu`/`sltiu` in the site's body that carry the recovered immediates.

    `want` selects the axis: "addend" or "bound", on "x" or "y". It exists because the check is a
    disjunction over both axes, so a test that mutates one bound still matches the other — the mistake
    this gate's own selftest made first time round.
    """
    found: list[str] = []
    for offset in range(0, span, 4):
        address = site + offset
        if address + 4 > image.base + 4 * len(image.words):
            break
        word = image.word(address)
        if want in ("any", "addend") and word >> 26 == 0x09:  # addiu
            imm = image.simm(address)
            if imm in (window.addend_x, window.addend_y):
                found.append(f"0x{address:08X} addiu {imm:#x}")
        if want in ("any", "bound") and word >> 26 == 0x0B and word & 0x001F0000:  # sltiu, rs != 0
            imm = image.uimm(address)
            if imm in (window.bound_x, window.bound_y):
                found.append(f"0x{address:08X} sltiu {imm:#x}")
    return found


# How far into each body to look for its immediates. The quad's four corner blocks are spread over
# 0x250 bytes, so a single range would miss three of its four bounds.
SITE_SPANS = {0x800D46F4: 0x260, 0x800D4024: 0x100, 0x800D57A8: 0x100}


def find_extent_addends(image: Image, site: int, span: int) -> list[str]:
    """The `addiu $r,$r,0x140` / `0xF0` that finish a register-form bound of `2*half + extent`."""
    found: list[str] = []
    for offset in range(0, span, 4):
        address = site + offset
        if address + 4 > image.base + 4 * len(image.words):
            break
        if (image.word(address) >> 26) != 0x09:
            continue
        imm = image.simm(address)
        if imm in (0x140, 0xF0):
            found.append(f"0x{address:08X} addiu {imm:#x}")
    return found


def check_owner_header() -> list[str]:
    """Parse the owner's own header and confirm it states the measured numbers."""
    problems: list[str] = []
    text = OWNER_HEADER.read_text()

    def constant(name: str) -> int | None:
        match = re.search(rf"{name}\s*=\s*(-?(?:0[xX][0-9A-Fa-f]+|\d+))", text)
        return int(match.group(1), 0) if match else None

    def slack(name: str) -> int | None:
        match = re.search(rf"{name}\s*=\s*(-?(?:0[xX][0-9A-Fa-f]+|\d+))\s*;", text)
        return int(match.group(1), 0) if match else None

    for name, expected in (
        ("kWidth", 320),
        ("kHeight", 240),
        ("kTight", 0x20),
        ("kWideX", 0x60),
        ("kWideY", 0x50),
        ("kLoose", 0x40),
    ):
        actual = slack(name)
        if actual != expected:
            problems.append(f"owner RetailScreen/RetailSlack {name} = {actual}, image says {expected:#x}")
    for name, expected in (
        ("kCameraLayersAddress", CAMERA_LAYERS),
        ("kCameraLayerStride", CAMERA_STRIDE),
        ("kCameraScrollX", CAMERA_SCROLL_X),
        ("kCameraScrollY", CAMERA_SCROLL_Y),
        ("kOnScreenOffset", ON_SCREEN),
        ("kBaseObjectBackgroundOffset", BASE_BACKGROUND_OFFSET),
        ("kQuadObjectBackgroundOffset", QUAD_BACKGROUND_OFFSET),
        ("kPositionIntegerX", X_INTEGER),
        ("kPositionIntegerY", Y_INTEGER),
    ):
        actual = constant(name)
        if actual != expected:
            problems.append(f"owner {name} = {actual}, image says {expected:#x}")
    for index, (x, y) in enumerate(QUAD_CORNERS):
        if f"0x{x:02X}u" not in text or f"0x{y:02X}u" not in text:
            problems.append(f"owner kQuadCornerX/Y does not state the measured corner {index} ({x:#x},{y:#x})")
    for name, expected in (
        ("kBaseOnScreenTight", 0x8002B288),
        ("kBaseOnScreenWide", 0x8002B3C0),
        ("kBaseOnScreenParametric", 0x8002B318),
        ("kBaseOffScreenParametric", 0x8002B1E8),
        ("kBaseOffScreenLoose", 0x8002B160),
        ("kBaseOffScreenLayerZero", 0x800B8490),
        ("kQuadOnScreen", 0x800D46F4),
    ):
        # Whitespace-tolerant, because `clang-format` is free to reflow the initialiser across lines
        # and a gate that breaks on formatting is a gate that gets deleted instead of fixed.
        match = re.search(rf"{name}\{{\s*(0x[0-9A-Fa-f]+)u", text)
        if not match or int(match.group(1), 16) != expected:
            problems.append(f"owner {name} address is {match.group(1) if match else 'absent'}, "
                            f"image census says {expected:#x}")
    return problems


def run_check(exe: Path) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if not exe.exists():
        return False, [f"no executable at {exe}; provision it with tools/resolve_disc.py + tools/extract_exe.py"]
    image = Image(exe)
    if image.sha1 != EXPECTED_SHA1:
        return False, [f"executable sha1 {image.sha1} is not SLUS_005.61 ({EXPECTED_SHA1})"]

    print(f"[cull] executable sha1 {image.sha1}, text section [{image.base:#x}, "
          f"{image.base + 4 * len(image.words):#x}), {len(image.words)} words")

    for site, window in sorted(OWNERS.items()):
        if site not in EXPECTED_CALL_SITES:
            problems.append(f"{site:#010x} is asserted as a window but is not a registered site")
        span = SITE_SPANS.get(site, 0x100)
        bounds = find_window_instructions(image, site, window, span, want="bound")
        addends = find_window_instructions(image, site, window, span, want="addend")
        # The BOUND is what decides the cull, so it is asserted on its own. Requiring only "some
        # instruction matched" let an addend match stand in for a missing bound, which is the mistake
        # this gate's first version made.
        if not window.parametric and not bounds:
            problems.append(
                f"{site:#010x}: no sltiu carries the recovered bounds {window.bound_x:#x}/{window.bound_y:#x}"
            )
        if window.addend_x and not addends:
            problems.append(
                f"{site:#010x}: no addiu carries the recovered addend {window.addend_x:#x}"
            )
        if window.parametric:
            # A register-form bound still states the retail screen extent, as the `addiu` that finishes
            # `2*half + extent`. Asserting only "it is parametric" would leave the extent unverified.
            extents = find_extent_addends(image, site, span)
            if not extents:
                problems.append(
                    f"{site:#010x}: parametric site states no `addiu 0x140/0xF0`, so the retail screen "
                    f"extent is unverified"
                )
        calls = image.call_sites(site)
        if calls != EXPECTED_CALL_SITES[site]:
            problems.append(
                f"{site:#010x}: {calls} call site(s), census expected {EXPECTED_CALL_SITES[site]}"
            )
        print(
            f"[cull] {site:#010x} window addend {window.addend_x:#x}/{window.addend_y:#x} "
            f"bound {window.bound_x:#x}/{window.bound_y:#x}  {calls:3d} call site(s)"
            + (f"  [{'; '.join(bounds)}]" if bounds else "")
            + (f"  [register-form bound: {', '.join(find_extent_addends(image, site, span))}]"
               if window.parametric else "")
            + (f"  +{len(addends)} addend site(s)" if addends else "")
        )

    for site, expected in sorted(OUT_OF_SCOPE_CALL_SITES.items()):
        calls = image.call_sites(site)
        state = "as reported" if calls == expected else f"MISMATCH (expected {expected})"
        if calls != expected:
            problems.append(f"{site:#010x}: {calls} call site(s), {state}")
        print(f"[cull] {site:#010x} out of scope (intro effect AABB), {calls} call site(s), {state}")

    # The struct offsets, read out of the two bodies rather than from the decomp's struct comments.
    layout_checks = (
        (0x8002B28C, BASE_BACKGROUND_OFFSET, "is_on_screen reads BaseObj.bg_offset at +0x14"),
        (0x800D46F8, QUAD_BACKGROUND_OFFSET, "quad_is_on_screen reads QuadObj.bg_offset at +0x37"),
        (0x8002B29C, X_INTEGER, "is_on_screen reads BaseObj x integer at +0x0A"),
        (0x8002B2A0, Y_INTEGER, "is_on_screen reads BaseObj y integer at +0x0E"),
        (0x800D470C, X_INTEGER, "quad_is_on_screen reads QuadObj x integer at +0x0A"),
        (0x800D4714, Y_INTEGER, "quad_is_on_screen reads QuadObj y integer at +0x0E"),
    )
    for address, expected, description in layout_checks:
        actual = image.uimm(address)
        status = "ok" if actual == expected else "MISMATCH"
        if actual != expected:
            problems.append(f"{description}: {address:#010x} carries {actual:#x}")
        print(f"[cull] {address:#010x} offset {actual:#04x} {status}: {description}")

    # The camera address ARITHMETIC, not just an offset field: `lui $1,0x8014` at 0x8002B2C4 plus the
    # `lhu` offset 0x19BA must resolve to kCameraLayersAddress + kCameraScrollX, and the y counterpart
    # to + kCameraScrollY. A wrong stride or a wrong base fails here even when every offset field is
    # individually plausible.
    for lui_at, load_at, field, description in (
        (0x8002B2C4, 0x8002B2CC, CAMERA_SCROLL_X, "layer-0 scroll x"),
        (0x8002B2D4, 0x8002B2DC, CAMERA_SCROLL_Y, "layer-0 scroll y"),
    ):
        lui = image.word(lui_at)
        high = (lui & 0xFFFF) << 16 if (lui >> 26) == 0x0F else None
        resolved = None if high is None else high + image.uimm(load_at)
        expected = CAMERA_LAYERS + field
        status = "ok" if resolved == expected else "MISMATCH"
        if resolved != expected:
            problems.append(
                f"{description}: lui at {lui_at:#010x} + offset at {load_at:#010x} resolves to "
                f"{resolved if resolved is None else hex(resolved)}, expected {expected:#x}"
            )
        print(
            f"[cull] {description}: {lui_at:#010x} lui + {load_at:#010x} offset resolves to "
            f"{'none' if resolved is None else hex(resolved)} {status} (expected {expected:#x})"
        )

    # The on_screen byte, at +3 in BOTH layouts: the two bodies' `sb` sites.
    for address, description in (
        (0x8002B298, "is_on_screen clears BaseObj.on_screen at +0x03"),
        (0x8002B30C, "is_on_screen sets BaseObj.on_screen at +0x03"),
        (0x800D4704, "quad_is_on_screen clears QuadObj.on_screen at +0x03"),
        (0x800D493C, "quad_is_on_screen sets QuadObj.on_screen at +0x03"),
    ):
        actual = image.uimm(address)
        status = "ok" if actual == ON_SCREEN else "MISMATCH"
        if actual != ON_SCREEN:
            problems.append(f"{description}: {address:#010x} carries {actual:#x}")
        print(f"[cull] {address:#010x} offset {actual:#04x} {status}: {description}")

    for index, (x, y) in enumerate(QUAD_CORNERS):
        for offset in (x, y):
            matches = [
                probe
                for probe in range(0x800D46F4, 0x800D46F4 + 0x260, 4)
                if (image.word(probe) >> 26) == 0x25 and (image.word(probe) & 0xFFFF) == offset
            ]
            if not matches:
                problems.append(f"quad corner {index}: no lhu of offset {offset:#x} in the body")
        print(f"[cull] quad corner {index}: x {x:#04x} / y {y:#04x} read by lhu in the body")

    header_problems = check_owner_header()
    problems.extend(header_problems)
    print(
        f"[cull] owner header {OWNER_HEADER.relative_to(ROOT)}: "
        f"{'agrees with the image' if not header_problems else f'{len(header_problems)} disagreement(s)'}"
    )

    total = sum(EXPECTED_CALL_SITES.values())
    print(f"[cull] census: {total} call sites across {len(EXPECTED_CALL_SITES)} registered owners, "
          f"{sum(OUT_OF_SCOPE_CALL_SITES.values())} on the two reported out-of-scope owners")
    return not problems, problems


def selftest(image: Image) -> bool:
    """Prove the gate can fail, on each of the three things it asserts.

    Each case mutates ONE expected value and requires the corresponding check to notice. A gate that
    only ever passes is indistinguishable from a gate that cannot fail.
    """
    ok = True

    # 1. A window BOUND, searched on the bound alone so the addends cannot satisfy the query.
    original = OWNERS[0x8002B288]
    mutated = dataclasses.replace(original, bound_x=original.bound_x - 1, bound_y=original.bound_y - 1)
    span = SITE_SPANS.get(0x8002B288, 0x100)
    if find_window_instructions(image, 0x8002B288, mutated, span, want="bound"):
        print("[cull-selftest] SURVIVED: a mutated window bound was still found in the image")
        ok = False
    else:
        print(f"[cull-selftest] caught a mutated bound at 0x8002B288 "
              f"({mutated.bound_x:#x}/{mutated.bound_y:#x} vs {original.bound_x:#x}/{original.bound_y:#x})")

    # 1b. And the control: the UNMUTATED bound must be found, or the case above proves nothing.
    if not find_window_instructions(image, 0x8002B288, original, span, want="bound"):
        print("[cull-selftest] FAILED: the unmutated bound is not in the image either")
        ok = False
    else:
        print("[cull-selftest] bound control: the unmutated bound is present in the image")

    # 2. The call-site census. A wrong expectation must be detectable, and a correct one must not be.
    actual = image.call_sites(0x8002B288)
    if actual != EXPECTED_CALL_SITES[0x8002B288]:
        print(f"[cull-selftest] FAILED: census reads {actual}, expected {EXPECTED_CALL_SITES[0x8002B288]}")
        ok = False
    else:
        print(f"[cull-selftest] census control: {actual} call sites at 0x8002B288, as expected")

    # 3. The owner-header binding. A constant the image does not carry must be reported.
    saved = OWNER_HEADER.read_text()
    try:
        ON_SCREEN_SAVED = check_owner_header.__globals__["ON_SCREEN"]
        check_owner_header.__globals__["ON_SCREEN"] = ON_SCREEN + 1
        problems = check_owner_header()
        if not any("kOnScreenOffset" in problem for problem in problems):
            print("[cull-selftest] SURVIVED: a wrong kOnScreenOffset expectation went unreported")
            ok = False
        else:
            print("[cull-selftest] caught a mutated owner-header expectation: "
                  + next(p for p in problems if "kOnScreenOffset" in p))
        check_owner_header.__globals__["ON_SCREEN"] = ON_SCREEN_SAVED
    finally:
        if not OWNER_HEADER.exists():  # pragma: no cover - the header is a tracked file
            OWNER_HEADER.write_text(saved)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--check", action="store_true", help="verify the owner against the image")
    parser.add_argument("--selftest", action="store_true", help="prove the gate can fail")
    args = parser.parse_args()

    if not args.check and not args.selftest:
        parser.error("choose --check and/or --selftest")

    failed = False
    if args.selftest:
        if not args.exe.exists():
            print(f"[cull-selftest] no executable at {args.exe}", file=sys.stderr)
            return 2
        failed |= not selftest(Image(args.exe))
    if args.check:
        ok, problems = run_check(args.exe)
        for problem in problems:
            print(f"[cull] FAIL {problem}", file=sys.stderr)
        if not ok:
            print(f"[cull] {len(problems)} problem(s)", file=sys.stderr)
        else:
            print("[cull] ok")
        failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
