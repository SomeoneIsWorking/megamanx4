#!/usr/bin/env python3
"""Measure when SLUS_005.61's STR movies actually complete, and what the picture is afterwards.

The STR movie path was previously reported as never completing. It does. The reason it looked that
way is a MEASUREMENT HORIZON, not a defect: the entry-one movie needs display field 974 (about
16.2 s at 60 Hz) and the indexed movie that follows needs field 13153, so every run of 30-400
fields necessarily ends mid-movie with the completion owner 0x80018E50 unentered and
`cd.stream_active` still set. This probe prints the two field numbers with their denominators, so
the claim is checkable instead of remembered.

WHAT IT MEASURES, per host field:
  * `0x80018E50` entries (`x4::movie_cleanup::run`) with the guest return address that reached them,
    which distinguishes the entry-one driver (ra 0x800184C4) from the indexed one (ra 0x800181DC);
  * `movieCleanup.completedFields()`, which is 7 exactly when the transaction's three VSync fences
    all ran, i.e. the teardown finished rather than merely started;
  * `cd.stream_active` and the guest field counter 0x80141BD8, which is FROZEN at 7 by contract
    while `movieOwnsPicture` is true and therefore proves the gameplay prefix resumed;
  * `0x801395E8` / `0x80139634` / the frame mirror 0x801441C0, the three words the investigation
    that produced this probe turned on.

It also reports the render width the product settled on, read from the run's own [wide] change log
(printed on change only, so its absence after the last value IS the steady state).

Usage:
    python tools/probe_str_loop.py --fields 1400          # first movie only (about 2 min under gdb)
    python tools/probe_str_loop.py --fields 20000         # both movies (about 25 min under gdb)
    python tools/probe_str_loop.py --fields 20000 --no-run   # print the gdb script and stop

The product is launched headless, silent and unpaced, and the probe refuses to start if another
megamanx4_port is already running: two product instances must never share this machine.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
DEFAULT_BINARY = ROOT / "build/bin/megamanx4_port"
SCRATCH = ROOT / "scratch/strloop"

# Guest facts this probe reads, all pinned by tools/verify_str_completion.py.
COLOUR_DEPTH_24 = 0x801395E8
COLOUR_DEPTH = 0x801395E4
MDEC_OUTPUT_OUTSTANDING = 0x80139634
FRAME_NUMBER_MIRROR = 0x801441C0
GUEST_FIELD_COUNTER = 0x80141BD8
# The two drivers' completion call sites, so an entry is attributable to the movie that made it.
ENTRY_ONE_COMPLETION_RETURN = 0x800184C4
INDEXED_COMPLETION_RETURN = 0x800181DC
CLEANUP_TOTAL_FIELDS = 7

GDB_SCRIPT = """set pagination off
set confirm off
set debuginfod enabled off
set $fld = 0
set $ncl = 0
break x4::frame::X4FrameDriver::stepFrame
commands
  silent
  set $fld = $fld + 1
  set $c = (Core *)$rsi
  set $ctx = (x4::X4Context *)$c->gameCtx
  if $fld % 500 == 0
    printf "PROBE fld=%d active=%d pending=%d done=%u fldCnt=%08x mirror=%08x c24=%08x cdepth=%08x mdec=%08x\\n", $fld, $c->game->cd.stream_active, (int)$ctx->movieCleanup.pending(), $ctx->movieCleanup.completedFields(), $c->mem_r32(0x80141BD8), $c->mem_r32(0x801441C0), $c->mem_r32(0x801395E8), $c->mem_r32(0x801395E4), $c->mem_r32(0x80139634)
  end
  if $fld > {fields}
    printf "PROBE summary fields=%d cleanupEntries=%d\\n", $fld-1, $ncl
    quit
  end
  continue
end
break x4::movie_cleanup::run
commands
  silent
  set $ncl = $ncl + 1
  set $c2 = (Core *)$rdi
  printf "PROBE cleanup entry=%d fld=%d ra=0x%08x activeBefore=%d\\n", $ncl, $fld, $c2->r[31], $c2->game->cd.stream_active
  continue
end
run
"""


class ProbeError(RuntimeError):
    pass


def running_instances() -> list[str]:
    listing = subprocess.run(
        ["ps", "-eo", "pid,args"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [line for line in listing if "megamanx4_port" in line and "ps -eo" not in line]


def parse_probe(text: str) -> tuple[list[dict[str, str]], list[dict[str, str]], int | None]:
    samples: list[dict[str, str]] = []
    cleanups: list[dict[str, str]] = []
    fields: int | None = None
    for line in text.splitlines():
        if not line.startswith("PROBE "):
            continue
        body = line[len("PROBE ") :]
        tokens = body.split()
        if body.startswith("cleanup "):
            cleanups.append(dict(token.split("=", 1) for token in tokens[1:]))
        elif body.startswith("summary "):
            fields = int(dict(token.split("=", 1) for token in tokens[1:])["fields"])
        else:
            samples.append(dict(token.split("=", 1) for token in tokens))
    return samples, cleanups, fields


def render_width_tail(log: Path) -> list[str]:
    """Every [wide] line, in order. The product prints on CHANGE, so the last one is the steady state."""
    if not log.is_file():
        return []
    return [
        line.split("] ", 1)[-1]
        for line in log.read_text(errors="replace").splitlines()
        if "[wide]" in line
    ]


def driver_for(return_address: str) -> str:
    """Which movie driver reached the completion owner, from the guest's own return address."""
    address = return_address.lower().removeprefix("0x")
    if address == f"{INDEXED_COMPLETION_RETURN:08x}":
        return "indexed movie driver 0x80018000"
    if address == f"{ENTRY_ONE_COMPLETION_RETURN:08x}":
        return "entry-one movie driver 0x800182E8"
    return f"UNATTRIBUTED (0x{address} is neither driver's completion call site)"


