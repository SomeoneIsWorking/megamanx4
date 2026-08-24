#!/usr/bin/env python3
"""Reject operational interpolation dependencies from MMX4's shipping source closure."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "game" / "core"


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Forbidden:
    label: str
    pattern: re.Pattern[str]


FORBIDDEN_INCLUDES = (
    Forbidden("interpolation header", re.compile(r'^\s*#\s*include\s*[<\"]fps60\.h[>\"]', re.MULTILINE)),
)
FORBIDDEN_CODE = (
    Forbidden("Fps60 product/type", re.compile(r"\bFps60\b")),
    Forbidden("Game::fps60 product", re.compile(r"(?:->|\.)fps60\b")),
    Forbidden("FPS60 macro", re.compile(r"\bFPS60_[A-Za-z0-9_]*\b")),
    Forbidden("legacy frame_commit", re.compile(r"\bframe_commit\s*\(")),
    Forbidden("temporal hook call", re.compile(r"(?:->|\.)fps60(?:Read|World|Bb|Temporal)[A-Za-z0-9_]*\s*\(")),
)
FORBIDDEN_LINK_SYMBOLS = (
    Forbidden("Fps60 implementation", re.compile(r"\bFps60(?:::|$)")),
    Forbidden("checked Fps60 accessor", re.compile(r"\bfps60\(Game&\)")),
    Forbidden("legacy temporal hook adapter", re.compile(r"\bgame_fps60_[A-Za-z0-9_]*")),
    Forbidden("temporal GPU pass", re.compile(r"\bgpu_fps60_[A-Za-z0-9_]*")),
)


def code_without_comments_or_literals(source: str) -> str:
    """Preserve token boundaries while removing comments, strings and character literals."""

    token = re.compile(
        r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'",
        re.DOTALL,
    )
    return token.sub(lambda match: "\n" * match.group(0).count("\n") or " ", source)


def violations(name: str, source: str) -> list[str]:
    failures: list[str] = []
    for forbidden in FORBIDDEN_INCLUDES:
        if forbidden.pattern.search(source):
            failures.append(f"{name}: {forbidden.label}")
    code = code_without_comments_or_literals(source)
    for forbidden in FORBIDDEN_CODE:
        if forbidden.pattern.search(code):
            failures.append(f"{name}: {forbidden.label}")
    return failures


def shipping_sources() -> list[Path]:
    paths = sorted((*SOURCE_ROOT.glob("*.cpp"), *SOURCE_ROOT.glob("*.h")))
    if not paths:
        raise VerificationError(f"no shipping sources under {SOURCE_ROOT}")
    return paths


def verify() -> list[Path]:
    paths = shipping_sources()
    failures: list[str] = []
    for path in paths:
        failures.extend(violations(path.relative_to(ROOT).as_posix(), path.read_text()))
    if failures:
        raise VerificationError("operational interpolation dependency found: " + "; ".join(failures))
    return paths


def linked_violations(symbols: str) -> list[str]:
    return [forbidden.label for forbidden in FORBIDDEN_LINK_SYMBOLS if forbidden.pattern.search(symbols)]


def verify_binary(path: Path) -> int:
    if not path.is_file():
        raise VerificationError(f"shipping binary is absent: {path}")
    result = subprocess.run(["nm", "-C", str(path)], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise VerificationError(f"nm failed for {path}: {result.stderr.strip()}")
    failures = linked_violations(result.stdout)
    if failures:
        raise VerificationError("shipping binary contains interpolation products: " + "; ".join(failures))
    return len(result.stdout.splitlines())


def selftest() -> list[str]:
    positive = "c->game->presentation.commit(c, 1); // Fps60 is intentionally absent\n"
    if violations("positive.cpp", positive):
        raise VerificationError("neutral presentation positive control was rejected")

    mutations = {
        "fps60 include": '#include "fps60.h"\n',
        "fps60 product": "auto product = std::make_unique<Fps60>(game);\n",
        "game fps60 call": "c->game->fps60.frame_commit(c, 1);\n",
        "fps60 macro": "int mode = FPS60_INTERPOLATE;\n",
        "temporal hook call": "hooks->fps60TemporalRotate(c);\n",
    }
    results = ["PASS positive neutral presentation"]
    for name, mutation in mutations.items():
        if not violations(f"negative-{name}.cpp", positive + mutation):
            raise VerificationError(f"negative {name} mutation was accepted")
        results.append(f"PASS negative {name}")
    linked_mutations = {
        "Fps60 method": "0000 T Fps60::present()\n",
        "checked accessor": "0000 T fps60(Game&)\n",
        "hook adapter": "0000 T game_fps60_world_pass()\n",
        "GPU pass": "0000 T gpu_fps60_present_pass()\n",
    }
    if linked_violations("0000 T FramePresenter::commit(TemporalFramePresentation*)\n"):
        raise VerificationError("neutral abstract presentation seam was rejected by the link gate")
    results.append("PASS positive neutral link seam")
    for name, mutation in linked_mutations.items():
        if not linked_violations(mutation):
            raise VerificationError(f"negative linked {name} mutation was accepted")
        results.append(f"PASS negative linked {name}")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="scan shipping game/core sources")
    parser.add_argument("--binary", type=Path, help="scan the linked shipping binary with nm -C")
    parser.add_argument("--selftest", action="store_true", help="run positive and mutation controls")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.check and not args.binary and not args.selftest:
        raise VerificationError("choose --check, --binary and/or --selftest")
    if args.check:
        paths = verify()
        print(f"PASS — {len(paths)} shipping sources have no operational interpolation dependency")
    if args.binary:
        symbols = verify_binary(args.binary)
        print(f"PASS — shipping binary has no Fps60 implementation across {symbols} linked symbols")
    if args.selftest:
        results = selftest()
        print("\n".join(results))
        print(f"PASS — selftest {len(results)}/{len(results)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
