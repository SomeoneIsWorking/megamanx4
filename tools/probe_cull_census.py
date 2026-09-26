#!/usr/bin/env python3
"""probe_cull_census.py — the cull census on CAPTURED guest state, with denominators.

WHAT THIS IS. The defect being fixed is a cull that discards geometry the widened frame can show, so the
number that matters is: of the objects the game actually had this frame, how many pass the cull at 4:3
versus at wide, and which are the ones the widening newly admits. A hand-built object set cannot answer
that; only the game's own pools can. This probe therefore drives the framework's control channel on a
live headless run, reads the real object pools and the real camera scroll, and evaluates BOTH windows
over that one captured state — the two windows being the only difference, which is what makes the
comparison a measurement of the cull rather than of two different frames.

IT REPORTS ITS OWN COVERAGE, and distinguishes the two ways a small number can be small. It prints how
many pool entries it scanned, how many it classified as participating in the draw gate, and it exits 3
with an explicit message when NOTHING was participating: a census over an unpopulated pool measured
nothing about the cull, and saying "0 passed" there would be a fabricated clean result.

POOL TABLE. Bases, sizes and counts are the decomp's own symbol declarations
(external/mmx4/config/symbols.us.txt:469-486, 566), not invented: the count is the declared size divided
by the stride, and the probe prints that division so a wrong stride is visible rather than assumed. The
`active` byte is offset +0 in every one of these layouts, which is what the draw pass tests.

READ-ONLY. The probe never writes guest memory and never calls a guest function; a census that pokes the
guest is measuring the poke.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# name, base, declared size, stride, layout. The count is derived and printed, not asserted here.
POOLS = [
    ("g_Player", 0x801418C8, 0xE4, 0xE4, "base"),
    ("g_Entity", 0x80175D58, 0xE4, 0xE4, "base"),
    ("baz_objects", 0x8013E470, 0xA0, 0x50, "base"),
    ("main_objects", 0x8013BED0, 0x1D40, 0x9C, "base"),
    ("foo_objects", 0x80141AB0, 0x120, 0x60, "base"),
    ("weapon_objects", 0x801406F8, 0x9C0, 0x9C, "base"),
    ("shot_objects", 0x8013F328, 0x1380, 0x9C, "base"),
    ("visual_objects", 0x8013E510, 0xE00, 0x70, "base"),
    ("item_objects", 0x80165A30, 0x1180, 0x8C, "base"),
    ("misc_objects", 0x80173CA0, 0x1800, 0x60, "base"),
    ("unk_objects", 0x801410C0, 0x780, 0x60, "base"),
    ("g_QuadObjects", 0x801435B0, 0xC00, 0x60, "quad"),
]

CAMERA_LAYERS = 0x801419B0
CAMERA_STRIDE = 0x54
CAMERA_SCROLL_X = 0x0A
CAMERA_SCROLL_Y = 0x0E

RETAIL_WIDTH = 320
RETAIL_HEIGHT = 240
# The 32/32 fixed slack of the 0x8002B288 writer, which is the window the draw pass's BaseObj path uses.
FIXED_ADDEND = 0x20
FIXED_BOUND_X = 0x180
FIXED_BOUND_Y = 0x130


class Channel:
    """The framework's control channel. One command per line, reply terminated by `---END---`
    (external/psxport/runtime/psx/dbg_server.cpp:10). Read-only: this probe never writes."""

    TERMINATOR = b"---END---"

    def __init__(self, port: int, timeout: float = 20.0) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buffer = b""

    def command(self, line: str) -> str:
        self.sock.sendall((line + "\n").encode())
        while self.TERMINATOR not in self.buffer:
            data = self.sock.recv(1 << 20)
            if not data:
                raise RuntimeError(f"control channel closed on {line!r}")
            self.buffer += data
        head, _, rest = self.buffer.partition(self.TERMINATOR)
        self.buffer = rest.lstrip(b"\r\n")
        return head.decode(errors="replace").strip()

    def read(self, address: int, words: int) -> list[int]:
        out: list[int] = []
        while len(out) < words:
            at = address + 4 * len(out)
            reply = self.command(f"rw {at:08x}")
            if not reply.startswith(f"{at:08X}:"):
                raise RuntimeError(f"control channel refused {address:#x}: {reply!r}")
            out.extend(int(word, 16) for word in reply.split(":", 1)[1].split())
        return out[:words]

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def sign_extend_byte(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def sign_extend_half(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def window_contains(value: int, addend: int, bound: int) -> bool:
    """The recovered predicate: (u16)(v + A) <u B, with both terms masked as the guest masks them."""
    return ((value + addend) & 0xFFFF) < (bound & 0xFFFF)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5962)
    parser.add_argument("--margin", type=int, default=54, help="the plan's horizontal margin")
    parser.add_argument("--json", type=Path, help="write the census here")
    args = parser.parse_args()

    try:
        channel = Channel(args.port)
    except OSError as error:
        print(f"[census] no control channel on 127.0.0.1:{args.port}: {error}", file=sys.stderr)
        print("[census] this instrument read NOTHING. It did not scan 0 objects; it failed to connect.")
        return 2

    report: dict = {"margin": args.margin, "pools": []}
    try:
        scrolls = {}
        for layer in range(3):
            base = CAMERA_LAYERS + layer * CAMERA_STRIDE
            word = channel.read(base + CAMERA_SCROLL_X, 1)[0]
            yword = channel.read(base + CAMERA_SCROLL_Y, 1)[0]
            scrolls[layer] = (sign_extend_half(word & 0xFFFF), sign_extend_half(yword & 0xFFFF))
        print(f"[census] camera scroll (x, y) per layer: {scrolls}")
        report["scrolls"] = scrolls

        scanned = 0
        active_total = 0
        nonzero_total = 0
        pass_4x3 = 0
        pass_wide = 0
        newly: list[dict] = []

        for name, base, size, stride, layout in POOLS:
            count = size // stride
            if size % stride:
                print(f"[census] {name}: declared size {size:#x} is not a multiple of stride {stride:#x}")
            background_offset = 0x37 if layout == "quad" else 0x14
            head_words = max(background_offset // 4 + 1, 0x34 // 4 if layout == "quad" else 6)
            pool_active = 0
            pool_nonzero = 0
            pool_4x3 = 0
            pool_wide = 0
            for index in range(count):
                entry = base + index * stride
                head = channel.read(entry, 1)[0]
                scanned += 1
                if head:
                    pool_nonzero += 1
                    nonzero_total += 1
                if head & 0xFF == 0:
                    continue
                pool_active += 1
                active_total += 1
                on_screen = (head >> 8) & 0xFF
                words = channel.read(entry, head_words)
                bg = sign_extend_byte((words[background_offset // 4] >> 24) & 0xFF)
                x_raw = (words[0x0A >> 2] >> 16) & 0xFFFF
                y_raw = (words[0x0E >> 2] >> 16) & 0xFFFF
                if 0 <= bg < len(scrolls):
                    x = sign_extend_half(x_raw) - scrolls[bg][0]
                    y = sign_extend_half(y_raw) - scrolls[bg][1]
                else:
                    x = sign_extend_half(x_raw)
                    y = sign_extend_half(y_raw)
                if layout == "quad":
                    corners = [
                        (
                            sign_extend_half(((words[cx >> 2] >> 16) & 0xFFFF) + x_raw),
                            sign_extend_half(((words[cy >> 2] >> 16) & 0xFFFF) + y_raw),
                        )
                        for cx, cy in ((0x16, 0x1A), (0x1E, 0x22), (0x26, 0x2A), (0x2E, 0x32))
                    ]
                    inside_4x3 = any(
                        window_contains(cx, 0, RETAIL_WIDTH) and window_contains(cy, 0, RETAIL_HEIGHT)
                        for cx, cy in corners
                    )
                    inside_wide = any(
                        window_contains(cx, args.margin, RETAIL_WIDTH + 2 * args.margin)
                        and window_contains(cy, 0, RETAIL_HEIGHT)
                        for cx, cy in corners
                    )
                else:
                    inside_4x3 = window_contains(x, FIXED_ADDEND, FIXED_BOUND_X) and window_contains(
                        y, FIXED_ADDEND, FIXED_BOUND_Y
                    )
                    inside_wide = window_contains(
                        x, FIXED_ADDEND + args.margin, FIXED_BOUND_X + 2 * args.margin
                    ) and window_contains(y, FIXED_ADDEND, FIXED_BOUND_Y)
                pool_4x3 += 1 if inside_4x3 else 0
                pool_wide += 1 if inside_wide else 0
                if inside_wide and not inside_4x3:
                    newly.append(
                        {
                            "pool": name,
                            "index": index,
                            "entry": f"{entry:#010x}",
                            "bg": bg,
                            "screen_x": x,
                            "screen_y": y,
                            "on_screen_byte": on_screen,
                        }
                    )
            pass_4x3 += pool_4x3
            pass_wide += pool_wide
            report["pools"].append(
                {
                    "name": name,
                    "base": f"{base:#010x}",
                    "size": size,
                    "stride": stride,
                    "count": count,
                    "nonzero_heads": pool_nonzero,
                    "active": pool_active,
                    "pass_4x3": pool_4x3,
                    "pass_wide": pool_wide,
                }
            )
            print(
                f"[census] {name:16s} {base:#010x} size {size:#06x} stride {stride:#04x} "
                f"n={count:3d} (size/stride={size // stride}) nonzero-heads={pool_nonzero:3d} "
                f"active={pool_active:3d} pass@4:3={pool_4x3:3d} pass@wide={pool_wide:3d} "
                f"newly={pool_wide - pool_4x3:+d}"
            )

        report.update(
            scanned=scanned,
            active=active_total,
            nonzero_heads=nonzero_total,
            pass_4x3=pass_4x3,
            pass_wide=pass_wide,
            newly_admitted=newly,
        )
        print(
            f"[census] COVERAGE: scanned {scanned} pool entries across {len(POOLS)} pools; "
            f"{nonzero_total} had a non-zero header; {active_total} were active"
        )
        if active_total == 0:
            print(
                "[census] NO ACTIVE OBJECTS. This run never reached a populated pool, so the census "
                "measured NOTHING about the cull. That is a failed measurement, not a clean one: the "
                f"0 pass@4:3 / 0 pass@wide figures above are the absence of state, not a verdict."
            )
        else:
            print(
                f"[census] {pass_4x3} of {active_total} active objects pass the cull at 4:3 and "
                f"{pass_wide} at wide; {len(newly)} newly admitted by the widening"
            )
            for entry in newly[:32]:
                print(
                    f"[census]   NEW {entry['pool']}[{entry['index']}] at {entry['entry']} "
                    f"bg={entry['bg']} screen=({entry['screen_x']},{entry['screen_y']}) "
                    f"on_screen_byte={entry['on_screen_byte']}"
                )
        if args.json:
            args.json.write_text(json.dumps(report, indent=2))
            print(f"[census] wrote {args.json}")
        return 0 if active_total else 3
    finally:
        channel.close()


if __name__ == "__main__":
    sys.exit(main())
