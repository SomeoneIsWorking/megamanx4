#!/usr/bin/env python3
"""Gate RE-10's first matching-decomp-seeded native body against retail MMX4.

The selected body is the title's state-0 white-logo quad initializer at 0x800D6F94. This verifier
reuses the title-composition instrument for the front-end -> quad-update path, then proves the
state-0 dispatch entry and all 49 retail instructions of the leaf body. It also diffs every address
and field offset consumed by the shipping native implementation back to that measurement and checks
that the retained-super ownership triple is wired.

This is the static/hermetic half of the ownership gate. It cannot prove that the override installed
or ran. RE-10 remains in progress until a serialized live run prints mirror-verify success for
0x800D6F94, and the same run must be discriminated by a deliberate native-body perturbation.
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
sys.path.insert(0, str(ROOT / "external/psxport/tools/recomp"))

import psexe
import verify_title_composition

DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"
HEADER = ROOT / "game/core/title_quad.h"
SOURCE = ROOT / "game/core/title_quad.cpp"
RUNTIME = ROOT / "game/core/x4_runtime.cpp"
DECOMP_SOURCE = ROOT / "external/mmx4/src/main/title_quad.c"
CONFIG_DOC = ROOT / "docs/config.md"

INITIALIZER = 0x800D6F94
INITIALIZER_END = 0x800D7058
TITLE_QUAD_UPDATE = 0x800D76F8
TITLE_STATE_DISPATCH = 0x8010FDD0
VERTEX_PRESETS = 0x8010FCCC
INITIAL_COLOR = 0x8010FD94

# Exact retail body [0x800D6F94, 0x800D7058): 49 instructions. A change is not accepted as a new
# implementation; it means this source supply no longer describes the owned executable.
EXPECTED_BODY = (
    0x2402FFFF,
    0xA0820037,
    0x80820002,
    0x24030001,
    0xA0830042,
    0x90830000,
    0x3C058011,
    0x24A5FCCC,
    0xA480000A,
    0xA480000E,
    0x00021100,
    0x00451021,
    0x34630080,
    0xA0830000,
    0x94430000,
    0x24420002,
    0xA4830016,
    0x94430000,
    0x24420002,
    0xA483001A,
    0x94430000,
    0x24420002,
    0xA483001E,
    0x94430000,
    0x24420002,
    0xA4830022,
    0x94430000,
    0x24420002,
    0xA4830026,
    0x94430000,
    0x24420002,
    0xA483002A,
    0x94430000,
    0x00000000,
    0xA483002E,
    0x94420002,
    0x00000000,
    0xA4820032,
    0x3C038011,
    0x9463FD94,
    0x24020010,
    0xA0820036,
    0x24020003,
    0xA0820004,
    0x24020014,
    0xA4820038,
    0xA0800043,
    0x03E00008,
    0xA4830034,
)

SHIPPED_CONSTANTS = {
    "kInitializeWhiteLogoQuad": INITIALIZER,
    "kTitleQuadUpdate": TITLE_QUAD_UPDATE,
    "kTitleStateDispatch": TITLE_STATE_DISPATCH,
    "kVertexPresets": VERTEX_PRESETS,
    "kInitialColor": INITIAL_COLOR,
    "kActive": 0x00,
    "kVariant": 0x02,
    "kState": 0x04,
    "kXPositionInteger": 0x0A,
    "kYPositionInteger": 0x0E,
    "kFirstVertexCoordinate": 0x16,
    "kColor": 0x34,
    "kPrimitiveCode": 0x36,
    "kBackgroundOffset": 0x37,
    "kTimer": 0x38,
    "kEnabled": 0x42,
    "kPhase": 0x43,
}


class Refused(RuntimeError):
    """The requested evidence could not be produced."""


def load_image(path: Path) -> psexe.PsxExe:
    if not path.is_file():
        raise Refused(f"{path} does not exist; inspected 0 retail instructions")
    try:
        return psexe.load(str(path))
    except (OSError, ValueError, struct.error) as exc:
        raise Refused(
            f"{path} is not a loadable PS-X EXE; inspected 0 instructions: {exc}"
        ) from exc


def body_words(image: psexe.PsxExe) -> tuple[int, ...]:
    return tuple(
        image.word(address) for address in range(INITIALIZER, INITIALIZER_END, 4)
    )


def verify_retail(image: psexe.PsxExe) -> list[str]:
    try:
        verify_title_composition.verify(image)
    except verify_title_composition.Refused as exc:
        raise Refused(f"upstream title-composition ownership failed: {exc}") from exc

    actual_body = body_words(image)
    if actual_body != EXPECTED_BODY:
        mismatch = next(
            index
            for index, (actual, expected) in enumerate(zip(actual_body, EXPECTED_BODY))
            if actual != expected
        )
        address = INITIALIZER + mismatch * 4
        raise Refused(
            f"initializer body mismatch at 0x{address:08X}: 0x{actual_body[mismatch]:08X}, "
            f"want 0x{EXPECTED_BODY[mismatch]:08X}; checked {len(actual_body)} instructions"
        )

    state_zero = image.word(TITLE_STATE_DISPATCH)
    if state_zero != INITIALIZER:
        raise Refused(
            f"title state-0 dispatch at 0x{TITLE_STATE_DISPATCH:08X} is 0x{state_zero:08X}, "
            f"want 0x{INITIALIZER:08X}"
        )

    return [
        "reused the complete title-composition gate through title quad update 0x800D76F8",
        "title state 0 dispatches 0x800D6F94",
        f"matched all {len(EXPECTED_BODY)} retail instructions in the selected leaf body",
        "derived vertex presets 0x8010FCCC, initial color 0x8010FD94, and all 17 shipped facts",
    ]


def parse_constant(text: str, name: str) -> int:
    match = re.search(rf"\b{name}\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)u?", text)
    if not match:
        raise Refused(
            f"{HEADER}: did not find {name}; cannot compare shipping title facts"
        )
    return int(match.group(1), 0)


def verify_source(
    header: str, source: str, runtime: str, decomp: str, config_doc: str
) -> None:
    mismatches = []
    for name, expected in SHIPPED_CONSTANTS.items():
        actual = parse_constant(header, name)
        if actual != expected:
            mismatches.append(f"{name}=0x{actual:X}, want 0x{expected:X}")

    required_source = (
        "void initializeWhiteLogoQuad(Core *core)",
        "overrides::install(kInitializeWhiteLogoQuad",
        "gen_func_800D6F94",
        "shard_set_override",
    )
    mismatches.extend(
        f"missing source token {token!r}"
        for token in required_source
        if token not in source
    )
    if "title_quad::registerOverride();" not in runtime:
        mismatches.append("X4Runtime does not install title_quad::registerOverride")
    for diagnostic in (
        "PSXPORT_MIRROR_VERIFY=0x800D6F94",
        "PSXPORT_THUNK_FORCE_GEN=0x800D6F94",
    ):
        if diagnostic not in config_doc:
            mismatches.append(f"missing title-sprite A/B diagnostic {diagnostic!r}")

    body_start = decomp.find("void func_800D6F94(struct QuadObj* entity)")
    body_end = decomp.find("// TitleUpdate2 state 1", body_start)
    if body_start < 0 or body_end < 0:
        mismatches.append("matching decomp has no bounded C body for func_800D6F94")
    else:
        selected = decomp[body_start:body_end]
        if "INCLUDE_ASM" in selected:
            mismatches.append(
                "matching decomp supplies func_800D6F94 as assembly, not a C body"
            )

    if mismatches:
        raise Refused("shipping/source mismatch: " + "; ".join(mismatches))


def read_sources() -> tuple[str, str, str, str, str]:
    try:
        return (
            HEADER.read_text(),
            SOURCE.read_text(),
            RUNTIME.read_text(),
            DECOMP_SOURCE.read_text(),
            CONFIG_DOC.read_text(),
        )
    except OSError as exc:
        raise Refused(f"cannot read ownership source: {exc}") from exc


def mutate(image: psexe.PsxExe, address: int, word: int) -> psexe.PsxExe:
    changed = bytearray(image.text)
    struct.pack_into("<I", changed, address - image.load, word)
    return dataclasses.replace(image, text=bytes(changed))


def selftest(image: psexe.PsxExe, sources: tuple[str, str, str, str, str]) -> None:
    cases = 0
    verify_retail(image)
    verify_source(*sources)
    print("[re-title-quad:selftest] PASS retail + shipping source accepted")
    cases += 1

    for label, fixture, diagnostic in (
        ("changed body instruction", mutate(image, INITIALIZER, 0), "body mismatch"),
        (
            "changed state-0 dispatch",
            mutate(image, TITLE_STATE_DISPATCH, 0),
            "title quad state-0 owner",
        ),
    ):
        try:
            verify_retail(fixture)
            raise Refused(f"selftest {label}: mutation was accepted")
        except Refused as exc:
            if diagnostic not in str(exc):
                raise Refused(f"selftest {label}: wrong diagnostic: {exc}") from exc
        print(f"[re-title-quad:selftest] PASS {label} rejected")
        cases += 1

    changed_header = sources[0].replace(
        "kVertexPresets = 0x8010FCCCu", "kVertexPresets = 0x8010FCD0u"
    )
    try:
        verify_source(changed_header, *sources[1:])
        raise Refused("selftest changed shipping constant: mutation was accepted")
    except Refused as exc:
        if "kVertexPresets" not in str(exc):
            raise Refused(
                f"selftest changed shipping constant: wrong diagnostic: {exc}"
            ) from exc
    print("[re-title-quad:selftest] PASS changed shipping constant rejected")
    cases += 1

    changed_config = sources[4].replace(
        "PSXPORT_THUNK_FORCE_GEN=0x800D6F94",
        "PSXPORT_THUNK_FORCE_GEN=0x800D6F98",
    )
    try:
        verify_source(*sources[:4], changed_config)
        raise Refused("selftest changed generated A/B address: mutation was accepted")
    except Refused as exc:
        if "A/B diagnostic" not in str(exc):
            raise Refused(
                f"selftest changed generated A/B address: wrong diagnostic: {exc}"
            ) from exc
    print("[re-title-quad:selftest] PASS changed generated A/B address rejected")
    cases += 1
    print(f"[re-title-quad:selftest] PASS {cases}/{cases} cases")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument(
        "--check", action="store_true", help="check retail and shipping ownership facts"
    )
    parser.add_argument(
        "--selftest", action="store_true", help="prove the gate accepts and rejects"
    )
    args = parser.parse_args()

    try:
        if hashlib.sha1(args.exe.read_bytes()).hexdigest() != EXPECTED_SHA1:
            raise Refused(
                f"{args.exe} is not retail SLUS_005.61 (whole-file SHA-1 mismatch)"
            )
        image = load_image(args.exe)
        sources = read_sources()
        if args.check or not args.selftest:
            for line in verify_retail(image):
                print(f"[re-title-quad] PASS {line}")
            verify_source(*sources)
            print(
                "[re-title-quad] PASS shipping native body and retained-super ownership triple are wired"
            )
            print(
                "[re-title-quad] BLIND SPOT: static/hermetic evidence cannot prove override reach or "
                "native-vs-substrate equality; serialized live mirror verification remains required"
            )
        if args.selftest:
            selftest(image, sources)
        return 0
    except (OSError, Refused) as exc:
        print(f"[re-title-quad] REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