def report(samples: list[dict[str, str]], cleanups: list[dict[str, str]], fields: int | None, wide: list[str]) -> None:
    print(f"fields measured: {fields if fields is not None else 'unknown (probe did not reach its horizon)'}")
    # x4::movie_cleanup::run has 3 inline call sites, so one logical entry produces a PAIR of
    # breakpoint hits. Report both numbers rather than letting a reader assume hits == entries.
    distinct = list(dict.fromkeys((entry["fld"], entry["ra"]) for entry in cleanups))
    print(
        f"0x80018E50: {len(cleanups)} breakpoint hit(s) -> {len(distinct)} logical completion "
        "entr(y/ies) (x4::movie_cleanup::run has 3 inline call sites, so hits come in pairs)"
    )
    for field, return_address in distinct:
        before = next(e["activeBefore"] for e in cleanups if e["fld"] == field and e["ra"] == return_address)
        print(
            f"  completion at display field {field:>6}  ra=0x{int(return_address, 16):08X} -> "
            f"{driver_for(return_address)}; cd.stream_active before = {before}"
        )
    if not distinct:
        print("  NONE: the horizon was too short to reach the completion owner, which is the whole "
              "point of this probe — a run shorter than one movie cannot show it.")
    if samples:
        print("\nper-field samples (every 500):")
        header = f"  {'field':>6} {'active':>6} {'pending':>7} {'done':>4} {'fldCnt':>8} {'mirror':>8} {'0x395E8':>8} {'0x395E4':>8} {'0x39634':>8}"
        print(header)
        for sample in samples:
            print(
                f"  {sample['fld']:>6} {sample['active']:>6} {sample['pending']:>7} {sample['done']:>4} "
                f"{sample['fldCnt']:>8} {sample['mirror']:>8} {sample['c24']:>8} {sample['cdepth']:>8} {sample['mdec']:>8}"
            )
    if wide:
        print("\n[wide] change log (printed on change only, so the last line IS the steady state):")
        for line in wide:
            print(f"  {line}")
    print(
        f"\nnotes: 0x{COLOUR_DEPTH_24:08X}/0x{COLOUR_DEPTH:08X} are the STR colour depth and never "
        f"change; 0x{MDEC_OUTPUT_OUTSTANDING:08X} is the MDEC-output-outstanding flag the guest spins "
        f"on inside 0x80018EEC; 0x{FRAME_NUMBER_MIRROR:08X} counts decoded STR frames; "
        f"0x{GUEST_FIELD_COUNTER:08X} is the guest's own field counter, frozen at 7 by contract while a "
        f"movie owns the picture, so it leaving 7 is the gameplay prefix resuming. A cleanup entry with "
        f"done={CLEANUP_TOTAL_FIELDS} means the transaction's three VSync fences all ran."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fields", type=int, default=1400, help="host fields to measure (default 1400)")
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--no-run", action="store_true", help="print the gdb script and stop")
    args = parser.parse_args()

    script = GDB_SCRIPT.format(fields=args.fields)
    if args.no_run:
        print(script)
        return 0

    for required in (args.binary, args.exe):
        if not required.is_file():
            raise ProbeError(f"{required} is missing; build the port and provision the executable first")
    if shutil.which("gdb") is None:
        raise ProbeError("gdb is required for this probe (it reads the Core the product is driving)")
    others = running_instances()
    if others:
        raise ProbeError(
            "refusing to start a second product instance; these are already running:\n  "
            + "\n  ".join(others)
        )

    SCRATCH.mkdir(parents=True, exist_ok=True)
    out_path = SCRATCH / "probe_str_loop.out"
    log_path = SCRATCH / "probe_str_loop.log"
    # Inherit the caller's environment and OVERLAY the run's own settings. Replacing it outright
    # strips what the product legitimately reads (HOME for the config resolver, XDG_RUNTIME_DIR for
    # the headless SDL sink), and the run then exits 2 from the CLI instead of measuring anything.
    environment = dict(os.environ)
    environment.update(
        {
            "PSXPORT_HEADLESS": "1",
            "PSXPORT_NOAUDIO": "true",
            "PSXPORT_NOPACE": "true",
            "PSXPORT_NATIVE_FRAMES": str(args.fields + 50),
            "PSXPORT_LOG_FILE": str(log_path),
            "PSXPORT_WATCHDOG": "7200",
        }
    )
    with tempfile.NamedTemporaryFile("w", suffix=".gdb", delete=False) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        with out_path.open("w") as sink:
            completed = subprocess.run(
                [
                    "gdb",
                    "-q",
                    "-batch",
                    "-x",
                    str(script_path),
                    "--args",
                    str(args.binary),
                    str(args.exe),
                ],
                stdout=sink,
                stderr=subprocess.STDOUT,
                env=environment,
                check=False,
            )
    finally:
        script_path.unlink(missing_ok=True)

    samples, cleanups, fields = parse_probe(out_path.read_text(errors="replace"))
    if not samples and not cleanups:
        tail = out_path.read_text(errors="replace").splitlines()[-25:]
        raise ProbeError(
            f"the probe measured nothing (gdb exit {completed.returncode}). Probe output tail:\n  "
            + "\n  ".join(tail)
        )
    report(samples, cleanups, fields, render_width_tail(log_path))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
