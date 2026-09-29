#!/usr/bin/env python3
"""Scan Mega Man X4's scheduler dispatch table for the corrupted function pointer.

DERIVED FROM THE DECODED GUEST INSTRUCTIONS, and corrected once already. The first version of this
probe read 250 addresses and NONE of them was a dispatch slot, because it took the table base from
`ori $s0, $s0, 0x8300` at 0x8001261C. That instruction does not set the table base: `$s0` holds the
CELL at 0x801F8300, and the table base is stored INTO that cell one instruction later:

    80012604  lui   $v0, 0x801f
    80012608  ori   $v0, $v0, 0x8100      v0 = 0x801F8100   <- the TABLE base
    80012624  lui   $at, 0x8020
    80012628  sw    $v0, -0x7d00($at)     [0x80200000-0x7d00 = 0x801F8300] = 0x801F8100
    80012630  lw    $a0, -0x7d00($a0)     a0 = the entry, loaded back from the cell
    80012638  lhu   $v1, ($a0)            state halfword at entry+0
    80012698  lw    $v0, ($s0)            v0 = the entry
    800126A0  lw    $a0, 8($v0)           the dispatch argument is entry+8
    80012718  addiu $v0, $v0, 0x80        advance 0x80 per entry
    8001271C  sltu  $v1, 0x801F82FF, $v0  the loop ends when entry+0x80 passes 0x801F82FF

which is FOUR entries, not 250. The lesson is recorded in the code because it is the same failure
as every other one in this investigation: a constant lifted from a disassembly listing is not a
derivation, and the only thing that catches it is checking the arithmetic against the loop's
behaviour.

THE FEEDER MUST BE SHOWN. A scan reporting "0 matches" is indistinguishable from a scan that never
ran, so every slot's value is printed and a scan that cannot read all of them FAILS rather than
reporting a clean zero. The scan also runs until the port faults, because a single sweep taken
before the fault is a measurement of the wrong moment.

EXIT CODES, and every decision that produces one is a pure function so a mutation to it is visible:
0 nothing saw the target, 1 a sighting was seen, 2 the run REFUSED to conclude. `--selftest` drives
`decide`, `sweep_refusal`, `classify` and the table walk with synthetic readings and no port, so the
gate that would have caught the withdrawn 4f915e5 refutation and the `NameError` in this tool exists.
"""
from __future__ import annotations

import argparse
import pathlib
import socket
import subprocess
import sys
import time

# THE TABLE BASE IS 0x801F8100, the value `ori $v0,$v0,0x8100` produces and `sw $v0,-0x7d00($at)`
# stores into the cell. 0x801F8300 is the CELL, not the table.
TABLE_BASE = 0x801F8100
STRIDE = 0x80
STATE_OFFSET = 0
POINTER_OFFSET = 8
LOOP_END = 0x801F82FF          # sltu (LOOP_END, entry+STRIDE) ends the loop
TARGET_DEFAULT = 0x0113D7D0


def entry_addresses() -> list[int]:
    """Walk the loop the guest actually walks, rather than guessing an extent.

    The loop runs while `LOOP_END >= entry + STRIDE`, so the entries are the multiples of STRIDE
    from TABLE_BASE up to the first one that passes LOOP_END. Deriving them by walking reproduces
    the guest's own arithmetic, which is the check that the previous 250-slot guess failed.
    """
    entries = []
    entry = TABLE_BASE
    while True:
        entries.append(entry)
        if LOOP_END < entry + STRIDE:
            return entries
        entry += STRIDE


def slot_addresses() -> list[tuple[int, int]]:
    """Every dispatch slot: the word at entry+8 for each entry the loop walks."""
    return [(index, entry + POINTER_OFFSET) for index, entry in enumerate(entry_addresses())]


def state_addresses() -> list[tuple[int, int]]:
    """The state halfword of each entry, at entry+0, for context in the report."""
    return [(index, entry + STATE_OFFSET) for index, entry in enumerate(entry_addresses())]


class DebugLink:
    """One line-oriented connection to the product's own control channel."""

    def __init__(self, port: int) -> None:
        self._sock = socket.create_connection(("127.0.0.1", port), timeout=8)
        self._buffer = b""

    def send(self, text: str) -> None:
        self._sock.sendall((text + chr(10)).encode())

    def line(self) -> str | None:
        """The next complete line, or None on close/timeout."""
        deadline = time.time() + 8
        while b"\n" not in self._buffer and time.time() < deadline:
            try:
                chunk = self._sock.recv(8192)
            except OSError:
