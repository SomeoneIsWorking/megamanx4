#!/usr/bin/env python3
"""Prove the shipping X4 seed configuration bootstraps from the retail executable.

This is deliberately an integration verifier over psxport's real emitter, not a second function
finder.  The framework owns binary discovery; this tool supplies the retail executable and this
repo's seed file, then checks the generated interface that this port consumes.  An empty explicit
seed list is valid here because emit.py always starts from the PS-X EXE entry point and its binary
pointer/table scans before following direct ``jal`` edges.

``--selftest`` proves both answers through the same subprocess path: the shipping configuration must
emit a resident substrate containing the measured crt0 and game-main functions, while an explicit
seed outside the executable text must be refused by emit.py.  Generated evidence lives in a scoped
temporary directory under ``scratch/raw`` and is removed automatically.

Blind spot: static discovery cannot see every runtime-computed target.  A successful result proves a
real initial substrate can be emitted; only a running port can expose further indirect-only entries
as ``[recomp-MISS]``.  Those future addresses remain empirical additions to recomp_seeds.json.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "scratch" / "bin" / "megamanx4" / "SLUS_005.61"
EMITTER = ROOT / "external" / "psxport" / "tools" / "recomp" / "emit.py"
SEEDS = ROOT / "game" / "recomp_seeds.json"
SCRATCH = ROOT / "scratch" / "raw"
TARGET_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"
GAME_MAIN = 0x80012024
CRT0 = 0x800DAE8C
COUNT_RE = re.compile(
    r"\[func\] functions: (?P<seeds>\d+) seeds -> (?P<functions>\d+) recompiled"
)


class Refused(RuntimeError):
    """The requested evidence could not be produced."""


@dataclass(frozen=True)
class Measurement:
    seed_count: int
    function_count: int
    version: str
    output: str


def require_retail_exe(path: Path) -> None:
    try:
        digest = hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Refused(f"cannot read retail executable {path}: {exc}") from exc
    if digest != TARGET_SHA1:
        raise Refused(
            f"{path} SHA-1 is {digest}, expected retail SLUS_005.61 {TARGET_SHA1}"
        )


def invoke_emitter(
    exe: Path, seeds: Path, output_dir: Path
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PSXPORT_SHARDS"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop("PSXPORT_USE_GHIDRA", None)
    try:
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(EMITTER),
                str(exe),
                str(output_dir / "main.c"),
                "--seeds",
                str(seeds),
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise Refused(f"could not invoke {EMITTER}: {exc}") from exc


def measure(exe: Path, seeds: Path, output_dir: Path) -> Measurement:
    result = invoke_emitter(exe, seeds, output_dir)
    if result.returncode != 0:
        raise Refused(
            f"emit.py rejected {seeds} with exit {result.returncode}:\n{result.stdout.rstrip()}"
        )

    count = COUNT_RE.search(result.stdout)
    if count is None:
        raise Refused("emit.py succeeded but printed no seed/function denominator")
    seed_count = int(count.group("seeds"))
    function_count = int(count.group("functions"))
    if seed_count <= 0 or function_count < seed_count:
        raise Refused(
            f"invalid discovery denominator: {seed_count} seeds -> {function_count} functions"
        )

    try:
        declarations = (output_dir / "rec_decls.h").read_text()
        manifest = (output_dir / "rec_sources.cmake").read_text()
        overlays = (output_dir / "overlay_table.c").read_text()
        version = (output_dir / ".recomp_version").read_text().strip()
    except OSError as exc:
        raise Refused(f"emit.py omitted a required generated interface: {exc}") from exc

    missing = [
        symbol
        for symbol in (
            f"void func_{GAME_MAIN:08X}(Core*);",
            f"void func_{CRT0:08X}(Core*);",
            "void main_dispatch(Core* c, uint32_t addr);",
            "void shard_set_override(uint32_t addr, OverrideFn fn);",
        )
        if symbol not in declarations
    ]
    if missing:
        raise Refused("generated declarations omit " + ", ".join(missing))
    for source in ("overlay_table.c", "shard_0.c", "shard_disp.c"):
        if source not in manifest:
            raise Refused(f"generated source manifest omits {source}")
    if "const int g_rec_overlay_count = 0;" not in overlays:
        raise Refused(
            "generated overlay table does not report the measured zero-overlay answer"
        )
    if not version:
        raise Refused("generated substrate has an empty recompiler version stamp")

    return Measurement(seed_count, function_count, version, result.stdout)


def check(exe: Path) -> Measurement:
    require_retail_exe(exe)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="recomp-bootstrap-", dir=SCRATCH
    ) as temporary:
        return measure(exe, SEEDS, Path(temporary))


def selftest(exe: Path) -> bool:
    positive = check(exe)
    print(
        "PASS positive: retail binary + shipping seeds emitted "
        f"{positive.seed_count} binary-rooted seeds -> {positive.function_count} functions; "
        f"crt0/gameMain present; 0 overlays; version {positive.version}"
    )

    with tempfile.TemporaryDirectory(
        prefix="recomp-refusal-", dir=SCRATCH
    ) as temporary:
        directory = Path(temporary)
        bad_seeds = directory / "outside-text.json"
        bad_seeds.write_text('{"main": ["0x90000000"]}\n')
        result = invoke_emitter(exe, bad_seeds, directory / "out")
        diagnostic = "seed(s) outside the module text"
        if result.returncode == 0 or diagnostic not in result.stdout:
            print(
                "FAIL negative: out-of-text seed was not refused with the emitter's bounded-text "
                f"diagnostic (exit {result.returncode})",
                file=sys.stderr,
            )
            return False
    print("PASS negative: an out-of-text explicit seed is refused before emission")
    print("SELFTEST 2/2")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    try:
        if args.selftest:
            return 0 if selftest(args.exe) else 1
        measurement = check(args.exe)
        print(
            "PASS: retail SLUS_005.61 emitted "
            f"{measurement.seed_count} binary-rooted seeds -> "
            f"{measurement.function_count} functions; crt0/gameMain present; 0 overlays; "
            f"version {measurement.version}"
        )
        return 0
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
