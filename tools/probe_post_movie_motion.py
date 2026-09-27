#!/usr/bin/env python3
"""Measure whether the post-movie phase ANIMATES, and run the 4:3 / 16:9 widescreen pair.

WHY A TOOL. "The presented frame is not black" is the wrong discriminator for a stalled guest: the
post-movie clear colour is RGB(8,8,16), which is NOT (0,0,0), so a non-black count of 61.89% reads as
"something is on screen" for a picture that never changes. The measurement that separates a running
guest from a frozen one is FRAME-TO-FRAME DIFFERENCE between CONSECUTIVE presents, reported with its
denominator, next to the distinct-colour count of each frame.

IT LAUNCHES THE PRODUCT ITSELF, one leg at a time, in its own process, because
`PSXPORT_PRESENT_SINK=WxH` is process-wide: two legs at the same width in one process make the pair
tool refuse. It refuses to start if another `megamanx4_port` is already running — this machine has a
single product slot.

    tools/probe_post_movie_motion.py --at 15000:8              # 8 consecutive wide presents
    tools/probe_post_movie_motion.py --at 15000:8 --pair       # ... and the widescreen pair verdict
    tools/probe_post_movie_motion.py --at 13500:2,15000:2      # two windows, no pair

Output per frame: present index, sink size, non-black pixels / total, distinct RGB colours, and the
top colours with their share. Then, per consecutive pair: pixels that differ / total, and the mean
and max per-channel absolute difference over the pixels that differ. A guest that is not animating
scores 0 differing pixels on every pair; that is the number to look for.
"""

from __future__ import annotations

import argparse
import collections
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "external/psxport/tools/port"))
from present_geometry import Unreadable, read_image  # noqa: E402

DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
DEFAULT_BINARY = ROOT / "build/bin/megamanx4_port"
SCRATCH = ROOT / "scratch/motion"
SCREENSHOTS = ROOT / "scratch/screenshots"
PAIR_TOOL = ROOT / "external/psxport/tools/port/widescreen_pair.py"

# The two legs the pair tool needs. The narrow sink is 4:3 at the guest's own 320x240 aspect; the
# wide sink is the title's measured 428-wide projection letterboxed into 16:9. Both are process-wide
# and are therefore two separate runs, never two settings of one.
LEG_NARROW = ("0", "960x720")
LEG_WIDE = ("1", "1284x720")


class ProbeError(RuntimeError):
    pass


def running_instances() -> list[str]:
    listing = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True, check=True).stdout
    return [line for line in listing.splitlines() if "megamanx4_port" in line and "ps -eo" not in line]


def parse_windows(text: str) -> list[tuple[int, int]]:
    """Parse `start:count[,start:count]` into capture windows, refusing what cannot be measured.

    TWO DEFECTS FIXED HERE, both found by this file's own `--selftest` rather than by a run:

    1. The guard said one thing and the code did another. It tested `count < 1` while its own message
       said "a frame-to-frame difference needs 2", so `--at 15000:1` was ACCEPTED. A one-frame window
       captures a single picture and `pair_difference` then compares it to itself, reporting
       `0.0% changed` — a number indistinguishable from a real measurement of a still frame. That is
       the worst shape a diagnostic can have: it manufactures agreement. The guard is now `< 2`.
    2. The empty-input refusal was UNREACHABLE. `"".split(",")` yields `[""]`, so `int("")` raised
       `ValueError` before the `if not windows` check could run, and a caller passing no window got a
       traceback instead of the sentence telling it what to pass.

    The default for a bare `start` moves from 1 to 2 for the same reason as (1): one frame cannot
    support a frame-to-frame claim, so the default must not ask for one.
    """
    if not text.strip():
        raise ProbeError("no capture window given; pass --at start:count (count must be 2 or more)")
    windows: list[tuple[int, int]] = []
    for part in text.split(","):
        first, _, last = part.partition(":")
        if not first.strip() or (last and not last.strip()):
            raise ProbeError(f"window {part!r} is not `start` or `start:count`")
        try:
            start = int(first)
        except ValueError as error:
            raise ProbeError(f"window {part!r} has a non-numeric start") from error
        if last:
            try:
                count = int(last)
            except ValueError as error:
                raise ProbeError(f"window {part!r} has a non-numeric frame count") from error
        else:
            count = 2
        if count < 2:
            raise ProbeError(
                f"window {part!r} asks for {count} frame(s); a frame-to-frame difference needs 2, and "
                f"one frame would be compared to itself and reported as 0.0% changed"
            )
        if start < 0:
            raise ProbeError(f"window {part!r} starts before the first field")
        windows.append((start, count))
    return windows


