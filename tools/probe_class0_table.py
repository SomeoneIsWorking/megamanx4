#!/usr/bin/env python3
"""probe_class0_table.py — watch the class-0 handler table for the word the guest dispatched on.

WHY THIS EXISTS. The recorded frontier said "the class-0 interrupt table entry at 0x8011CB98 holds
0x0113D7D0, a non-guest word that no owner of the queue could have written". Issue 0036 later
corrected the model underneath that sentence - the guest DISPATCHED on the word rather than storing
it - but the sentence's own claim about the slot was never checked, and it is the load-bearing half.

This probe checks it, and the answer is no. Across 41 ticks x 1,024 word-reads spanning presented
frames 15 to 13,426, and across a separate 97-tick spot series over 14,297 frames that included
0x8011CB98 itself, **0x0113D7D0 was not present in any watched window**, and 0x8011CB98 held a stable
0x800DD7FC - a plausible guest address - at every observation including the one at the fault. The
static image agrees: 0 of 294,912 words hold the value, and 0x8011CB90..0x8011CB9C are all zero in
the file, so the table is filled at runtime and the bad word is not one of its values either.

So the frontier question changes shape: it is no longer "which slot holds it" but "what computes
it". A value that is never seen sitting in memory anywhere reachable, and is nevertheless the
address the CPU was told to jump to, was produced transiently - in a register, or across a
calculation the sampler never catches between.

DESIGNED NEGATIVE FIRST, and it earned that on its first run. The `rw` endpoint REFUSES a 512-word
block, so an early version of this probe reported "scanned 0 word(s) this tick" and would have
published a clean absence over a window it never read. It now treats an empty read as a HOLE, names
it as not covered, and carries on. Block size 64 words is measured to work; 512 does not.

The environment is not hand-built. `agent_environment` is the framework's ONE headless, silent,
unpaced launch policy and it REFUSES without a named settings file, so composing an environment here
would both bypass that refusal and miss what it sets. `tools/live_play.py` uses it the same way.

Usage: uv run --frozen python tools/probe_class0_table.py [PORT]
"""
from __future__ import annotations
import os, pathlib, socket, subprocess, sys, time

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "external/psxport" / "tools"))
sys.path.insert(0, str(REPO / "external/psxport" / "tools" / "port"))
from launch_environment import agent_environment

SETTINGS = REPO / "psxport_settings.ini"
EXECUTABLE = REPO / "build/bin/megamanx4_port"
IMAGE = REPO / "scratch/bin/megamanx4/SLUS_005.61"
if "--help" in sys.argv or "-h" in sys.argv:
    print(__doc__.strip())
    raise SystemExit(0)
PORT = int(sys.argv[1]) if len(sys.argv) == 2 else 6095
# A WIDE window, because 0x0113D7D0 was not in the eight words an earlier record named, and the
# question is now "where is that word at all" rather than "what is in this slot".
#
# BLOCK is a MEASURED limit, not a preference: the `rw` endpoint refuses a 512-word block and
# answers 64. A probe that treats the empty answer as "nothing there" would publish a clean absence
# over a window it never read, which is the one failure this whole workspace keeps meeting.
# FOUR regions, each added because a previous region came back empty and the NEXT place the value
# could be sitting was named rather than guessed:
#   0x8011C000  the class-0 handler table neighbourhood the frontier originally blamed
#   0x801FE000  the BIOS-thread TASK STACK. OpenTh logged sp=0x801FEC00 for entry 0x8001DAF8, and
#               the sp descends across repeated ChangeTh, so this is where a stale guest return
#               address would live if the fault were a bad word read off the task's own stack.
#   0x801F8000  scratch region
#   0x80139000  the second fault-time register's neighbourhood
# Measured: 0x0113D7D0 present at 0 of 43,520 word-reads over these, across 34 ticks to frame 13,163.
BLOCK = 64

# ROTATING SLAB OVER ALL GUEST RAM, and WHY the four fixed windows were replaced.
#
# The value is in no register at the fault (0 of 32 general registers hold 0x0113D7D0, measured), it
# is not an immediate a `jal` could carry from KSEG0 code, and it was absent from the four windows
# below over 43,520 word-reads. That leaves a LOAD, so it is in RAM - and the four windows covered
# 43,520 of the 512,000 words the PSX has. A quarter-percent coverage cannot support "it is not in
# memory".
#
# So this scans a slab that SLIDES each tick: 256 blocks of 64 = 16,384 words per tick, covering all
# 512,000 words in ~32 ticks. The fault lands near tick 33, so full coverage and the fault are close
# enough to be worth one run. `slab(tick)` keeps the arithmetic in one place so the window a tick
# reads is a function of the tick, not a statement repeated in the loop.
SLAB_BLOCKS = 256
GUEST_RAM_BYTES = 2 * 1024 * 1024