#THE PORT DIED.That is the NORMAL end of this run - it faults on purpose, and the
#OS resets the socket.It is reported as "no more lines", not raised, so the sweeps
#already completed are kept and reported instead of being lost to a traceback.
                return None
            if not chunk:
                return None
            self._buffer += chunk
        if b"\n" not in self._buffer:
            return None
        line, _, rest = self._buffer.partition(b"\n")
        self._buffer = rest
        return line.decode(errors="replace")

    def close(self) -> None:
        self._sock.close()


def read_word(link: DebugLink, address: int) -> int | None:
    """Read one guest word, and REFUSE a reply that does not answer the question asked.

    The channel interleaves unsolicited telemetry (`guest:`, `fallback:`, `---END---`) with command
    replies, so taking "the next line" desynchronises: measured on a live port, `rw 0x801F8300`
    returned the data line for `0x801F8308`, and a probe that believed it would have recorded a
    confidently WRONG value for every slot. The data line is therefore identified by its own format
    AND its address is checked against the request; anything else is skipped, and a run that never
    sees a matching line FAILS instead of reporting a clean zero.
    """
    link.send(f"rw 0x{address:08X} 1")
    for _ in range(64):
        line = link.line()
        if line is None:
            return None
        head, sep, words = line.partition(":")
        if not sep or len(head.strip()) != 8:
            continue
        try:
            answered = int(head.strip(), 16)
        except ValueError:
            continue
        if answered != address:
            continue
        for token in words.split():
            try:
                return int(token, 16)
            except ValueError:
                continue
    return None


def classify(values: dict[int, int], target: int) -> tuple[bool, list[tuple[int, int]]]:
    """Pure decision, so it can be mutation-tested without a live product."""
    hits = sorted((addr, value) for addr, value in values.items() if value == target)
    return bool(hits), hits


# EVERY verdict and EVERY refusal this tool can return lives in the two functions below and nowhere
# else, so `--selftest` drives the real decisions instead of comparing constants.
#
# That separation is not decoration. The first version of this tool decided inline in `main`: it
# shipped a `NameError` on any run where a slot was non-zero, and it wrote a WRONG refutation at
# ~12 s, before the fault it was supposed to observe. Both were caught by a human reading output,
# because there was no gate. A decision inline in a loop over a socket cannot be given one without
# being taken out of the loop, and taking it out is the whole fix.
def sweep_refusal(sweep_index: int, read_count: int, expected_slots: int) -> str | None:
    """The refusal for a sweep that did not read every slot, or None when it did.

    A sweep missing a slot is not a small hole in a clean zero -- it is a snapshot of a table being
    torn down, and reporting its zeros as the table's contents is exactly the refutation that was
    withdrawn in 4f915e5.
    """
    if read_count == expected_slots:
        return None
    return (f"REFUSED: sweep {sweep_index} read {read_count} of {expected_slots} slots; the port is "
            f"gone or the channel stopped answering, so the table was NOT fully read")


def decide(sweeps: int, slots: list[tuple[int, int]], last_values: dict[int, int],
           sightings: list[tuple[int, int, int]], target: int) -> tuple[list[str], int]:
    """Turn what was read into the report lines and the exit code. Pure: no I/O, no clock.

    THE SIGHTING BEATS THE LAST SWEEP, deliberately, and the order is asserted rather than assumed.
    The last complete sweep is what the faulting dispatch read, but a target seen in ANY earlier
    sweep is a real sighting that must not be reported as a clean zero; conversely a sighting in an
    earlier sweep is still a sighting when the last sweep is empty, so this branch must stay ABOVE
    the missing-snapshot refusal. Reordering the two makes a tool that refutes what it saw.
    """
    lines = [f"completed {sweeps} sweep(s) of {len(slots)} slots "
             f"(0x{TABLE_BASE + POINTER_OFFSET:08X}..0x{slots[-1][1]:08X}, stride 0x{STRIDE:X})",
             f"LAST sweep before the port ended: {len(last_values)} words, "
             f"{len(set(last_values.values()))} distinct values, "
             f"{sum(1 for v in last_values.values() if v)} non-zero"]
    non_zero = [(address, last_values[address]) for _, address in slots
                if last_values.get(address, 0) != 0]
    lines += [f"  non-zero slot 0x{address:08X} = 0x{value:08X}" for address, value in non_zero[:8]]
    if sightings:
        lines += [f"SIGHTING: sweep {sweep} slot {index} at 0x{address:08X} held 0x{target:08X}"
                  for sweep, index, address in sightings[:8]]
        return lines, 1
    if sweeps == 0:
        lines.append("REFUSED: no complete sweep was ever read, so this is NOT a clean zero")
        return lines, 2
    lines.append(f"NO SWEEP of {sweeps} saw 0x{target:08X} in the table "
                 f"(0 matches of {sweeps * len(slots)} words read)")
    return lines, 0


