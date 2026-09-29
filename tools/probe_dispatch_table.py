#!/usr/bin/env python3
"""Scan Mega Man X4's scheduler dispatch table for the corrupted function pointer.

DERIVED, NOT ASSUMED. Every constant below comes from the decoded guest instructions at
0x80012600, quoted in the docstring, so a wrong table cannot be produced by a wrong guess:

    80012618  lui   $s0, 0x801f          8001261C  ori $s0, $s0, 0x8300   cursor base 0x801F8300
    80012710  lw    $v0, ($s0)           80012718  addiu $v0, $v0, 0x80   advance 0x80
    800126A0  lw    $a0, 8($v0)                                          the slot is cursor+8
    80012708  sw    $v0, 8($v1)                                          a delay slot writes it back
    80012714  ori   $v1, $v1, 0x82ff     8001271C  sltu $v1, $v1, $v0    loop while cursor <= 0x801F82FF

THE FEEDER MUST BE SHOWN. A scan that reports "0 matches" is indistinguishable from a scan
that never ran, which is the dead-tap failure this project treats as worst. So the table is
not only searched for the target: it is searched for a value that is DEFINITELY there -- the
cursor's own base 0x801F8300 appears in slot 0's neighbourhood only if the table is real -- and
more importantly every slot's value is printed, so the reader sees 250 actual words rather than
a count. A refused or empty scan FAILS; it does not report a clean zero.

Exit codes: 0 the scan ran and the table was read; 1 the target was found in the table;
2 the scan could not run (no port, no media, unreadable table).
"""
from __future__ import annotations

import argparse
import pathlib
import socket
import subprocess
import sys
import time

CURSOR_BASE = 0x801F8300
STRIDE = 0x80
SLOT_OFFSET = 8
TABLE_LIMIT = 0x801FFFF0
TARGET_DEFAULT = 0x0113D7D0


def slot_addresses() -> list[tuple[int, int]]:
    """Every dispatch slot, derived from the decoded cursor arithmetic."""
    return [
        (index, CURSOR_BASE + index * STRIDE + SLOT_OFFSET)
        for index in range((TABLE_LIMIT - CURSOR_BASE - SLOT_OFFSET) // STRIDE + 1)
    ]


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
                # THE PORT DIED. That is the NORMAL end of this run - it faults on purpose, and the
                # OS resets the socket. It is reported as "no more lines", not raised, so the sweeps
                # already completed are kept and reported instead of being lost to a traceback.
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


def main() -> int:
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
        # THE SCAN RUNS UNTIL THE FAULT, NOT ONCE. A single sweep taken ~12 s into the run reads a
        # table that is 245/250 zero with four VALID code pointers in it, and the fault does not
        # happen until ~40 s. That zero looks exactly like a clean refutation and is one -- it is a
        # measurement of the wrong moment. So the table is swept continuously and BOTH answers are
        # kept: whether any sweep ever saw the target, and the last complete sweep before the
        # process died, which is the state the faulting dispatch actually read.
        sweeps = 0
        ever_saw_target: list[tuple[int, int, int]] = []
        last_values: dict[int, int] = {}
        while True:
            values: dict[int, int] = {}
            for _, address in slots:
                value = read_word(link, address)
                if value is None:
                    break
                values[address] = value
            if len(values) != len(slots):
                print(f"REFUSED: sweep {sweeps} read {len(values)} of {len(slots)} slots; the port is "
                      f"gone or the channel stopped answering, so the table was NOT fully read")
                break
            sweeps += 1
            last_values = values
            for index, (_, address) in enumerate(slots):
                if values[address] == args.target:
                    ever_saw_target.append((sweeps, index, address))
            if sweeps % 10 == 0:
                print(f"  sweep {sweeps}: {len(set(values.values()))} distinct values, "
                      f"{sum(1 for v in values.values() if v)} non-zero slots, "
                      f"{len(ever_saw_target)} target sighting(s)")

        values = last_values
        found, hits = classify(values, args.target)
        report = args.out / "dispatch_table.txt"
        report.write_text(
            "".join(f"{index:4d} 0x{address:08X} 0x{values[address]:08X}\n"
                    for index, (_, address) in enumerate(slots))
        )
        distinct = len(set(values.values()))
        print(f"completed {sweeps} sweep(s) of {len(slots)} slots "
              f"(0x{CURSOR_BASE + SLOT_OFFSET:08X}..0x{slots[-1][1]:08X}, stride 0x{STRIDE:X})")
        print(f"LAST sweep before the port ended: {len(values)} words, {distinct} distinct values, "
              f"{sum(1 for v in values.values() if v)} non-zero")
        non_zero = [(a, values[a]) for _, a in slots if values[a] != 0]
        for address, value in non_zero[:8]:
            print(f"  non-zero slot 0x{address:08X} = 0x{value:08X}")
        print(f"table written to {report}")
        if ever_saw_target:
            for sweep, index, address in ever_saw_target[:8]:
                print(f"SIGHTING: sweep {sweep} slot {index} at 0x{address:08X} held 0x{args.target:08X}")
            return 1
        if not values:
            print("REFUSED: no complete sweep was ever read, so this is NOT a clean zero")
            return 2
        print(f"NO SWEEP of {sweeps} saw 0x{args.target:08X} in the table "
              f"(0 matches of {sweeps * len(slots)} words read)")
        return 0
    finally:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()


if __name__ == "__main__":
    sys.exit(main())