def run_leg(label: str, widescreen: str, sink: str, frames: int, at: str, log: Path) -> None:
    environment = dict(os.environ)
    environment.update(
        {
            "PSXPORT_VK_HEADLESS": "1",
            "PSXPORT_NOAUDIO": "1",
            "PSXPORT_NOPACE": "1",
            "PSXPORT_X4_WIDESCREEN": widescreen,
            "PSXPORT_PRESENT_SINK": sink,
            "PSXPORT_NATIVE_FRAMES": str(frames),
            "PSXPORT_WATCHDOG": "3600",
            "PSXPORT_PRESENT_SHOT_AT": ",".join(at.split()),
            "PSXPORT_LOG_FILE": str(log),
        }
    )
    # `PSXPORT_LOG_FILE` APPENDS. A previous run's `[wide]` change lines therefore survive into this
    # one's tail, and because that announcement prints on CHANGE only, the "the last line is the
    # steady state" rule then reads a line from an EARLIER run. That is exactly the trap this tool
    # exists beside, and it produced a wrong 24-transition tail on its first use here. Delete first.
    log.unlink(missing_ok=True)
    completed = subprocess.run(
        [str(DEFAULT_BINARY), str(DEFAULT_EXE)],
        env=environment,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        raise ProbeError(f"{label} leg exited {completed.returncode}; see {log}")


def frame_stats(path: Path) -> dict:
    width, height, pixels = read_image(path)
    total = width * height
    counts = collections.Counter(
        pixels[index:index + 3].hex() for index in range(0, len(pixels), 3)
    )
    non_black = sum(count for colour, count in counts.items() if colour != "000000")
    return {
        "path": path,
        "w": width,
        "h": height,
        "total": total,
        "colours": len(counts),
        "non_black": non_black,
        "top": counts.most_common(4),
        "pixels": pixels,
    }


def pair_difference(first: dict, second: dict) -> dict:
    """Where and how much two frames differ.

    Returns the count of differing pixels, the mean per-channel |delta| over those, the worst single
    channel |delta|, and the bounding box of the differing pixels. The box matters: "0.4% of the frame
    changes" is a much weaker claim than "the 2,871 pixels that change are a 3-row band at
    y=236..238", because the second names what is moving.
    """
    a, b = first["pixels"], second["pixels"]
    if len(a) != len(b):
        raise ProbeError(f"{first['path'].name} and {second['path'].name} are different sizes")
    width = first["w"]
    differing = 0
    total_delta = 0
    worst = 0
    x0, y0, x1, y1 = width, first["h"], -1, -1
    for index in range(0, len(a), 3):
        d0 = abs(a[index] - b[index])
        d1 = abs(a[index + 1] - b[index + 1])
        d2 = abs(a[index + 2] - b[index + 2])
        if not (d0 or d1 or d2):
            continue
        differing += 1
        total_delta += d0 + d1 + d2
        worst = max(worst, d0, d1, d2)
        pixel = index // 3
        x, y = pixel % width, pixel // width
        x0, x1 = min(x0, x), max(x1, x)
        y0, y1 = min(y0, y), max(y1, y)
    mean = (total_delta / (3 * differing)) if differing else 0.0
    return {
        "differing": differing,
        "mean": mean,
        "worst": worst,
        "box": None if y1 < 0 else (x0, y0, x1 - x0 + 1, y1 - y0 + 1),
    }


def report_window(name: str, stats: list[dict]) -> None:
    print(f"\n=== {name} ===")
    for entry in stats:
        top = ", ".join(
            f"#{colour} {count} ({100.0 * count / entry['total']:.2f}%)" for colour, count in entry["top"]
        )
        print(
            f"  present {entry['present']:>6}  {entry['w']}x{entry['h']}  "
            f"non-black {entry['non_black']}/{entry['total']} "
            f"({100.0 * entry['non_black'] / entry['total']:.2f}%)  "
            f"distinct colours {entry['colours']}  top: {top}"
        )
    for first, second in zip(stats, stats[1:]):
        delta = pair_difference(first, second)
        total = first["total"]
        differing = delta["differing"]
        box = delta["box"]
        where = "nowhere (no pixel differs)" if box is None else f"bbox x={box[0]} y={box[1]} {box[2]}x{box[3]}"
        verdict = "IDENTICAL" if differing == 0 else "DIFFERS"
        print(
            f"  present {first['present']} -> {second['present']}: {differing}/{total} pixels differ "
            f"({100.0 * differing / total:.3f}%)  {verdict}; {where}; mean |delta| over the differing "
            f"pixels {delta['mean']:.2f}/255, worst channel {delta['worst']}/255"
        )


def selftest() -> int:
    """The analysis half of this probe, on fixtures, driving NOTHING.

    WHY A SELFTEST IS THE POINT HERE. This tool's conclusion about the post-movie phase rests entirely
    on two pure functions: `parse_windows`, which decides which fields are captured, and
    `pair_difference`, which decides how much moved and WHERE. A bug in either does not crash — it
    returns a plausible number, and a plausible number is what a whole "the picture is flat" verdict
    gets built on. Measured on this area already: a wrong 24-transition `tail` was read off a log
    because `PSXPORT_LOG_FILE` appends (see `run_leg`), so the habit this guards is not hypothetical.

    The suite requires BOTH answers from each function. `pair_difference` on two IDENTICAL frames must
    report zero differing pixels and a `None` box — a differencer that cannot say "nothing changed"
    cannot support a claim that something did, and that is the same discipline the widescreen pair
    verdict depends on. `parse_windows` must both accept a real window list and REFUSE a count below 2,
    because a 1-frame window silently compares a frame to itself and would report "0.0% changed" as
    though it were a measurement.
    """
    failures = 0
    total = 0

    def check(name: str, got: object, want: object) -> None:
        nonlocal failures, total
        total += 1
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: got {got!r}, expected {want!r}")

    # --- parse_windows: a real list, and the two refusals ---
    check("windows accept start:count list", parse_windows("15000:4,15100:2"),
          [(15000, 4), (15100, 2)])
    # A bare start now defaults to TWO frames, because one frame cannot support the claim: it would be
    # compared to itself. This expectation is load-bearing — it is the default the tool would otherwise
    # use to quietly manufacture a 0.0%-changed result.
    check("windows default a bare start to two frames", parse_windows("15000"), [(15000, 2)])
    for name, text in (("windows refuse count < 2", "15000:1"),
                       ("windows refuse an empty list", ""),
                       ("windows refuse a non-numeric start", "soon:4"),
                       ("windows refuse a non-numeric count", "15000:four"),
                       ("windows refuse a malformed part", "15000:4,:2")):
        total += 1
        try:
            parse_windows(text)
        except ProbeError:
            print(f"  ok   {name}: refused, as required")
        else:
            failures += 1
            print(f"  FAIL {name}: accepted {text!r}, which cannot support a frame-to-frame claim")

    # --- pair_difference: the discriminator, on synthetic pixel buffers ---
    width, height = 8, 4

    def frame(pixels: bytes) -> dict:
        return {"path": Path("fixture.ppm"), "w": width, "h": height, "pixels": pixels}

    flat = bytes(bytearray([10, 20, 30]) * (width * height))
    same = pair_difference(frame(flat), frame(flat))
    check("identical frames -> 0 differing", same["differing"], 0)
    check("identical frames -> mean 0", same["mean"], 0.0)
    check("identical frames -> worst 0", same["worst"], 0)
    check("identical frames -> no box", same["box"], None)

    # A known 2-row band at the BOTTOM row of the frame, 3 pixels wide, each pixel +5 on one channel.
    moved = bytearray(flat)
    for y in (height - 2, height - 1):
        for x in (2, 3, 4):
            base = (y * width + x) * 3
            moved[base] = min(255, moved[base] + 5)
    band = pair_difference(frame(flat), frame(bytes(moved)))
    check("known band -> 6 differing pixels", band["differing"], 6)
    check("known band -> worst channel delta 5", band["worst"], 5)
    check("known band -> mean channel delta 5/3", round(band["mean"], 4), round(5 / 3, 4))
    check("known band -> box names where it moved", band["box"], (2, height - 2, 3, 2))

    # A single-channel change of 1 must be reported, not rounded away: a differencer that ignored
    # small deltas would report a still frame as static and call a real 1-LSB difference "no change".
    one = bytearray(flat)
    one[0] = min(255, one[0] + 1)
    single = pair_difference(frame(flat), frame(bytes(one)))
    check("1-LSB single-pixel change is not rounded away", single["differing"], 1)
    check("1-LSB change -> box is one pixel", single["box"], (0, 0, 1, 1))

    # Differently-sized frames must be REFUSED, not compared over the shorter buffer.
    total += 1
    try:
        pair_difference(frame(flat), {"path": Path("small.ppm"), "w": 4, "h": 4,
                                      "pixels": bytes(48)})
    except ProbeError:
        print("  ok   mismatched sizes refused, as required")
    else:
        failures += 1
        print("  FAIL mismatched sizes compared anyway, which would report a whole-frame difference")

    if failures:
        print(f"  selftest: {failures} case(s) FAILED")
        return 1
    print(f"  selftest: {total - failures}/{total} cases behaved as required. The load-bearing pair "
          "is the two identical "
          "frames reporting zero and no box, and the known 2-row band naming its own box: without both, "
          "'nothing moved' and 'this band moved' are the same claim.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--at", default="15000:4", help="capture window(s): start:count[,start:count]")
    parser.add_argument("--frames", type=int, default=0, help="field budget (default: last window end + 600)")
    parser.add_argument("--pair", action="store_true", help="also run the 4:3/16:9 widescreen pair verdict")
    parser.add_argument("--keep", action="store_true", help="keep the captured PNGs in scratch/screenshots")
    parser.add_argument("--selftest", action="store_true",
                        help="exercise the window parser and the frame differencer on fixtures, "
                             "driving nothing and launching no product")
    args = parser.parse_args()
    if args.selftest:
        return selftest()

    windows = parse_windows(args.at)
    last = max(start + count - 1 for start, count in windows)
    budget = args.frames or (last + 600)
    for required in (DEFAULT_BINARY, DEFAULT_EXE, PAIR_TOOL if args.pair else DEFAULT_BINARY):
        if not required.is_file():
            raise ProbeError(f"{required} is missing")

    others = running_instances()
    if others:
        raise ProbeError("refusing to start a second product instance; already running:\n  " + "\n  ".join(others))
    if not SCREENSHOTS.is_dir():
        SCREENSHOTS.mkdir(parents=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    flat = [index for start, count in windows for index in range(start, start + count)]
    # The capture trigger is capped at 32 entries inside the product, so say so rather than letting a
    # long window silently lose its tail.
    if len(flat) > 32:
        raise ProbeError(f"{len(flat)} capture indices requested; the product's trigger holds 32")

    # Every leg writes the same scratch/screenshots/present_<n>.png names, so each leg's captures are
    # RENAMED into this tool's own directory the moment that leg finishes. Without that, the second
    # leg's run deletes the first leg's pictures before the pair tool ever sees them — which is
    # exactly the kind of silent evidence loss this project treats as a lying instrument.
    leg_files: dict[tuple[str, int], Path] = {}
    for label, (widescreen, sink) in (("4:3", LEG_NARROW), ("16:9", LEG_WIDE)):
        for stale in SCREENSHOTS.glob("present_*.png"):
            stale.unlink()
        log = SCRATCH / f"leg_{label.replace(':', '')}.log"
        run_leg(label, widescreen, sink, budget, " ".join(str(i) for i in flat), log)
        missing = [n for n in flat if not (SCREENSHOTS / f"present_{n}.png").is_file()]
        if missing:
            tail = log.read_text(errors="replace").splitlines()[-12:]
            raise ProbeError(
                f"{label} leg captured none of {missing}; the product's own trigger log says:\n  "
                + "\n  ".join(tail)
            )
        for index in flat:
            owned = SCRATCH / f"{label.replace(':', '')}_{index}.png"
            shutil.move(str(SCREENSHOTS / f"present_{index}.png"), str(owned))
            leg_files[(label, index)] = owned
        for start, count in windows:
            stats = []
            for index in range(start, start + count):
                entry = frame_stats(leg_files[(label, index)])
                entry["present"] = index
                stats.append(entry)
            report_window(f"{label} leg, presents {start}..{start + count - 1}", stats)
        width_line = [
            line.split("] ", 1)[-1]
            for line in log.read_text(errors="replace").splitlines()
            if "[wide]" in line
        ]
        print(f"\n[{label}] [wide] change log, in order (printed on change only, so the LAST is the steady state):")
        for line in width_line:
            print(f"    {line}")
        print(f"    steady state = {width_line[-1] if width_line else 'NO [wide] LINE AT ALL'}")

    if args.pair:
        for start, count in windows:
            print(f"\n=== widescreen_pair.py verdict, presents {start}..{start + count - 1} ===")
            # The pair tool's refusal is the deliverable, so its own stdout and stderr are BOTH
            # forwarded: a verdict hidden behind a swallowed error code is not a verdict.
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PAIR_TOOL),
                    "--narrow",
                    str(leg_files[("4:3", start)]),
                    "--wide",
                    str(leg_files[("16:9", start)]),
                ],
                cwd=ROOT,
                check=False,
            )
            print(f"(widescreen_pair.py exit {completed.returncode})")

    if not args.keep:
        for path in leg_files.values():
            path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProbeError, Unreadable) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