def selftest() -> int:
    """Drive `decide`, `sweep_refusal`, `classify` and the table walk with synthetic readings.

    These are the tool's actual decisions, so a mutation to one of them turns this red. If a
    mutation survives, the gate is decorative and must be rewritten rather than trusted.
    """
    slots = slot_addresses()
    zeroed = {address: 0 for _, address in slots}
    # A table that is MOSTLY ZERO IS NOT A TABLE OF ZEROS. The withdrawn 4f915e5 refutation read a
    # table that was 245/250 zero with four valid code pointers in it and reported the zeros; this
    # is the same input at the corrected extent, and the report has to name what it actually read.
    populated = dict(zeroed)
    populated[slots[0][1]] = 0x8001D7D0
    populated[slots[2][1]] = 0x800DD7FC
    first, third = slots[0][1], slots[2][1]
    cases: list[tuple[str, int, dict[int, int], list[tuple[int, int, int]], int, tuple[str, ...]]] = [
        ("three clean sweeps and no sighting is a clean zero",
         3, zeroed, [], 0, ("NO SWEEP of 3 saw 0x0113D7D0 in the table",
                             "0 matches of 12 words read")),
        # The retracted refutation's input, at the corrected extent. It must name the pointers it
        # read, and count them, or the reader cannot tell a read table from an empty one.
        ("a sweep holding valid code pointers still reports what it read",
         1, populated, [], 0, ("LAST sweep before the port ended: 4 words, 3 distinct values, "
                               "2 non-zero", "  non-zero slot 0x801F8108 = 0x8001D7D0",
                               "  non-zero slot 0x801F8208 = 0x800DD7FC")),
        ("a sighting in the last sweep is a sighting",
         5, zeroed, [(5, 1, slots[1][1])], 1, ("SIGHTING: sweep 5 slot 1 at 0x801F8188",)),
        # THE DECISION THE TOOL EXISTS FOR: the last sweep saw nothing, an earlier one saw the
        # target. Reporting the last sweep alone here would be a clean zero the run contradicts.
        ("a sighting from an earlier sweep outranks a clean last sweep",
         7, zeroed, [(3, 0, first)], 1, ("SIGHTING: sweep 3 slot 0",)),
        ("a sighting outranks the missing-snapshot refusal",
         0, {}, [(1, 2, third)], 1, ("SIGHTING: sweep 1 slot 2",)),
        ("no complete sweep is refused, not reported as a clean zero",
         0, {}, [], 2, ("REFUSED: no complete sweep was ever read",)),
        ("one sweep is a measurement, so it is not refused",
         1, zeroed, [], 0, ("completed 1 sweep(s) of 4 slots",)),
    ]
    failures: list[str] = []
    for name, sweeps, values, sightings, want_rc, want_texts in cases:
        lines, got_rc = decide(sweeps, slots, values, sightings, TARGET_DEFAULT)
        if got_rc != want_rc:
            failures.append(f"{name}: exit {got_rc}, expected {want_rc}")
        for want_text in want_texts:
            if not any(want_text in line for line in lines):
                failures.append(f"{name}: no report line contains {want_text!r}; got {lines!r}")

    # The refusal that fires MID-SWEEP, on the line that used to fall through into a report.
    for read_count, want in ((4, None), (3, "read 3 of 4 slots"), (0, "read 0 of 4 slots")):
        got = sweep_refusal(9, read_count, len(slots))
        if (got is None) != (want is None) or (want is not None and want not in got):
            failures.append(f"sweep_refusal(9, {read_count}, 4) = {got!r}, expected {want!r}")

    # The per-sweep classifier, on its own, because a non-zero value that is not the target is the
    # input this investigation is entirely about and the one the first draft mishandled.
    found, hits = classify(populated, TARGET_DEFAULT)
    if found or hits:
        failures.append("classify called valid code pointers a sighting")
    found, hits = classify({**zeroed, first: TARGET_DEFAULT}, TARGET_DEFAULT)
    if not found or hits != [(first, TARGET_DEFAULT)]:
        failures.append(f"classify missed a target in the table: found={found} hits={hits!r}")

    # The table walk itself. 250 slots was the withdrawn refutation, so the extent is asserted, not
    # assumed: four entries, from the walk, with the pointer at entry+8 and none of them the CELL.
    entries = entry_addresses()
    if len(entries) != 4 or entries != [0x801F8100, 0x801F8180, 0x801F8200, 0x801F8280]:
        failures.append(f"the walk found {entries!r}, not the four entries the loop bounds describe")
    if 0x801F8300 in entries:
        failures.append("the cell 0x801F8300 is in the table; it is where the base is STORED")
    if [address for _, address in slots] != [entry + POINTER_OFFSET for entry in entries]:
        failures.append("the slots are not the pointer words of the walked entries")

    for line in failures:
        print(f"SELFTEST FAIL: {line}")
    if failures:
        return 1
    print(f"selftest passed: {len(cases)} decision cases, 3 refusal cases, 2 classifier cases, "
          f"and a {len(entries)}-entry table walk")
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=lambda v: int(v, 16), default=TARGET_DEFAULT)
    parser.add_argument("--port", type=int, default=6173)
    parser.add_argument("--log", type=pathlib.Path, default=pathlib.Path("scratch/dispatch_table/t.log"))
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("scratch/dispatch_table"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    env = {
        "PSXPORT_VK_HEADLESS": "1",
        "PSXPORT_NOAUDIO": "1",
        "PSXPORT_NOPACE": "1",
        "PSXPORT_SETTINGS": str(pathlib.Path.cwd() / "psxport_settings.ini"),
        "PSXPORT_ASSET_DIR": "/home/bhamil/repo/psx/psxport",
        "PSXPORT_DEBUG_SERVER": str(args.port),
        "PSXPORT_NATIVE_FRAMES": "20000",
        "PSXPORT_LOG_FILE": str(args.log),
    }
    child = subprocess.Popen(
        ["./build/bin/megamanx4_port"], env={**__import__("os").environ, **env},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        link = None
        for _ in range(40):
            try:
                link = DebugLink(args.port)
                break
            except OSError:
                time.sleep(0.5)
        if link is None:
            print("REFUSED: the port's control channel never came up; the table was NOT read")
            return 2

        slots = slot_addresses()
#THE SCAN RUNS UNTIL THE FAULT, NOT ONCE.A single sweep taken ~12 s into the run reads a
#table that is 245 / 250 zero with four VALID code pointers in it, and the fault does not
#happen until ~40 s.That zero looks exactly like a clean refutation and is one-- it is a
#measurement of the wrong moment.So the table is swept continuously and BOTH answers are
#kept : whether any sweep ever saw the target, and the last complete sweep before the
#process died, which is the state the faulting dispatch actually read.
        sweeps = 0
        ever_saw_target: list[tuple[int, int, int]] = []
        last_values: dict[int, int] = {}
        index_of = {address: index for index, address in slots}
        while True:
            values: dict[int, int] = {}
            for _, address in slots:
                value = read_word(link, address)
                if value is None:
                    break
                values[address] = value
            refusal = sweep_refusal(sweeps, len(values), len(slots))
            if refusal is not None:
                print(refusal)
                break
            sweeps += 1
            last_values = values
            found, hits = classify(values, args.target)
            if found:
                ever_saw_target.extend((sweeps, index_of[address], address) for address, _ in hits)
            if sweeps % 10 == 0:
                print(f"  sweep {sweeps}: {len(set(values.values()))} distinct values, "
                      f"{sum(1 for v in values.values() if v)} non-zero slots, "
                      f"{len(ever_saw_target)} target sighting(s)")

        lines, rc = decide(sweeps, slots, last_values, ever_saw_target, args.target)
        for line in lines:
            print(line)
        if rc == 2:
            # Nothing complete was ever read, so there is no table to write. The report is written
            # only for a sweep that covered every slot, which is what stopped the port-died-first
            # path from walking an empty dict and raising out of the tool.
            return rc
        report = args.out / "dispatch_table.txt"
        report.write_text(
            "".join(f"{index:4d} 0x{address:08X} 0x{last_values[address]:08X}\n"
                    for index, (_, address) in enumerate(slots))
        )
        print(f"table written to {report}")
        return rc
    finally:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()


if __name__ == "__main__":
    sys.exit(main())
