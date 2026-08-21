#!/usr/bin/env python3
"""Keep Mega Man X4's generated resident substrate aligned with its real inputs."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "scratch" / "bin" / "megamanx4" / "SLUS_005.61"
SEEDS = ROOT / "game" / "recomp_seeds.json"
GENERATED = ROOT / "generated"
HASH_FILE = GENERATED / ".recomp.hash"
VERSION_FILE = GENERATED / ".recomp_version"


class RecompError(RuntimeError):
    """The substrate cannot be proven current."""


def say(message: str) -> None:
    print(f"[ensure-recomp] {message}", file=sys.stderr)


def recompiler_sources(psxport_dir: Path) -> list[Path]:
    recomp = psxport_dir / "tools" / "recomp"
    return [recomp / name for name in ("emit.py", "decode.py", "psexe.py")]


def recomp_version(emitter: Path) -> str:
    match = re.search(
        r'^RECOMP_VERSION\s*=\s*"([^"]+)"', emitter.read_text(), re.MULTILINE
    )
    if not match:
        raise RecompError(f"could not read RECOMP_VERSION from {emitter}")
    return match.group(1)


def input_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        if not path.is_file():
            raise RecompError(f"required recomp input is absent: {path}")
        label = path.relative_to(ROOT) if path.is_relative_to(ROOT) else Path(path.name)
        digest.update(str(label).encode())
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def generated_complete() -> bool:
    manifest = GENERATED / "rec_sources.cmake"
    if not manifest.is_file():
        return False
    listed = re.findall(r"^\s*(\S+\.c)\s*$", manifest.read_text(), re.MULTILINE)
    required = [GENERATED / "rec_decls.h", GENERATED / "overlay_table.h"]
    return (
        bool(listed)
        and all(path.is_file() for path in required)
        and all((GENERATED / name).is_file() for name in listed)
    )


def ensure(psxport_dir: Path) -> None:
    sources = recompiler_sources(psxport_dir)
    version = recomp_version(sources[0])
    wanted = f"{version}:{input_hash([EXE, SEEDS, *sources])}"
    have = HASH_FILE.read_text().strip() if HASH_FILE.is_file() else ""
    stamp = VERSION_FILE.read_text().strip() if VERSION_FILE.is_file() else ""
    force = os.environ.get("PSXPORT_FORCE_RECOMP", "") not in ("", "0")

    if not force and have == wanted and stamp == version and generated_complete():
        say(f"recomp up to date (version {version}) — nothing to do")
        return

    reason = "forced" if force else "inputs or generated output changed"
    say(f"{reason} — emitting resident substrate (version {version})")
    GENERATED.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.setdefault("PSXPORT_SHARDS", "8")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(sources[0]),
            str(EXE),
            str(GENERATED / "main.c"),
            "--seeds",
            str(SEEDS),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
    )
    if result.returncode:
        raise RecompError("resident substrate emission failed")
    if not generated_complete():
        raise RecompError("emitter returned success but generated/ is incomplete")
    actual_stamp = VERSION_FILE.read_text().strip() if VERSION_FILE.is_file() else ""
    if actual_stamp != version:
        raise RecompError(
            f"emitter stamped version {actual_stamp!r}, expected {version!r}"
        )
    HASH_FILE.write_text(wanted + "\n")
    say(f"recomp current (version {version})")


def main() -> int:
    psxport = Path(
        os.environ.get("PSXPORT_DIR", ROOT / "external" / "psxport")
    ).resolve()
    try:
        ensure(psxport)
    except (OSError, RecompError) as exc:
        print(f"[ensure-recomp] error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