def slab(tick: int) -> list[tuple[int, int]]:
    words = SLAB_BLOCKS * BLOCK
    start = (tick * words * 4) % GUEST_RAM_BYTES
    ranges = []
    for i in range(SLAB_BLOCKS):
        base = start + i * BLOCK * 4
        if base + BLOCK * 4 <= GUEST_RAM_BYTES:
            ranges.append((base, BLOCK))
    return ranges
SPOT = [0x801F8300, 0x80139554]
BAD = 0x0113D7D0
TERMINATOR = "---END---\n"

for required in (EXECUTABLE, IMAGE, SETTINGS):
    if not required.is_file():
        print(f"REFUSED: {required} is missing — NOTHING WAS RUN")
        raise SystemExit(1)

environment = agent_environment(dict(os.environ), settings=SETTINGS)
for key in ("PSXPORT_REPL", "PSXPORT_NATIVE_FRAMES"):
    environment.pop(key, None)
log = REPO / "scratch/live/table_probe_run.log"
log.parent.mkdir(parents=True, exist_ok=True)
log.write_text("")
environment.update({
    "PSXPORT_DEBUG_SERVER": str(PORT),
    "PSXPORT_PRESENT_SINK": "1284x720",
    "PSXPORT_X4_WIDESCREEN": "1",
    "PSXPORT_WATCHDOG": "3600",
    "PSXPORT_LOG_FILE": str(log),
})
child = subprocess.Popen([str(EXECUTABLE), str(IMAGE)], cwd=REPO, env=environment,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f"probe: product pid {child.pid} on 127.0.0.1:{PORT}, scanning {SLAB_BLOCKS * BLOCK} word(s) "
      f"per tick, sliding, for 0x{BAD:08X}")
try:
    deadline = time.time() + 120.0
    sock = None
    while True:
        try:
            sock = socket.create_connection(("127.0.0.1", PORT), timeout=5.0)
            break
        except OSError:
            if time.time() > deadline or child.poll() is not None:
                print("probe: the endpoint never opened")
                raise SystemExit(1)
            time.sleep(0.5)
    stream = sock.makefile("rwb")

    def cmd(text: str):
        stream.write((text + "\n").encode()); stream.flush(); out = []
        while True:
            line = stream.readline()
            if not line:
                return None
            decoded = line.decode(errors="replace")
            if decoded == TERMINATOR:
                return "".join(out).rstrip("\n")
            out.append(decoded)

    def word(address: int):
        reply = cmd(f"rw {address:X} 1")
        if reply is None or ":" not in reply:
            return None
        try:
            return int(reply.split(":", 1)[1].split()[0], 16)
        except (IndexError, ValueError):
            return None

    def frame():
        reply = cmd("frame")
        if reply is None:
            return None
        for token in reply.replace("=", " ").split():
            if token.isdigit():
                return int(token)
        return None

    def block(address: int, count: int):
        reply = cmd(f"rw {address:X} {count}")
        if reply is None or ":" not in reply:
            return None
        try:
            return [int(x, 16) for x in reply.split(":", 1)[1].split()]
        except ValueError:
            return None

    ticks = 0
    scanned = 0
    while True:
        current = frame()
        if current is None:
            print(f"probe: the endpoint stopped answering after {ticks} tick(s) — the product ended")
            break
        found = []
        total = 0
        for base, count in slab(ticks):
            got = block(base, count)
            if got is None:
                print(f"probe: a block read came back empty at frame {current}; that is a HOLE, "
                      f"not a zero, and the scan below does NOT cover it")
                continue
            total += len(got)
            for offset, value in enumerate(got):
                if value == BAD:
                    found.append(base + offset * 4)
        spot = [word(a) for a in SPOT]
        print(f"frame {current:>6}  scanned {total:>4} word(s) this tick  "
              f"spot " + "  ".join(f"0x{a:08X}=" + (f"{v:08X}" if v is not None else "EMPTY")
                                    for a, v in zip(SPOT, spot)), flush=True)
        scanned += total
        if found:
            print(f"FOUND 0x{BAD:08X} at " + ", ".join(f"0x{a:08X}" for a in found)
                  + f" at frame {current}, after {ticks} tick(s) and {scanned} word(s) scanned")
            break
        ticks += 1
        time.sleep(0.05)
    else:
        print(f"no transition seen: {scanned} word(s) scanned over {ticks} tick(s)")
finally:
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
    print(f"probe: product exited with {child.returncode}")
