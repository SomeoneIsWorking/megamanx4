#!/usr/bin/env python3
"""live_play.py — PLAY the Mega Man X4 port over its live debug server, and report what it did.

    uv run --frozen python tools/live_play.py
    uv run --frozen python tools/live_play.py --budget-frames 30000 --poll-seconds 0.4
    uv run --frozen python tools/live_play.py --hold right --seconds 8
    uv run --frozen python tools/live_play.py --selftest

WHY THIS IS NOT A SCRIPTER. Every other Mega Man X4 run in this repository is a fixed field budget
with no input at all, and the ones that sample state take their samples at named presents. That shape
cannot answer two of this title's questions:

* "does the front end RESPOND to a pad" is a question about a running game, and a fixed-budget run has
  no way to ask it — and the honest answer for a still-parked guest is "the pad edge reached the
  guest's own words and the front end's handler did not read it", which is two different findings.
* the post-movie falsifier in docs/issues/0029 is about how LONG a state is held and whether the
  state word MOVES, so it needs observations spread across a window rather than at three checkpoints.

So this one leaves the product running at full speed, censuses the front end's own state machine
while it does, offers real pad EDGES only where the census says the guest's code reads the pad, and
photographs what is actually on screen at the points that matter.

THE TRANSPORT IS NOT HERE. `external/psxport/tools/dbgclient.py` is the framework's one client for
`runtime/psx/dbg_server.cpp`, and the port's live endpoint does NOT pause the game — which is exactly
what makes it usable to play a running game and watch it. A second transport here would be free to
disagree about when a reply has arrived. The MENU MODEL is not here either: `tools/title_prompts.py`
owns which screen is on display and which button it wants, and this file asks it.

ONE ROUND TRIP PER CELL, NOT PER QUESTION. The endpoint services at most one command per PRESENTED
frame, so a poll's cost is measured in frames, not milliseconds. Every census is therefore a fixed set
of contiguous `r` byte reads (game_info + its handshake byte in one read, the three CD/stream cells in
another, the pad trio in a third), never one command per field. A driver that spent nine round trips
per decision would stretch its own duty cycle by the difference, and the frame budget is what this
title's history says to distrust: the same boundary was measured at field 974 in one run and 13,153 in
another.

THE TAP POLICY IS A CENSUS DECISION, NOT A CADENCE. `func_8001E708` reads Start only while
`game_info.unkD == 1`, and `func_8001DAF8` takes a different Start arm only while it is 0. So the
model asks `title_prompts.wants_start`, and every tap is reported beside the `unkD` and the pad trio it
was delivered into. Mashing Start blind would also DESTROY the measurement this run exists for: the
`unkD == 0` arm jumps the front end to game state 5, so a tap offered while the state machine is
parked would abandon the very state word the falsifier reads.

WHAT THE RUN REFUSES RATHER THAN REPORTS A ZERO FOR
    an endpoint that never answers; a command the binary does not implement (that is a stale build, not
    a zero); a census read that timed out, more than a few times; a run that presented frames but
    executed no guest blocks; a held input that moved no guest word; an address this tool reads that the
    owning source no longer declares at the same value.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "external/psxport" / "tools"))
sys.path.insert(0, str(REPO / "external/psxport" / "tools" / "port"))
sys.path.insert(0, str(REPO / "tools"))

# agent_environment is the framework's ONE headless/silent/unpaced launch policy, and it is also the
# thing that insists on a named settings file. present_geometry is the framework's ONE PPM/PNG reader.
# dbgclient is the framework's ONE client for the live endpoint. title_prompts is this repository's
# ONE front-end model. Nothing below re-implements any of them.
import title_prompts as prompts
from dbgclient import LiveClient
from launch_environment import agent_environment
from present_geometry import Unreadable, read_image

SETTINGS = REPO / "psxport_settings.ini"
EXECUTABLE = REPO / "build/bin/megamanx4_port"
IMAGE = REPO / "scratch/bin/megamanx4/SLUS_005.61"
OUT = REPO / "scratch/live"
LOG = OUT / "live_play.log"
WAV = OUT / "live_play.wav"
SHOT_DIR = OUT / "shots"

# The debug channel this run needs on. `music_cd`'s tally is a `lucent::debug("x4-music-cd", ...)`
# call, so a run without the channel can observe the state word but NOT the owner being reached — and
# "the state word did not move" and "the owner was never offered the leaf" are different findings.
MUSIC_CD_CHANNEL = "x4-music-cd"
# The per-field, read-only input-path observer in game/core/input_path.cpp. It prints one line per
# DELIVERED FIELD (two: one either side of Pad::serviceFrame), naming every stage of the path from
# the REPL mask through the framework's BIOS-pad gate to the guest's own libpad packet buffer. Without
# it this tool can only read the LAST stage from outside, which is a symptom and not a defect.
#
# It is opt-in (`--input-path-trace`) because it is O(fields) lines, and a run that leaves it off must
# SAY it is off: a report with no observer lines then means "not measured", which is the difference
# between a broken input path and an unasked question.
INPUT_PATH_CHANNEL = "x4-input-path"
SERVER_TIMEOUT_PREFIX = "(debug server:"
# The libpad packet's button halfword when nothing is pressed. ACTIVE LOW, so an untouched pad reads
# 0xFFFF and a held button is that word with the button's bit CLEARED. This is the value the tap
# witness compares against, and it is named because "the word was 0xFFFF" and "the word was not read"
# are different findings.
IDLE_ACTIVE_LOW = 0xFFFF

# The census is a fixed set of contiguous byte reads. `misc_objects` (0x1800 bytes) and the raw pad
# buffer are NOT in the per-poll set: the first would need 24 reads, the second only matters when a tap
# is issued. Both are read on demand, and the report says so rather than implying full coverage.
POLL_READS = (
    (prompts.GAME_INFO, prompts.GAME_INFO_PROBE_BYTES, "game_info + handshake"),
    (prompts.CD_PROBE_BASE, prompts.CD_PROBE_BYTES, "CD machine state / error / result"),
    (prompts.STREAM_PROBE_BASE, prompts.STREAM_PROBE_BYTES, "music-active + guest field counter"),
    (prompts.ENGINE_PROBE_BASE, prompts.ENGINE_PROBE_BYTES, "engine_obj stage/substage"),
    (prompts.PAD_HELD, prompts.PAD_PROBE_BYTES, "pad 1 held / previous / pressed"),
    # The raw libpad packet word is read EVERY poll, not only around a tap. It is the only level of
    # the input chain that says whether a pad is connected and idle, and a census that omits it cannot
    # tell "no edge was offered" from "no pad is attached" — which are different findings about the
    # title. One extra round trip per poll is the price of that, and it is the same price as any other
    # cell this census claims.
    (prompts.PAD_BUFFER, 4, "libpad packet: status, id and the active-low button halfword"),
    (prompts.PLAYER, prompts.PLAYER_PROBE_BYTES, "player object lens"),
)


SCENE_TOTALS = re.compile(
    r"totals:\s*poly=(-?\d+)\s+rect=(-?\d+)\s+line=(-?\d+)\s+fill=(-?\d+)\s+vramcopy=(-?\d+)\s+"
    r"upload=(-?\d+)\s+env=(-?\d+)")


def scene_prims(reply: str) -> tuple[int, str]:
    """The guest's classified display-list total, and the verbatim totals line.

    "There is a scene on screen" is a statement about what the guest SUBMITTED, and the endpoint already
    classifies it. This run's first capture proved the alternative does not work: a post-movie present
    at frame 3,619 carried 14,276 distinct colours at 98.51% non-black and was uninitialised VRAM, read
    one instruction after the guest segfaulted. A colour count cannot tell a scene from noise, so the
    number that decides it is the prim count, and the colour count is still reported beside it.

    A reply with no totals line yields -1, which is NOT zero: an unread display list must not read as
    "the guest drew nothing"."""
    line = next((line for line in reply.splitlines() if "totals:" in line), "")
    match = SCENE_TOTALS.search(line)
    if not match:
        return -1, line.strip()
    return sum(int(value) for value in match.groups()), line.strip()


class Refusal(SystemExit):
    """A run that cannot honestly report the thing it was asked to report."""


# ── the per-field input-path observer, parsed ────────────────────────────────────────────────
#
# game/core/input_path.cpp prints one line per delivered field, one either side of
# Pad::serviceFrame, in exactly this shape. The PRE-service line is not a duplicate: the tap
# countdown is decremented INSIDE serviceFrame, so the pre-service `tap_n` is the only reading of
# "did this field consume a tap count", and the post-service `buttons` is this field's resolved
# mask. Pairing the two is what makes a per-field verdict correct instead of off by one — reading
# only the post-service line would call the field that consumed the LAST count an idle field and
# silently drop the final frame of every edge.
#
# Every stage is compared against the value the PREVIOUS stage produced, so the verdict names the
# FIRST stage that disagrees rather than the first stage that looks wrong. A stage that cannot be
# evaluated is reported as NOT COMPARED, never folded into "correct".
#
# Deliberately NOT anchored at the start of the line: lucent prefixes each record with its channel
# name, and the reader is selected by the channel being present in the line. Anchoring would make
# every real record a "skipped" line, which is the silent-drop failure this parser counts against.
# SELECT BY THE LOG'S CHANNEL TAG, not by the channel name appearing anywhere in the line. The first
# reader used a substring test, and it counted the framework's own config echo — two lines of
# "[cfg] active: PSXPORT_DEBUG=x4-music-cd,x4-input-path ..." — as observer records it could not parse,
# which put a phantom "2 line(s) skipped" into a report about the input path. A channel tag is a
# bracketed field the logger owns, so this matches records and not prose about them.
INPUT_PATH_TAG = re.compile(rf"(?:^|\]\s)\[{re.escape(INPUT_PATH_CHANNEL)}\]\s")

INPUT_PATH_LINE = re.compile(
    r"(?P<phase>pre-service|post-service): "
    r"vbl=(?P<vbl>\d+) "
    r"repl\(on=(?P<on>\w+) tap=0x(?P<tap>[0-9A-Fa-f]{4}) tap_n=(?P<tap_n>-?\d+) "
    r"hold=0x(?P<hold>[0-9A-Fa-f]{4})\) "
    r"resolved\(buttons=0x(?P<buttons>[0-9A-Fa-f]{4})\) "
    r"gate\(initialized=(?P<init>\w+) irq_started=(?P<irq>\w+) shouldService=(?P<gate>\w+)\) "
    r"guest\(slot0_bytes=0x(?P<slot0_bytes>[0-9A-Fa-f]{8}) "
    r"slot0_buttons=0x(?P<slot0_buttons>[0-9A-Fa-f]{4}) "
    r"slot1_bytes=0x(?P<slot1_bytes>[0-9A-Fa-f]{8}) "
    r"slot1_buttons=0x(?P<slot1_buttons>[0-9A-Fa-f]{4}) "
    r"held=0x(?P<held>[0-9A-Fa-f]{4}) pressed=0x(?P<pressed>[0-9A-Fa-f]{4})\)$"
)

# The stages of the path, in the order the edge travels them, as the PER-FIELD observer can compare
# them. `endpoint` is NOT here: it is measured by this tool from the reply to `tap`, once per
# command, and has no per-field reading. Folding it into this list would make it compare `False`
# against every field (there is no per-field value to compare) and report it as the broken stage of
# every run, which is how a reader that cannot answer becomes a reader that always answers wrongly.
FIELD_STAGES = ("repl", "resolved", "gate", "guest")
# What a break at the FIRST per-field stage means for the stage before it: the endpoint accepted the
# command and the mask existed, so `endpoint` is genuinely the last correct stage in that case.
STAGE_BEFORE = {"repl": "endpoint", "resolved": "repl", "gate": "resolved", "guest": "gate"}


def truthy(token: str) -> bool:
    """A boolean as the product PRINTS it, which is not one spelling.

    The observer's line mixes two host types, and the product formats each by its own type: `Pad`/`Hle`
    members that are declared `int` print as `1`/`0`, and the ones declared `bool` print as
    `true`/`false`. Reading either as the other's spelling is a reader that silently answers "no" for
    every true value, and it is exactly the failure this function exists to prevent: the first live
    reading of this observer was compared with `== "true"` against a `repl(on=1)` field, every edge
    field came back "broken at repl", and the run published "the last stage correct is endpoint" for
    a product that had in fact written the tap into the guest's own packet buffer. The fixture in
    `--selftest` is pinned to the SHIPPING spelling of each field, and both spellings are exercised,
    so a change to either the formatter or the parser is caught here rather than in a run.
    """
    return token.strip().lower() in {"1", "true"}


def parse_input_path_counts(log: Path) -> tuple[list[dict], int, int]:
    """Every observer line, how many did not match, and how many disagreed with themselves.

    A line that does not match is counted, never dropped in silence: a log format change would
    otherwise show up as "the observer reported nothing", which is the same shape as "the input path
    produced no edge" — the exact confusion this whole measurement exists to remove.
    """
    parsed: list[dict] = []
    skipped = 0
    refused = 0
    if not log.is_file():
        # An absent LOG is not an empty answer. It is reported as a log this reader could not open, so
        # a caller cannot tell "the run wrote no observer lines" from "there was no log to read" by
        # looking at a zero — the report distinguishes them by the channel state it also carries.
        return parsed, skipped, refused
    for line in log.read_text(errors="replace").splitlines():
        if not INPUT_PATH_TAG.search(line):
            continue
        match = INPUT_PATH_LINE.search(line.strip())
        if not match:
            skipped += 1
            continue
        row = match.groupdict()
        # The line carries the packet's four bytes AND the button halfword read back out of them.
        # Slice the bytes here and compare: if the two disagree the line is not a packet record this
        # reader can interpret, and a reader that picks one of them would be choosing a byte order
        # rather than measuring one. That disagreement is counted as a line this reader REFUSED, and
        # it is the exact error the frontier probe shipped in both directions.
        bytes0 = int(row["slot0_bytes"], 16)
        sliced = (bytes0 >> 16) & 0xFFFF
        if sliced != int(row["slot0_buttons"], 16):
            refused += 1
            continue
        parsed.append({
            "phase": row["phase"],
            "vbl": int(row["vbl"]),
            "on": truthy(row["on"]),
            "tap": int(row["tap"], 16),
            "tap_n": int(row["tap_n"]),
            "hold": int(row["hold"], 16),
            "buttons": int(row["buttons"], 16),
            "initialized": truthy(row["init"]),
            "irq_started": truthy(row["irq"]),
            "gate": truthy(row["gate"]),
            "slot0_bytes": bytes0,
            "slot0_buttons": int(row["slot0_buttons"], 16),
            "slot1_buttons": int(row["slot1_buttons"], 16),
            "held": int(row["held"], 16),
            "pressed": int(row["pressed"], 16),
        })
    return parsed, skipped, refused


def parse_input_path_log(log: Path) -> tuple[list[dict], int]:
    """Every observer line, and how many lines this reader would not or could not use."""
    parsed, skipped, refused = parse_input_path_counts(log)
    return parsed, skipped + refused


def input_path_verdict(rows: list[dict], endpoint_taps: int) -> dict:
    """Where the edge died: the LAST stage at which it was still correct, over every field of every
    edge the observer saw.

    Pairing is by consecutive pre/post lines, and an UNPAIRED line is counted and reported rather
    than treated as a passing field — a half-printed run must not read as a delivered edge.

    For each field whose PRE-service `tap_n` was above zero (that is the field the tap countdown
    decided), the expected mask for that field is `repl_tap`, and the stages are compared in order:

        repl      the drive was armed at all (`on`) and carried a mask that is not the idle word
        resolved  post-service `buttons` == the mask the pre-service line says this field used
        gate      the framework's own BIOS-pad gate says the write is permitted
        guest     the guest's slot-0 packet button halfword == the resolved mask

    A field whose LAST stage is `guest` is an edge that reached guest memory. A field that never
    gets there reports the first stage that disagreed, and the run's answer is the EARLIEST such
    stage across all edge fields — the first broken link is the one that explains the rest.
    """
    fields: list[dict] = []
    unpaired = 0
    pending: dict | None = None
    for row in rows:
        if row["phase"] == "pre-service":
            if pending is not None:
                unpaired += 1
            pending = row
            continue
        if pending is None:
            unpaired += 1
            continue
        pre, post = pending, row
        pending = None
        if pre["tap_n"] > 0:
            fields.append({"pre": pre, "post": post, "expected": pre["tap"], "stages": {}})
    # A run that stopped between the two halves of a field left a pre-service line with no partner.
    # That is a HOLE, and a hole that was silently dropped is a field nobody compared — so it is
    # counted here rather than forgotten at the end of the loop.
    if pending is not None:
        unpaired += 1

    for entry in fields:
        pre, post, expected = entry["pre"], entry["post"], entry["expected"]
        stages = entry["stages"]
        stages["repl"] = bool(pre["on"] and expected != IDLE_ACTIVE_LOW)
        stages["resolved"] = post["buttons"] == expected
        stages["gate"] = post["gate"]
        # The guest's own slot-0 button halfword, taken from the value the observer read back with
        # mem_r16 at +2 — the guest's own read of the same four bytes, not this tool's slice of them.
        stages["guest"] = post["slot0_buttons"] == post["buttons"]

    broken_at: str | None = None
    for stage in FIELD_STAGES:
        if any(not entry["stages"].get(stage, False) for entry in fields):
            broken_at = stage
            break
    last_correct = None
    if broken_at is not None:
        last_correct = STAGE_BEFORE[broken_at]

    delivered = [entry for entry in fields if entry["stages"].get("guest")]
    # The guest's OWN decoded words across the edge, in the convention the guest itself uses. The
    # packet word is ACTIVE LOW (idle 0xFFFF, a pressed bit CLEARED); the guest's router converts it
    # to its own pressed-bit convention, so a non-zero `pressed` here is the guest acknowledging an
    # edge, and it is the deepest level this surface can reach without asking the guest a question.
    pressed_values = sorted({entry["post"]["pressed"] for entry in fields})
    held_values = sorted({entry["post"]["held"] for entry in fields})
    return {
        "edge_fields": len(fields),
        "unpaired_lines": unpaired,
        "endpoint_taps": endpoint_taps,
        "broken_at": broken_at,
        "last_correct_stage": last_correct,
        "delivered_fields": len(delivered),
        "gate_open_fields": sum(1 for entry in fields if entry["post"]["gate"]),
        "initialized": sorted({entry["post"]["initialized"] for entry in fields}),
        "irq_started": sorted({entry["post"]["irq_started"] for entry in fields}),
        "guest_pressed_values": pressed_values,
        "guest_held_values": held_values,
        "edge_field_span": ([fields[0]["pre"]["vbl"], fields[-1]["post"]["vbl"]] if fields else None),
        "sample": [
            {
                "vbl": entry["pre"]["vbl"],
                "expected": f"0x{entry['expected']:04X}",
                "resolved": f"0x{entry['post']['buttons']:04X}",
                "gate": entry["post"]["gate"],
                "guest_packet_bytes": f"0x{entry['post']['slot0_bytes']:08X}",
                "guest_packet": f"0x{entry['post']['slot0_buttons']:04X}",
                "guest_held": f"0x{entry['post']['held']:04X}",
                "guest_pressed": f"0x{entry['post']['pressed']:04X}",
            }
            for entry in fields[:4]
        ],
    }


def ask(client: LiveClient, line: str, *, retries: int = 3) -> str:
    """One command, refusing the three replies that are NOT answers.

    The server's own 4-second timeout notice is a sentence about the debug server. An empty reply is a
    socket that closed mid-run. A `? <line>` reply means this BINARY does not implement the command,
    which is a fact about the build, not a zero.

    A timeout is retried rather than fatal, because a single stalled frame is a legitimate thing for a
    port to do mid-movie — but it is COUNTED, because a census with silent holes is a census whose
    gaps a reader cannot see.
    """
    last = ""
    for attempt in range(retries):
        reply = client.send(line)
        if reply.startswith(SERVER_TIMEOUT_PREFIX):
            last = reply.strip()
            continue
        if not reply.strip():
            raise Refusal(f"REFUSED: `{line}` came back EMPTY — the endpoint closed or stopped "
                          f"answering mid-run. Nothing below this line was measured.")
        if reply.lstrip().startswith("?"):
            raise Refusal(f"REFUSED: this product does not implement `{line.split()[0]}` "
                          f"({reply.strip()}). The endpoint's command set is the BINARY's, so this is "
                          f"a stale build, not a zero: rebuild the tree this run used, or point "
                          f"--executable at a build made against a framework that has the command.")
        return reply
    raise Refusal(f"REFUSED: the endpoint timed out servicing `{line}` on all {retries} attempt(s) "
                  f"(last notice: {last}). The product was not presenting.")


def read_bytes(client: LiveClient, address: int, count: int, *, tolerate_hole: bool = False) -> bytes:
    """One guest byte read. The reply is `ADDR: HH HH ...`; the ADDRESS PREFIX IS NOT the data, so the
    split is on the last colon.

    A reply carrying fewer bytes than asked for RAISES, because a silently-short read is how a failed
    probe becomes a confident table — and the framework has already been bitten by exactly that
    (`psxport/AGENTS.md`, "a short answer must declare itself"). `tolerate_hole` is for the two reads
    that are genuinely best-effort — the multi-command `misc_objects` sweep and the pad words sampled
    around a hold window — and it returns b"" for BOTH causes, a short answer and an exhausted
    timeout, so every caller of it reports the number of records or words it actually got."""
    reply = ask(client, f"r {address:08X} {count}")
    try:
        payload = reply.rsplit(":", 1)[1].split()
    except IndexError as error:
        raise Refusal(f"REFUSED: `r {address:08X} {count}` returned {reply.strip()!r}") from error
    if len(payload) < count:
        if not tolerate_hole:
            raise Refusal(f"REFUSED: asked for {count} byte(s) at 0x{address:08X} and got "
                          f"{len(payload)}. The REST WAS NOT READ — it is not zero.")
        return b""
    try:
        return bytes(int(value, 16) for value in payload[:count])
    except ValueError as error:
        raise Refusal(f"REFUSED: `r {address:08X} {count}` returned unparsable bytes "
                      f"{payload[:8]}") from error


def frame_of(client: LiveClient) -> int:
    """REAL presented frames. This title has no temporal path (`RenderCapabilities::widescreenOnly()`,
    docs/project-state.md S005), so `interp` is expected to stay 0 and `total` is checked against
    `frame` — the run reports both so a product that had grown an in-between would be visible."""
    reply = ask(client, "frame")
    values = {}
    for token in reply.split():
        key, equals, value = token.partition("=")
        if equals and value.lstrip("-").isdigit():
            values[key] = int(value)
    if "frame" not in values:
        raise Refusal(f"REFUSED: the `frame` reply carried no counter: {reply.strip()!r}")
    return values["frame"]


def presented(client: LiveClient) -> dict:
    reply = ask(client, "frame")
    found = {}
    for token in reply.split():
        key, equals, value = token.partition("=")
        if equals and value.lstrip("-").isdigit():
            found[key] = int(value)
    if "total" not in found:
        raise Refusal(f"REFUSED: the `frame` reply carries no `total=` counter, so this build cannot "
                      f"be asked about presentation cadence: {reply.strip()!r}")
    return found


def guest_execution(client: LiveClient) -> tuple[dict, str]:
    """The dynarec's own denominators, asked of the running process.

    The reply carries TWO lines, `guest:` and `fallback:`, and BOTH name `calls` and `instructions`.
    They stay in separate dicts because a merged one answers both questions with whichever line was
    parsed last: on a run with zero fallback, the merged reading of `instructions` is the count the
    DYNAREC executed. The raw reply is returned too, because a parsed number nobody can check is a
    number nobody can refute."""
    reply = ask(client, "guest")
    counters: dict[str, dict[str, int]] = {}
    for line in reply.splitlines():
        prefix, separator, rest = line.partition(":")
        prefix = prefix.strip()
        if not separator or prefix not in ("guest", "fallback"):
            continue
        counters.setdefault(prefix, {})
        for token in rest.split():
            key, equals, value = token.partition("=")
            if equals:
                counters[prefix][key] = int(value) if value.isdigit() else -1
    if "guest" not in counters:
        raise Refusal(f"REFUSED: the `guest` reply carried no counters: {reply.strip()!r}")
    return counters, reply.strip()


def effective_configuration(client: LiveClient) -> dict:
    """The configuration the product is ACTUALLY running, asked of the configuration owner. A boot log
    line is a statement about the past; this is the answer as it stands. `cvars` also carries which
    LAYER each value came from, which is what says whether a run tested what it meant to test, and it
    names the env variables that matched NO knob — the ones that did nothing at all."""
    reply = ask(client, "cvars")
    knobs: dict[str, str] = {}
    layers: dict[str, str] = {}
    for line in reply.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[2] != "=":
            continue
        layer = next((index for index in range(3, len(fields)) if fields[index].startswith("[")), None)
        if layer is None:
            continue
        knobs[fields[0]] = " ".join(fields[3:layer])
        layers[fields[0]] = fields[layer].strip("[]")
    return {
        "knobs": knobs,
        "layers": layers,
        "audit": next((line.strip() for line in reply.splitlines()
                       if line.startswith("env audit:")), "(no audit line)"),
        "unmatched": sorted({line.split("UNKNOWN ", 1)[1].split()[0]
                             for line in reply.splitlines() if line.strip().startswith("UNKNOWN ")}),
    }


def read_misc_objects(client: LiveClient) -> tuple[int, int]:
    """`misc_objects` is 96 records of 0x60 = 6144 bytes and the endpoint serves 256 per command, so it
    is read in 24 commands. Returns the RAW BYTES, and the counting rule is
    `title_prompts.count_misc_populated` — one implementation of that rule, not two.

    It is not in the per-poll census because 24 round trips per poll would dominate the poll's cost,
    and because issue 0028's measurement of it is a post-movie figure, not a per-field one."""
    wanted = prompts.MISC_RECORD_COUNT * prompts.MISC_RECORD_SIZE
    payload = b""
    while len(payload) < wanted:
        chunk = read_bytes(client, prompts.MISC_OBJECTS + len(payload),
                           min(256, wanted - len(payload)), tolerate_hole=True)
        if not chunk:
            break
        payload += chunk
    return prompts.count_misc_populated(payload), len(payload) // prompts.MISC_RECORD_SIZE


def capture(client: LiveClient, path: Path) -> dict | None:
    """Photograph what is PRESENTED, and measure the picture with the framework's own reader.

    The three numbers are the ones that can tell a running guest from a frozen one: the DISTINCT
    COLOUR COUNT (the measured park is exactly 2), the non-black share, and — for every capture after
    the first — the fraction of pixels that differ from the previous capture. A non-black share alone
    cannot: this title's park clear colour is RGB(8,8,16), not black, so "61.89% non-black" reads as
    "something is on screen" for a picture that never changes (docs/issues/0028)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    try:
        reply = ask(client, f"shot {path}").strip()
    except Refusal:
        return None
    if not path.is_file():
        return None
    try:
        width, height, pixels = read_image(path)
    except (Unreadable, OSError) as error:
        return {"path": path, "reply": reply, "bytes": path.stat().st_size, "error": str(error)}
    total = width * height
    colours: dict[str, int] = {}
    non_black = 0
    for index in range(0, len(pixels), 3):
        pixel = pixels[index:index + 3]
        key = pixel.hex()
        colours[key] = colours.get(key, 0) + 1
        if key != "000000":
            non_black += 1
    top = sorted(colours.items(), key=lambda item: -item[1])[:3]
    return {
        "path": path,
        "reply": reply,
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "total": total,
        "colours": len(colours),
        "non_black": non_black,
        "non_black_share": non_black / total if total else 0.0,
        "top": top,
        "digest": hashlib.md5(pixels).hexdigest(),
        "pixels": pixels,
    }


def picture_diff(previous: dict, current: dict) -> dict | None:
    """Pixels that DIFFER between two captures, with their denominator and their bounding box. "0.4% of
    the frame changes" is a much weaker claim than "the 2,394 pixels that change are a 3-row band at
    y=717", because the second names what is moving."""
    if not previous or not current or previous.get("error") or current.get("error"):
        return None
    first, second = previous["pixels"], current["pixels"]
    if len(first) != len(second):
        return {"different": None, "reason": "captures are different sizes"}
    width = current["width"]
    differing = 0
    total_delta = 0
    x0, y0, x1, y1 = width, current["height"], -1, -1
    for index in range(0, len(first), 3):
        delta = (abs(first[index] - second[index]) + abs(first[index + 1] - second[index + 1])
                 + abs(first[index + 2] - second[index + 2]))
        if not delta:
            continue
        differing += 1
        total_delta += delta
        pixel = index // 3
        x, y = pixel % width, pixel // width
        x0, x1 = min(x0, x), max(x1, x)
        y0, y1 = min(y0, y), max(y1, y)
    return {
        "different": differing,
        "of": current["total"],
        "share": differing / current["total"] if current["total"] else 0.0,
        "mean": (total_delta / (3 * differing)) if differing else 0.0,
        "box": None if y1 < 0 else (x0, y0, x1 - x0 + 1, y1 - y0 + 1),
    }


def wav_report(path: Path) -> dict:
    """What the headless audio sink actually captured, from the file's own header.

    `PSXPORT_WAV` is the headless sink: a real product run writes a device, and an agent run may not.
    A WAV that is 0 bytes, or whose peak sample is zero, is SILENCE and is reported as silence — this
    title's measured post-movie capture was 66.7 s of movie XA rather than BGM, so a non-silent file
    is not by itself evidence of music."""
    if not path.is_file():
        return {"present": False}
    size = path.stat().st_size
    result: dict = {"present": True, "bytes": size}
    if size < 44:
        result["verdict"] = "too short to be a WAV; the sink wrote nothing"
        return result
    with path.open("rb") as handle:
        header = handle.read(12)
        if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            result["verdict"] = "not a RIFF/WAVE file"
            return result
        rate = channels = bits = 0
        while True:
            chunk = handle.read(8)
            if len(chunk) < 8:
                break
            name, size_field = struct.unpack("<4sI", chunk)
            if name == b"fmt ":
                body = handle.read(size_field)
                _, channels, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            elif name == b"data":
                break
            else:
                handle.seek(size_field + (size_field & 1), 1)
    result.update(rate=rate, channels=channels, bits=bits)
    if rate and channels and bits == 16:
        seconds = (size - 44) / float(rate * channels * 2)
        result["seconds"] = seconds
        peak = 0
        samples = 0
        with path.open("rb") as handle:
            handle.seek(44)
            while True:
                block = handle.read(65536)
                if not block:
                    break
                count = len(block) // 2
                samples += count
                values = struct.unpack(f"<{count}h", block[:count * 2])
                local = max((abs(value) for value in values), default=0)
                peak = max(peak, local)
        result["peak"] = peak
        result["samples"] = samples
        result["verdict"] = ("SILENT (every sample is zero)" if peak == 0
                             else f"non-silent, peak {peak}/32767")
    else:
        result["verdict"] = f"unsampled layout ({bits}-bit, {channels}ch, {rate}Hz)"
    return result


def running_instances() -> list[str]:
    """Any other product instance on this machine. There is one shared product slot, and two instances
    would also make the two runs' frame counters incomparable."""
    listing = subprocess.run(["ps", "-eo", "pid,etimes,args"], capture_output=True, text=True,
                             check=True).stdout
    return [line.strip() for line in listing.splitlines()
            if "megamanx4_port" in line and "ps -eo" not in line]


def launch(port: int, sink: str, wide: str, log: Path, wav: Path,
           input_path_trace: bool = False) -> subprocess.Popen:
    """The product: headless, silent, unpaced, live endpoint on this run's own port.

    `agent_environment` is the framework's one policy and it REFUSES without a named settings file,
    which is correct: an unset PSXPORT_SETTINGS hands the product its own working-directory discovery,
    so the run would be configured by whichever untracked file sits beside it.

    Four things are added here, and each is a measurement requirement rather than a convenience:

    * PSXPORT_DEBUG_SERVER names the live endpoint, and its presence LIFTS the headless frame cap
      (native_boot.cpp), which is what lets a driven run last as long as it needs.
    * PSXPORT_DEBUG carries the channel names, and this run's is the `x4-music-cd` channel the falsifier
      needs. The endpoint's `debug` command could set it mid-run, which would leave the movie phase
      unobserved by the very channel the falsifier reads. `--input-path-trace` adds the title's
      per-field input-path observer channel to the same list, so the stages between the endpoint and
      the guest's own packet buffer are sampled once per DELIVERED FIELD rather than once per poll.
    * PSXPORT_PRESENT_SINK fixes the readback size. Headless has no window, so without it there is no
      drawable to present into; 1284x720 is the 4/3 multiple of this title's measured 428-wide widescreen
      projection (960x720 is the same ratio on the 4:3 leg), so both legs are 4:3-scaled.
    * PSXPORT_WAV is the headless audio sink. Never a device.

    The base mapping is the process environment, not an empty one: HOME and the loader paths are how
    the product finds a Vulkan ICD and a writable config, and dropping them turns a headless run into a
    different failure. `agent_environment` overwrites the three agent keys and sets PSXPORT_SETTINGS
    either way, so inheriting the caller's environment cannot leak a presentation knob into the run.
    """
    environment = agent_environment(dict(os.environ), settings=SETTINGS)
    environment.pop("PSXPORT_REPL", None)
    environment.pop("PSXPORT_NATIVE_FRAMES", None)
    environment.update({
        "PSXPORT_DEBUG_SERVER": str(port),
        "PSXPORT_DEBUG": (f"{MUSIC_CD_CHANNEL},{INPUT_PATH_CHANNEL}" if input_path_trace
                          else MUSIC_CD_CHANNEL),
        "PSXPORT_PRESENT_SINK": sink,
        "PSXPORT_WAV": str(wav),
        "PSXPORT_X4_WIDESCREEN": wide,
        "PSXPORT_WATCHDOG": "3600",
        "PSXPORT_LOG_FILE": str(log),
    })
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("")  # the logger appends, so "this run" is truncated first
    if wav.exists():
        wav.unlink()
    for required in (EXECUTABLE, IMAGE):
        if not required.is_file():
            raise Refusal(f"REFUSED: {required} is missing — NOTHING WAS RUN. Build with "
                          f"`cmake --build build --target megamanx4_port -j$(nproc)` and provision the "
                          f"authenticated executable first; this tool does not build and does not extract.")
    return subprocess.Popen([str(EXECUTABLE), str(IMAGE)], cwd=REPO, env=environment,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def connect(port: int, seconds: float, log: Path) -> LiveClient:
    deadline = time.monotonic() + seconds
    last: OSError | None = None
    while time.monotonic() < deadline:
        try:
            return LiveClient(port)
        except OSError as error:
            last = error
            time.sleep(0.05)
    raise Refusal(f"REFUSED: the live endpoint never answered on 127.0.0.1:{port} within {seconds:.0f}s "
                  f"({last}). The product's own log is {log}.")


class Session:
    """The play-through. Every step counts what it did, so a run that never got past the movie says so
    with a number rather than a zero."""

    def __init__(self, client: LiveClient) -> None:
        self.client = client
        self.screens: list[prompts.Screen] = []
        self.frames: list[int] = []
        self.observations = 0
        self.timeouts = 0
        self.answers = 0
        self.pad_commands = 0
        self.shots: list[dict] = []
        self.leg_frames: dict[str, int] = {}
        self.tap_log: list[str] = []
        self.hold_log: list[dict] = []
        # Every DISTINCT value the guest's own pad words took while a tap was being witnessed, and how
        # many taps produced no change in the packet word at all.
        self.pad_words_seen: dict[str, set[int]] = {}
        self.tap_unwitnessed = 0
        self.tap_witnessed = 0
        # Whether the run asked for the per-field input-path observer. Recorded here, not inferred
        # from the log, so a run whose channel was off cannot be read as a run that measured nothing
        # and found nothing wrong.
        self.input_path_trace = False
        # The tap length this run issues, and what one endpoint read costs in presented frames. Both
        # are denominators: a read that costs more presented frames than a tap spans fields cannot
        # witness that tap, and the report has to be able to say so.
        self.tap_fields = 4
        self.read_cost_samples = 0
        self.read_cost_frames = 0
        # Read-back samples actually taken, so the report can divide the commands it issued by the
        # samples it drew rather than implying one sample per command.
        self.tap_probes = 0
        # What the product said about ITSELF, sampled the moment the endpoint answered and kept. A run
        # whose subject then dies still has these; asking again at the end would find a closed socket,
        # and a driver that reports nothing because its subject crashed has thrown away the census it
        # spent the whole run taking.
        self.opening: dict = {}
        # How the run ENDED. `None` means the window was spent normally; anything else is a recorded
        # outcome, and the report prints it before anything else so a crash is never read as a verdict.
        self.stopped: str | None = None
        self.stopped_at_frame: int | None = None

    def sample_opening_state(self) -> None:
        """Configuration, dynarec counters and the present counter, taken while the product is alive,
        and RE-taken on every later census poll so the report's numbers describe the run and not its
        first second.

        `guest_execution` returns the VERBATIM reply alongside the parsed dicts, which is what makes a
        kept sample checkable by a reader rather than merely quotable. `cvars` is only read here and not
        per poll: it is a statement about the run's configuration, which does not change."""
        self.opening = {
            "frame": presented(self.client),
            "guest": guest_execution(self.client),
            "configuration": effective_configuration(self.client),
        }

    def alive(self) -> bool:
        try:
            frame_of(self.client)
            return True
        except (OSError, Refusal):
            return False
    # ---- observation ----------------------------------------------------------------------------
    def census(self) -> tuple[prompts.Screen, int, int]:
        """One census: the whole front-end state machine, the pad trio, the raw pad word, the player
        lens, and the presented-frame interval it was taken over.

        The read list and the decoder's required cells must agree, and they are checked against each
        other here rather than trusted: a poll that omitted a read the decoder demands raised
        `ValueError` on the FIRST observation of the first run, which is a cheap way to find out and an
        expensive way not to — a census that decodes with a cell missing would report it as zero."""
        for address, count, label in POLL_READS:
            if address not in prompts.PROBE_REQUIREMENTS:
                raise Refusal(f"REFUSED: this poll reads {label} at 0x{address:08X} but "
                              f"title_prompts does not require that cell, so decoding would ignore it")
        for address, count in prompts.PROBE_REQUIREMENTS.items():
            if not any(entry[0] == address for entry in POLL_READS):
                raise Refusal(f"REFUSED: title_prompts REQUIRES the cell at 0x{address:08X} "
                              f"({count} byte(s)) but this poll does not read it. Nothing was measured; "
                              f"add it to POLL_READS rather than relaxing the decoder, because a "
                              f"required cell that is not read is a cell reported as zero.")
        frame_before = frame_of(self.client)
        blocks: dict[int, bytes] = {}
        for address, count, _ in POLL_READS:
            try:
                blocks[address] = read_bytes(self.client, address, count)
            except Refusal as error:
                if "timed out" not in str(error):
                    raise
                raise Refusal(f"census read at 0x{address:08X} timed out on all attempts; this "
                              f"observation is a HOLE, not a zero") from error
        try:
            prims, totals = scene_prims(ask(self.client, "scene"))
            screen = prompts.decode(blocks, scene_prims=prims, scene_totals=totals)
        except Refusal as error:
            if "timed out" not in str(error):
                raise
            # A display list that could not be read leaves the prim count at -1, which the scene leg
            # treats as "not read" rather than "no scene".
            screen = prompts.decode(blocks)
        frame_after = frame_of(self.client)
        self.observations += 1
        # The dynarec's own counters, sampled on EVERY poll and keeping the latest. Sampled once at
        # connect they describe a three-frame run, which is not a denominator for a 3,600-frame
        # play-through; sampled per poll the last successful value is the closest reading to the end of
        # the run that a product which may die at any moment can leave behind.
        try:
            self.opening["guest"] = guest_execution(self.client)
            self.opening["frame"] = presented(self.client)
        except (OSError, Refusal):
            pass  # the run is ending; the last good sample stands and the report says when it was taken
        return screen, frame_after, frame_before

    def record(self, screen: prompts.Screen, frame: int) -> None:
        self.screens.append(screen)
        self.frames.append(frame)

    # ---- input ----------------------------------------------------------------------------------
    def tap(self, button: str, frames: int, screen: prompts.Screen) -> None:
        """A pad EDGE, WITNESSED at the resolution it happens at.

        `tap` and a press+release inside ONE frame are not the same thing: the latter can be serviced
        inside a single frame and be invisible to the guest, which is the hazard this endpoint's own
        client documents. So the edge spans `frames` presented frames.

        And then it is WITNESSED, because the alternative is measuring a 4-frame edge with a poll that
        samples every ~100 presented frames and reporting "the pad never changed" — which is what the
        first three runs of this tool did, and it is indistinguishable from a tap that was never
        delivered. Immediately after issuing the tap this reads the guest's own pad words back and
        records every DISTINCT value it saw. A tap that is delivered must show up in `packet`; a tap
        that is delivered AND decoded must also show up in `pressed`.

        WHAT IT NOW ALSO MEASURES is what one of those reads COSTS. "The endpoint services one command
        per presented frame" is an upper bound on how OFTEN it is served, not a lower bound on how long
        a read takes: MEASURED 2026-09-27 on this title, 16 packet reads cost 287 presented frames, so
        one read spans ~18 fields and a 4-field tap is over before the first read can land. That is why
        the `INPUT VERDICT` this tool used to print was not a conclusion its own surface could support,
        and why `measure_read_cost` now reports the ratio and the delivery verdict comes from the
        per-field observer instead.

        This costs `frames + 6` round trips, which is presented frames of real presented frames — the
        same frames the game is playing."""
        ask(self.client, f"tap {button} {frames}")
        self.answers += 1
        self.pad_commands += 1
        seen: dict[str, set[int]] = {"packet": set(), "held": set(), "pressed": set()}
        # The read-back does NOT have to span the edge — it has to LAND IN it. One read costs ~13
        # presented frames on this title, so a 40-field edge needs about three reads to be sampled and
        # a `frames + 6` probe loop would spend 46 of them — which is more presented frames than the
        # whole route budget, and in the 2026-09-28 measurement it walked the run straight into the
        # stage-load fault. So the probe count is bounded and the bound is a number, not a formula on
        # the edge: enough samples to land inside an edge several reads wide, and counted either way.
        probes = min(frames + 2, 8)
        self.tap_probes += probes
        for _ in range(probes):
            probe = self.verify_tap_landed()
            for key in seen:
                if probe.get(key) is not None:
                    seen[key].add(probe[key])
        for key, values in seen.items():
            if values:
                self.pad_words_seen.setdefault(key, set()).update(values)
        self.tap_log.append(
            f"{button} x{frames} at presented frame {self.frames[-1] if self.frames else '?'}"
            f" with unkD={screen.accept_input} game_info={screen.game_state}/{screen.sub_state};"
            f" over {probes} read-back sample(s) of the {frames}-field edge, the guest's own words "
            f"took these values:"
            f" packet(active-low)={sorted(seen['packet'])} held={sorted(seen['held'])}"
            f" pressed={sorted(seen['pressed'])}")
        # IDLE, not merely "empty": the packet word is read every frame of the edge, so a set holding
        # only the idle value means the edge was NOT delivered. The first version of this check tested
        # for an empty set and therefore reported every tap as witnessed, because the idle value is
        # itself an observation.
        if seen["packet"] and seen["packet"] <= {IDLE_ACTIVE_LOW}:
            self.tap_unwitnessed += 1
        else:
            self.tap_witnessed += 1

    def measure_read_cost(self, samples: int = 12) -> float | None:
        """How many PRESENTED FRAMES one endpoint read costs, or None if it could not be measured.

        This is the denominator the tap witness needs and did not have. The witness reads the guest's
        own words back over the span of an edge and concludes from what it sees, which is only sound
        if a read is FINER than the edge. It is not: MEASURED 2026-09-27 on this title, 16 packet
        reads cost 287 presented frames — 17.9 frames per read — while a 4-field tap spans 4. The
        read-back therefore samples the edge at roughly a fifth of its own duration and reports "idle"
        for a tap that was delivered, which is exactly the false negative issue 0030 published.

        So the cost is measured rather than assumed, and the report states whether a read COULD have
        landed inside the edge it was watching. A witness that cannot say this is a witness whose
        negative is meaningless.
        """
        try:
            before = frame_of(self.client)
            for _ in range(samples):
                read_bytes(self.client, prompts.PAD_BUFFER, 4, tolerate_hole=True)
            after = frame_of(self.client)
        except (OSError, Refusal):
            return None
        if samples <= 0:
            return None
        self.read_cost_samples = samples
        self.read_cost_frames = after - before
        return self.read_cost_frames / samples

    def verify_tap_landed(self) -> dict:
        """Did the edge reach the guest's own words, and at which of the two levels?

        `Pad::fillBuffer` (psxport/runtime/psx/pad_input.cpp:66) writes the packet the game polls as
        status, id, then a 16-bit ACTIVE LOW button mask at offset +2 — so the header's first two bytes
        are NOT the input, and an earlier version of this tool read them and reported a constant
        0x4100 in every run, which read exactly like "the taps never arrived". Both levels are
        returned, each named:

        * `packet` — what the host wrote into the guest's libpad buffer. ACTIVE LOW, so idle is 0xFFFF
          and a pressed Start is that word with bit 11 cleared.
        * `held`/`previous`/`pressed` — the guest's own decoded trio, which the guest's input router
          writes FROM that packet.

        An edge can arrive at the first and not the second; that is a finding about the guest's router,
        and reporting only the pair's conjunction would hide which half failed."""
        packet = read_bytes(self.client, prompts.PAD_BUFFER, 4, tolerate_hole=True)
        trio = read_bytes(self.client, prompts.PAD_HELD, prompts.PAD_PROBE_BYTES, tolerate_hole=True)
        return {
            "packet": int.from_bytes(packet[2:4], "little") if len(packet) >= 4 else None,
            "packet_header": packet[:2].hex() if len(packet) >= 2 else None,
            "held": int.from_bytes(trio[0:2], "little") if len(trio) >= 2 else None,
            "previous": int.from_bytes(trio[2:4], "little") if len(trio) >= 4 else None,
            "pressed": int.from_bytes(trio[4:6], "little") if len(trio) >= 6 else None,
        }

    def hold_window(self, buttons: list[str], seconds: float) -> dict:
        """Hold buttons for a wall-clock window while the game runs, and report what moved — in the
        GUEST's words, through the lens this repository already owns. The dynarec's counters are
        sampled across the window too, so "the game kept executing while the picture was sampled" is a
        number rather than an assumption.

        The pad words are sampled BEFORE the press as well, so a run that proves the held word never
        changed has proved the edge did not arrive rather than merely failing to move the player.

        A product that dies INSIDE the window is a recorded outcome, not an exception. This window is
        by far the longest unbroken stretch of endpoint traffic in a run — one `frame` poll per
        50 ms for the whole hold — and this title's measured 0x26010006 stage-load fault lands at
        presented field ~1200-2800, which is exactly where a hold that follows a 2000-frame route
        happens. Measured 2026-09-28: the exception escaped `main`, and the run printed no report at
        all, losing the census, the legs, the taps and the captures it had already measured."""
        try:
            return self._hold_window(buttons, seconds)
        except (OSError, Refusal) as error:
            self.stopped = (f"the product stopped answering the endpoint during the hold window "
                            f"({type(error).__name__}: {str(error).splitlines()[0][:140]})")
            self.stopped_at_frame = self.frames[-1] if self.frames else None
            print(f"[live] {self.stopped} after presented frame {self.stopped_at_frame}. The census, "
                  f"the legs reached, the taps and the captures so far are still reported below, and "
                  f"this hold window is a SKIP rather than a zero: no held input was ever delivered.")
            skipped = {"buttons": buttons, "skipped": True, "moved": False, "player_before": {},
                       "player_after": {}, "seconds": 0.0, "presented_frames": 0,
                       "pad_before": None, "pad_during": {}, "pad_after": {},
                       "guest_before": {}, "guest_after": {}}
            # A skipped window is still a window the run attempted, so it is RECORDED and the report
            # prints it as a skip. A hold the run never mentions is a hold a reader cannot tell from
            # one that was never asked for.
            self.hold_log.append(skipped)
            return skipped

    def _hold_window(self, buttons: list[str], seconds: float) -> dict:
        before_pad = read_bytes(self.client, prompts.PAD_HELD, prompts.PAD_PROBE_BYTES,
                                tolerate_hole=True)
        for button in buttons:
            ask(self.client, f"press {button}")
            self.pad_commands += 1
        before_frame = frame_of(self.client)
        before_guest, _ = guest_execution(self.client)
        before = self.player_view()
        mid_pad = self.verify_tap_landed()
        started = time.monotonic()
        while time.monotonic() - started < seconds:
            time.sleep(0.05)
            frame_of(self.client)
        after_guest, _ = guest_execution(self.client)
        after = self.player_view()
        for button in buttons:
            ask(self.client, f"release {button}")
            self.pad_commands += 1
        # The post-release sample is taken AFTER A SETTLE, not on the next round trip. The release
        # commands above are only ACCEPTED at the endpoint; the guest's own router has not run yet,
        # so a sample taken immediately still reads the held state and the report's "after the
        # release" would name a moment the guest has not reached. Measured 2026-09-28: the immediate
        # sample came back `held=0x2000`, identical to the held sample, which reads as "the release
        # did nothing" and is a property of WHEN the sample was taken rather than of the input path.
        # A few endpoint reads is a few presented frames of the guest actually running.
        for _ in range(4):
            frame_of(self.client)
        settled = self.verify_tap_landed()
        held = {
            "buttons": buttons,
            "seconds": round(time.monotonic() - started, 2),
            "presented_frames": frame_of(self.client) - before_frame,
            "player_before": before,
            "player_after": after,
            "pad_before": int.from_bytes(before_pad[0:2], "little") if len(before_pad) >= 2 else None,
            "pad_during": mid_pad,
            "pad_after": settled,
            "guest_before": before_guest.get("guest", {}),
            "guest_after": after_guest.get("guest", {}),
        }
        held["moved"] = (before.get("xy") != after.get("xy") or before.get("state") != after.get("state")
                         or before.get("anim") != after.get("anim"))
        self.hold_log.append(held)
        return held

    def player_view(self) -> dict:
        raw = read_bytes(self.client, prompts.PLAYER, prompts.PLAYER_PROBE_BYTES, tolerate_hole=True)
        if not raw:
            return {"read": False}

        def signed8(offset: int) -> int:
            return raw[offset] - 0x100 if raw[offset] >= 0x80 else raw[offset]

        return {
            "read": True,
            "active": raw[prompts.PLAYER_ACTIVE],
            "id": raw[prompts.PLAYER_ID],
            "character": raw[prompts.PLAYER_CHARACTER],
            "state": raw[prompts.PLAYER_STATE],
            "xy": (int.from_bytes(raw[prompts.PLAYER_X:prompts.PLAYER_X + 2], "little", signed=True),
                   int.from_bytes(raw[prompts.PLAYER_Y:prompts.PLAYER_Y + 2], "little", signed=True)),
            "anim": raw[prompts.PLAYER_ANIM],
            "hitpoints": signed8(prompts.PLAYER_HITPOINTS),
        }

    def try_capture(self, frame: int, screen) -> dict | None:
        """A capture, or None — and a dead product ends the run rather than raising out of a statement
        that only wanted a picture. Guarded for the same reason as the frame poll: the product is
        allowed to die, and every place it can be observed doing so has to be a place that records it."""
        try:
            shot = capture(self.client, SHOT_DIR / f"present_{frame:06d}.png")
        except (OSError, Refusal) as error:
            self.stopped = (f"the product stopped answering the endpoint during a capture "
                            f"({type(error).__name__}: {str(error).splitlines()[0][:140]})")
            self.stopped_at_frame = frame
            return None
        if shot:
            self.shots.append({"frame": frame, "screen": screen, **shot})
        return shot

    # ---- the route ------------------------------------------------------------------------------
    def run_route(self, budget_frames: int, budget_seconds: float, poll_seconds: float,
                  shot_every: int, tap_frames: int = 4) -> None:
        """Poll the census across the whole window, photograph it, and offer a pad edge only where the
        front end's own code reads one. The route has no fixed list of screens to walk: this title's
        post-movie state IS a state machine, and the route is "watch it and answer it when it asks"."""
        print(f"[live] route: watching the front end for up to {budget_frames} presented frames / "
              f"{budget_seconds:.0f}s, censusing every {poll_seconds:.2f}s, photographing every "
              f"{shot_every or 'no'} frame(s), tapping over {tap_frames} field(s) per edge")
        # What one read of the guest's own words costs, measured BEFORE any tap is offered, so the
        # report can say whether the read-back could have witnessed the edges it is about to watch.
        cost = self.measure_read_cost()
        if cost is None:
            print("[live]   read-back cost: NOT MEASURED (the endpoint did not answer the calibration "
                  "reads), so no negative from the read-back below carries weight")
        else:
            print(f"[live]   read-back cost: {cost:.1f} presented frame(s) per read, against a "
                  f"{tap_frames}-field tap — a read "
                  f"{'CAN' if cost <= tap_frames else 'CANNOT'} land inside the edge")
        started = time.monotonic()
        first = frame_of(self.client)
        last_shot_frame = -1
        last_tap_frame = -10_000
        settled_since = 0
        previous_key: tuple | None = None
        while True:
            # EVERY step of this loop is guarded, including the frame poll at the top. The first
            # version guarded only the census, and the product died during the poll between two
            # observations — so the guard that was supposed to make a crash a reported outcome missed
            # the one place the crash actually happened in.
            try:
                now = frame_of(self.client)
                spent = now - first
                if spent >= budget_frames or time.monotonic() - started > budget_seconds:
                    print(f"[live] window spent at presented frame {now} ({spent} frames of route, "
                          f"{self.observations} observations, {self.answers} menu answers)")
                    break
                # A census that could not be completed is a HOLE and the window goes on — but only a
                # TIMED-OUT read is a hole. An empty reply or a closed socket is the product being
                # GONE, and counting that as a hole would let a dead product run the whole window
                # reporting nothing but timeouts. So only the timeout is absorbed here and every other
                # refusal is re-raised to the guard below, which records how the run ended.
                try:
                    screen, frame_after, _ = self.census()
                except Refusal as error:
                    if "timed out" not in str(error):
                        raise
                    self.timeouts += 1
                    print(f"[live]   census hole: {str(error).splitlines()[0][:120]} "
                          f"({self.timeouts} so far)")
                    continue
                self.record(screen, frame_after)
                # EVERYTHING below this line is inside the same guard, deliberately. The guard used to
                # close right after the census, and the tap witness — which reads the guest's own words
                # back over the edge's whole span — sat outside it, so a product that died DURING a tap
                # (this title's measured 0x26010006 stage-load fault, presented field ~1300-3600
                # depending on the run) raised out of the route and the run reported NOTHING: no census,
                # no taps, no captures. Measured 2026-09-28. Same class as the census escape the tool
                # already fixed, one call site away from the fix.
                key = (screen.game_state, screen.sub_state, screen.machine_state, screen.handshake)
                if key != previous_key:
                    settled_since = 0
                    previous_key = key
                    if frame_after - last_shot_frame > 200:
                        shot = self.try_capture(frame_after, screen)
                        if shot:
                            last_shot_frame = frame_after
                else:
                    settled_since += 1
                self.check_legs(screen, frame_after)
                # A pad edge, but only where the front end's own code reads one and only once the
                # screen has been still for a poll. Both are census decisions; neither is a cadence.
                if (prompts.wants_start(screen) and settled_since >= 1
                        and frame_after - last_tap_frame >= 12):
                    self.tap("start", tap_frames, screen)
                    last_tap_frame = frame_after
                    settled_since = 0
                if shot_every and frame_after - last_shot_frame >= shot_every:
                    shot = self.try_capture(frame_after, screen)
                    if shot:
                        last_shot_frame = frame_after
                if self.stopped:
                    break
                time.sleep(poll_seconds)
            except (OSError, Refusal) as error:
                # The product is GONE. That is a RESULT, not a reason to abandon the run: the census,
                # the leg arrivals, the taps and the captures taken up to here are all still real, and
                # the report below prints them with their denominators. A driver that lets its subject's
                # death raise a traceback reports NOTHING, which is the one outcome that turns a
                # measured frontier back into an unmeasured question.
                self.stopped = (f"the product stopped answering the endpoint "
                                f"({type(error).__name__}: {str(error).splitlines()[0][:140]})")
                self.stopped_at_frame = self.frames[-1] if self.frames else None
                print(f"[live] {self.stopped} after presented frame {self.stopped_at_frame}. The "
                      f"census, the legs reached, the taps and the captures so far are still "
                      f"reported below.")
                break
        # A final photograph, so the last thing this run has is a picture of where it actually was.
        # Guarded like every other late query: if the product died, there is nothing left to photograph
        # and saying so is the honest outcome, where an unguarded call here would throw away the whole
        # report on the last statement of the run.
        try:
            final_frame = frame_of(self.client)
            shot = capture(self.client, SHOT_DIR / f"present_{final_frame:06d}.png")
        except (OSError, Refusal):
            print("[live] no final photograph: the product is no longer running, so there is no picture "
                  "left to take. Every capture above is one the product actually presented.")
            return
        if shot:
            self.shots.append({"frame": final_frame,
                               "screen": self.screens[-1] if self.screens else None, **shot})

    def check_legs(self, screen: prompts.Screen, frame: int) -> None:
        for leg in prompts.ROUTE:
            if leg.reached is None or leg.name in self.leg_frames:
                continue
            if leg.reached(screen):
                self.leg_frames[leg.name] = frame
                print(f"[live] leg reached: '{leg.name}' at presented frame {frame} after "
                      f"{self.observations} observation(s); {screen.describe()}")


def report(session: Session, client: LiveClient, log: Path) -> int:
    """Everything the run measured, with its denominators, and the refusals.

    The endpoint may already be gone by the time this runs — the product is allowed to die, and did.
    Every live query below is therefore wrapped, and a query that cannot be answered says NOT MEASURED
    and falls back to what the product logged while it was alive. It never prints a zero for a number it
    could not read."""
    census = prompts.census_tally(session.screens, session.frames)
    # The scene leg is judged on the guest's own submission, and the picture is reported BESIDE it. A
    # capture with many colours and few prims is the shape of a false positive, so it is named as one
    # rather than folded into the verdict.
    capture_prims = [entry["screen"].scene_prims if entry.get("screen") else -1
                     for entry in session.shots]
    colour_counts = [entry.get("colours") or 0 for entry in session.shots]
    scene_leg = prompts.leg3_from_captures(capture_prims)
    text = log.read_text(errors="replace") if log.is_file() else ""

    print()
    print("=== how this run ENDED ===")
    if session.stopped:
        print(f"[live]   {session.stopped}, at presented frame {session.stopped_at_frame}. Nothing "
              f"below is a measurement taken after that point.")
        for line in text.splitlines()[-6:]:
            print(f"[live]     the product's own last words: {line.strip()}")
    else:
        print("[live]   the window was spent normally and the product was still running at the end")

    def live(label: str, work, fallback: str = "NOT MEASURED — the product was no longer running"):
        try:
            return work()
        except (OSError, Refusal):
            print(f"[live]   {label}: {fallback}")
            return None
    print()
    print("=== route ===")
    for index, leg in enumerate(prompts.ROUTE, start=1):
        if leg.reached is None:
            verdict = ("REACHED, judged from the guest's own prim submissions (not from the picture)"
                       if scene_leg else
                       "NOT REACHED, judged from the guest's own prim submissions (not from the "
                       "picture)")
        elif leg.name in session.leg_frames:
            verdict = f"REACHED at presented frame {session.leg_frames[leg.name]}"
        else:
            verdict = "NOT REACHED"
        print(f"[live]   leg {index} of {len(prompts.ROUTE)} '{leg.name}': {verdict}")
        print(f"[live]     {leg.why}")
    print(f"[live]   {session.observations} census observation(s) over "
          f"{census['frames_covered']} presented frames (from {census['first_frame']} to "
          f"{census['last_frame']}), {session.answers} menu answer(s), {session.pad_commands} pad command(s), "
          f"{session.timeouts} timed-out census read(s) — a timed-out read is a HOLE in the census, not a zero")
    print(f"[live]   {session.shots and len(session.shots) or 0} capture(s)")

    print()
    print("=== guest state census (denominator: the observations above) ===")
    print(f"[live]   (game state, sub state) -> observations, presented frames held, handshake bytes seen, machine states seen")
    for key in sorted(census["game_states"]):
        entry = census["game_states"][key]
        print(f"[live]   {key[0]}/{key[1]}: {entry['observations']} observation(s), "
              f"presented frames {entry['first_frame']}..{entry['last_frame']} "
              f"({entry['frames_held']} inclusive), handshake {entry['handshakes']}, "
              f"machine states {entry['machine_states']}, at the measured park in "
              f"{entry['at_park']} of {entry['observations']}")
    print(f"[live]   XA/BGM machine-state word 0x{prompts.MACHINE_STATE:08X} distribution: "
          f"{dict(sorted(census['machine_states'].items()))}")
    print(f"[live]   music-active values seen: {sorted(census['musics'])}")
    print(f"[live]   handshake byte reached {prompts.FALSIFIER_HANDSHAKE} in "
          f"{sum(1 for s in session.screens if s.falsifier_closed)} of {len(session.screens)} observation(s)")
    print(f"[live]   game_info.unkD == 1 (the front end's own accept-input flag) in "
          f"{census['accept_input_ones']} of {len(session.screens)} observation(s)")
    # `misc_objects` is read ONCE, here, and reported as populated / records-read. Issue 0028 measured
    # 1 of 96 at the park; a stage frame must beat that, and the denominator is printed because 40 of
    # 96 records read would otherwise print a smaller number that reads as "fewer objects".
    misc = live("misc_objects", lambda: read_misc_objects(client),
                fallback="NOT MEASURED — the product was no longer running, so the park's own 1 of 96 "
                         "(docs/issues/0028) stands unchallenged")
    if misc is not None:
        populated, records_read = misc
        print(f"[live]   misc_objects 0x{prompts.MISC_OBJECTS:08X}: {populated} of {records_read} "
              f"record(s) read have a non-zero record id. The park's own measured value is 1 of 96 "
              f"(docs/issues/0028); issue 0028's reason it matters is that the park submits 2 prims per "
              f"frame and one of 96 object records.")
    for word in ("held", "previous", "pressed"):
        distribution = census["pad_words"][word]
        print(f"[live]   pad {word} word, value -> observations: "
              f"{ {f'0x{value:04X}': count for value, count in sorted(distribution.items())} }")
    print("[live]   ^ a word that never changes across the whole window means no edge was ever sampled "
          "by the guest; the tap list below is what was offered. The pressed word is the one the front "
          "end's own handlers test (the decomp's `controller_state`).")
    for line in session.tap_log:
        print(f"[live]   tap offered: {line}")
    # THE READ-BACK'S OWN RESOLUTION, before any verdict it could produce. Issue 0030 published
    # "the tap was NOT delivered into guest memory" from this surface, and that conclusion was not
    # available to it: a read costs more presented frames than a tap spans fields, so the read-back
    # reports the idle word for a delivered tap every time. The cost is therefore measured here and
    # the report says whether a read COULD have landed inside the edge, which is the question that
    # makes any negative from this surface meaningful.
    if session.read_cost_frames:
        per_read = session.read_cost_frames / max(session.read_cost_samples, 1)
        witnessed = per_read <= session.tap_fields
        print(f"[live]   READ-BACK RESOLUTION: {session.read_cost_samples} packet read(s) cost "
              f"{session.read_cost_frames} presented frame(s), i.e. {per_read:.1f} frame(s) per read. "
              f"This run's taps span {session.tap_fields} field(s) each, so a read-back COULD "
              f"{'land inside' if witnessed else 'NOT land inside'} the edge it is watching. The "
              f"read-back's negative is therefore "
              f"{'usable' if witnessed else 'NOT EVIDENCE of non-delivery'} — a surface that samples "
              f"coarser than the thing it samples cannot report its absence.")
    else:
        print("[live]   READ-BACK RESOLUTION: NOT MEASURED this run, so the read-back's negative below "
              "carries no weight either way.")
    if session.tap_unwitnessed:
        print(f"[live]   READ-BACK WITNESS: {session.tap_unwitnessed} of {session.answers} tap(s) showed no "
              f"change in the guest's own libpad packet word (active-low idle is 0x{IDLE_ACTIVE_LOW:04X}) "
              f"in any read-back sample. Read the READ-BACK RESOLUTION line above before drawing a "
              f"conclusion from this: this is what an undersampled edge looks like, and it is NOT by "
              f"itself a finding about the input path.")
    elif session.answers:
        print(f"[live]   READ-BACK WITNESS: all {session.answers} tap(s) were witnessed as a change in the "
              f"guest's own libpad packet word (active low) on at least one read-back sample.")
    if session.pad_words_seen:
        print(f"[live]   every distinct value the guest's pad words took while a tap was being witnessed:"
              f" { {k: sorted(v) for k, v in session.pad_words_seen.items()} }")
    # The per-field input-path observer. Reported WHETHER OR NOT it was enabled, because "no observer
    # lines" reads as "no finding" unless the report says the channel was off.
    rows, unusable = parse_input_path_log(log)
    if session.input_path_trace:
        _, skipped, refused = parse_input_path_counts(log)
        verdict_input = input_path_verdict(rows, session.pad_commands)
        print(f"[live]   INPUT PATH, per delivered field (channel {INPUT_PATH_CHANNEL} was ON): "
              f"{len(rows)} observer line(s) parsed ({len(rows) // 2} paired field(s)), "
              f"{skipped} line(s) skipped for not matching this tool's reader, {refused} line(s) "
              f"REFUSED because the record's own bytes and halfword disagree")
        if verdict_input["unpaired_lines"]:
            print(f"[live]     {verdict_input['unpaired_lines']} observer line(s) could NOT be paired into a "
                  f"field and are NOT counted as passing fields")
        if verdict_input["edge_fields"] == 0:
            print(f"[live]     NO EDGE FIELD was observed: the endpoint was asked for "
                  f"{verdict_input['endpoint_taps']} pad command(s) and the observer saw "
                  f"{verdict_input['edge_fields']} field(s) whose tap countdown was live. This run did not "
                  f"MEASURE the path — it asked no question of it.")
        else:
            print(f"[live]     {verdict_input['edge_fields']} of {len(rows) // 2} observed field(s) "
                  f"consumed a tap count; the gate was open on "
                  f"{verdict_input['gate_open_fields']} of them; "
                  f"{verdict_input['delivered_fields']} reached the guest's own packet word")
            if verdict_input["broken_at"] is None:
                print(f"[live]     STAGE VERDICT: every observed edge field carried the correct mask through "
                      f"all {len(FIELD_STAGES)} per-field stages "
                      f"({' -> '.join(FIELD_STAGES)}), so the LAST STAGE CORRECT is `guest` — the edge "
                      f"reached guest memory.")
            else:
                print(f"[live]     STAGE VERDICT: the first stage that disagreed is "
                      f"`{verdict_input['broken_at']}`, so the LAST STAGE CORRECT is "
                      f"`{verdict_input['last_correct_stage']}`.")
            for sample in verdict_input["sample"]:
                print(f"[live]       vbl={sample['vbl']} expected={sample['expected']} "
                      f"resolved={sample['resolved']} gate={sample['gate']} "
                      f"guest_packet_bytes={sample['guest_packet_bytes']} "
                      f"guest_packet={sample['guest_packet']} "
                      f"guest_held={sample['guest_held']} guest_pressed={sample['guest_pressed']}")
            print(f"[live]     THE GATE'S OWN INPUTS, read from the product, over the "
                  f"{verdict_input['edge_fields']} edge field(s): "
                  f"bios_pad_initialized={verdict_input['initialized']} "
                  f"bios_pad_irq_started={verdict_input['irq_started']} — and "
                  f"Hle::biosPadShouldService() reported {verdict_input['gate_open_fields']} of "
                  f"{verdict_input['edge_fields']} open. This is the framework's BIOS InitPAD "
                  f"lifecycle gate (pad_input.cpp's `if (!game->hle.biosPadShouldService()) return;`), "
                  f"and the words above decide whether it is the cause on THIS title.")
            print(f"[live]     THE GUEST'S OWN DECODED WORDS across those edge fields: "
                  f"held={['0x%04X' % v for v in verdict_input['guest_held_values']]} "
                  f"pressed={['0x%04X' % v for v in verdict_input['guest_pressed_values']]} — the "
                  f"packet word is ACTIVE LOW (idle 0xFFFF, a pressed bit CLEARED) and the guest's own "
                  f"router converts it into its pressed-bit convention, so a non-zero value here is the "
                  f"guest acknowledging the edge. The edge fields span the VBlank field counter "
                  f"{verdict_input['edge_field_span']}.")
    else:
        print(f"[live]   INPUT PATH, per delivered field: NOT MEASURED — the {INPUT_PATH_CHANNEL} channel "
              f"was off for this run, so the stages between the endpoint and the guest's packet buffer "
              f"were sampled 0 times. That is an absent measurement, not a pass and not a defect.")
    for held in session.hold_log:
        if held.get("skipped"):
            print(f"[live] held {held['buttons']}: SKIPPED — the product was gone before a held input "
                  f"could be delivered. That is a skip, not a zero, and it carries no input claim.")
            continue
        before, after = held["player_before"], held["player_after"]
        print(f"[live] held {held['buttons']} for {held['seconds']}s: {held['presented_frames']} "
              f"presented frames; player {before} -> {after} "
              f"({'MOVED' if held['moved'] else 'DID NOT MOVE'})")
        print(f"[live]   input in the guest's own memory, before the press {held['pad_before']}, "
              f"while held {held['pad_during']}, after the release {held['pad_after']}")
        print(f"[live]     `packet` is the ACTIVE-LOW button halfword the HOST wrote into the guest's "
              f"libpad buffer at 0x{prompts.PAD_BUFFER:08X}+2, so 0xFFFF is idle and a pressed Start "
              f"has bit 11 cleared; `packet_header` is that packet's status and pad-id bytes, which are "
              f"NOT input and are printed so nobody mistakes them for it again. held/previous/pressed "
              f"are the trio the GUEST's own router decodes from that packet. An unchanged packet means "
              f"the edge never arrived; a changed packet with an unchanged trio means it arrived and "
              f"the guest's router did not decode it; both with an unmoved player means the front end "
              f"read it and nothing acted on it.")
        if held["guest_before"] and held["guest_after"]:
            gained = (held["guest_after"].get("executed_instructions", 0)
                      - held["guest_before"].get("executed_instructions", 0))
            print(f"[live]   guest work during the window: {gained} instructions, "
                  f"{held['guest_after'].get('executed_blocks', 0) - held['guest_before'].get('executed_blocks', 0)}"
                  f" blocks, {held['guest_after'].get('cache_hits', 0) - held['guest_before'].get('cache_hits', 0)}"
                  f" cache hits — the guest kept executing while the picture was sampled")

    print()
    print("=== the post-movie falsifier (docs/issues/0029) ===")
    text = log.read_text(errors="replace") if log.is_file() else ""
    music_lines = [line.strip() for line in text.splitlines() if MUSIC_CD_CHANNEL in line]
    served = [line for line in music_lines if "CdSync 0x800E5D20 served" in line]
    verdict, explanation = prompts.falsifier_verdict(census, music_lines)
    print(f"[live]   the channel `{MUSIC_CD_CHANNEL}` was enabled for this whole run, and logged "
          f"{len(music_lines)} line(s) of which {len(served)} are a served CdSync edge. That count is "
          f"the denominator the falsifier needs: without it, 'the state word did not move' cannot be "
          f"told apart from 'the owner was never reached'.")
    for line in served[:4]:
        print(f"[live]     {line}")
    if len(served) > 4:
        print(f"[live]     ... and {len(served) - 4} more served edge(s) in {log}")
    print(f"[live]   VERDICT: {verdict}")
    print(f"[live]   {explanation}")
    print(f"[live]   The issue's own closing falsifier is a post-movie present containing scene. Whether "
          f"this run produced one is the capture table below, not this line.")

    print()
    print("=== screenshots ===")
    previous: dict | None = None
    for entry in session.shots:
        line = (f"[live]   present {entry['frame']}: {entry.get('width')}x{entry.get('height')} "
                f"{entry['bytes']}B, {entry.get('colours')} distinct colours, "
                f"non-black {entry.get('non_black')}/{entry.get('total')} "
                f"({100.0 * (entry.get('non_black_share') or 0):.2f}%)")
        if entry.get("error"):
            line += f" UNREADABLE: {entry['error']}"
        else:
            top = ", ".join(f"#{colour} {count}" for colour, count in entry.get("top", []))
            line += f", top: {top}"
        print(line)
        if entry.get("screen"):
            print(f"[live]     at that present: {entry['screen'].describe()}")
        difference = picture_diff(previous, entry) if previous else None
        if difference and difference.get("different") is not None:
            box = difference["box"]
            where = "nowhere (no pixel differs)" if box is None else f"bbox x={box[0]} y={box[1]} {box[2]}x{box[3]}"
            print(f"[live]     vs the previous capture: {difference['different']}/{difference['of']} "
                  f"pixels differ ({100.0 * difference['share']:.3f}%); {where}; mean |delta| "
                  f"{difference['mean']:.2f}/255")
        elif difference and difference.get("reason"):
            print(f"[live]     vs the previous capture: {difference['reason']} — NOT COMPARED")
        previous = entry
    for entry in session.shots:
        if "pixels" in entry:
            entry.pop("pixels", None)
    scene_captures = [entry for entry, prims in zip(session.shots, capture_prims)
                      if prims > prompts.PARK_PRIMS]
    print(f"[live]   per capture: DISTINCT COLOURS then GUEST-SUBMITTED PRIMS (the park's measured "
          f"values are {prompts.PARK_COLOURS} and {prompts.PARK_PRIMS}): "
          f"{list(zip(colour_counts, capture_prims))}")
    print(f"[live]   {len(scene_captures)} of {len(session.shots)} capture(s) were taken while the guest "
          f"had submitted MORE THAN {prompts.PARK_PRIMS} prims. Issue 0029's CLOSING falsifier is 'a "
          f"post-movie present contains scene', and the count that answers it is the prim count, because "
          f"'a scene' is a statement about what the guest drew.")
    for entry, colours, prims in zip(session.shots, colour_counts, capture_prims):
        if colours > prompts.PARK_COLOURS and prims <= prompts.PARK_PRIMS:
            print(f"[live]     MISMATCH at present {entry['frame']}: {colours} distinct colours but only "
                  f"{'an unread prim count' if prims < 0 else f'{prims} prim(s)'}. That picture is NOT "
                  f"a scene, and a colour-count test alone would have called it one. Uninitialised or "
                  f"half-written VRAM contains far more distinct colours than a rendered frame does.")
    if scene_captures:
        for entry in scene_captures:
            print(f"[live]     present {entry['frame']} is a scene capture: {entry.get('colours')} "
                  f"distinct colours and the guest's own display list follows")

    print()
    print("=== configuration, asked of the product over `cvars` ===")
    configuration = session.opening.get("configuration") or live(
        "cvars", lambda: effective_configuration(client))
    if configuration is None:
        configuration = {"knobs": {}, "layers": {}, "audit": "(not read: the product was gone)",
                         "unmatched": []}
        print("[live]   NO configuration was read: the endpoint was gone before this ran, and the "
              "product's own [cfg] boot line in the log is the only record — it is printed above")
    for line in text.splitlines():
        if line.strip().startswith("[cfg] active:") or line.strip().startswith("[cfg]   PSXPORT_"):
            print(f"[live]   {line.strip()}")
    for name in ("PSXPORT_SETTINGS", "PSXPORT_DEBUG_SERVER", "PSXPORT_X4_WIDESCREEN", "PSXPORT_NOAUDIO",
                 "PSXPORT_NOPACE", "PSXPORT_VK_HEADLESS", "PSXPORT_RENDER_PATH", "PSXPORT_WATCHDOG",
                 "PSXPORT_PRESENT_SINK", "PSXPORT_WAV", "PSXPORT_NATIVE_FRAMES", "PSXPORT_REPL"):
        if name in configuration["knobs"]:
            print(f"[live]   {name} = {configuration['knobs'][name]} [{configuration['layers'][name]}]")
    print(f"[live]   {configuration['audit']}")
    print("[live]   knobs this run SET that matched no declared CVar — they were read through the "
          "legacy path, which is why the audit calls them legacy, and the boot line calls them "
          "UNKNOWN:")
    for name in configuration["unmatched"]:
        print(f"[live]     {name}")
    wide_lines = [line.strip() for line in text.splitlines() if "[wide]" in line]
    for line in wide_lines:
        print(f"[live]   {line}")
    if wide_lines:
        print(f"[live]   the [wide] announcement prints on CHANGE only, so the LAST line is the steady "
              f"state: {wide_lines[-1]}")
    else:
        print("[live]   NO [wide] line in this run's log; the picture geometry is not readable from it")

    print()
    print("=== audio (the headless PSXPORT_WAV sink, never a device) ===")
    for name, value in wav_report(WAV).items():
        print(f"[live]   {name}: {value}")

    print()
    print("=== guest execution denominators (the framework's own counters) ===")
    # The latest per-poll sample, which is the closest reading to the end of the run a product that may
    # die at any moment can leave behind. `when` says WHICH sample this is, because counters read at the
    # end of a longer run must not be read as one set with the census above.
    counters = session.opening.get("guest")
    if counters is None:
        print("[live]   NOT MEASURED: the endpoint never answered a `guest` query in this run. The "
              "product's own log is the only record.")
        return 1
    counters, raw = counters
    sampled_frame = session.opening.get("frame", {}).get("frame")
    print(f"[live]   the latest sample, taken during the census poll at presented frame "
          f"{sampled_frame} of {session.frames[-1] if session.frames else '?'} — the run's LAST "
          f"successful reading of the counters, not a reading taken at the end")
    print(f"[live]   verbatim: {raw}")
    dynarec = counters["guest"]
    fallback = counters.get("fallback", {})
    print(f"[live]   dynarec: {dynarec.get('executed_blocks', 0)} executed blocks of "
          f"{dynarec.get('translated_blocks', 0)} translated, "
          f"{dynarec.get('executed_instructions', 0)} guest instructions in "
          f"{dynarec.get('calls', 0)} executor calls, {dynarec.get('host_dispatches', 0)} host "
          f"dispatches, cache {dynarec.get('cache_hits', 0)} hits / {dynarec.get('cache_misses', 0)} "
          f"misses, {dynarec.get('invalidations', 0)} invalidations, {dynarec.get('faults', 0)} faults")
    print(f"[live]   interpreter fallback: {fallback.get('calls', -1)} calls, "
          f"{fallback.get('instructions', -1)} instructions, {fallback.get('refused_calls', -1)} refused "
          f"(compilation_failed={fallback.get('compilation_failed', -1)} "
          f"self_modifying_code={fallback.get('self_modifying_code', -1)} "
          f"unsupported_block={fallback.get('unsupported_block', -1)} "
          f"load_delay_hazard={fallback.get('load_delay_hazard', -1)} "
          f"unsafe_instruction_fetch={fallback.get('unsafe_instruction_fetch', -1)})")
    counts = session.opening.get("frame") or {}
    if counts.get("frame") is None:
        print("[live]   presented frames: NOT MEASURED; the frame counter the census used is in the leg "
              "table above")
    else:
        print(f"[live]   presented frames at that sample: real={counts.get('frame')} "
              f"interp={counts.get('interp')} total={counts.get('total')} — this title declares no "
              f"temporal path, so a non-zero `interp` would be a finding in itself")

    failures = 0
    if dynarec.get("executed_blocks", 0) <= 0:
        print("[live]   REFUSED: the product presented frames but executed no guest blocks; a "
              "play-through with no dynarec execution is not gameplay evidence.")
        failures += 1
    if counts.get("interp") not in (0, None):
        print("[live]   REFUSED: the product emitted interpolated in-betweens, and Mega Man X4 declares "
              "no temporal path (RenderCapabilities::widescreenOnly). That is out of scope for this "
              "title and must not be counted as a cadence claim.")
        failures += 1
    if session.stopped:
        failures += 1
    for held in session.hold_log:
        if not held["moved"]:
            print(f"[live]   FINDING (not a pass): {held['buttons']} was held for {held['seconds']}s and "
                  f"the guest's player object did not move. Read it beside the census: if the player "
                  f"was never ACTIVE, no input could have moved it.")
    return failures


def kill(process: subprocess.Popen) -> int:
    """Kill by the PID this tool launched, never by name: another agent's product run must not die
    with this one."""
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=30)
    return process.returncode


def selftest() -> int:
    """The analysis half of this tool, on fixtures, driving NOTHING and launching no product.

    Three functions carry the run's conclusions, and each has a case that WOULD change its answer:
    the reply reader (a short read must raise, not pad with zeros), the picture differencer (identical
    frames must report zero differing pixels and no box, because a differencer that cannot say "nothing
    changed" cannot support "this changed"), and the WAV reader (a zero-peak file must say SILENCE,
    because this title's measured post-movie capture was movie XA rather than BGM and a non-silent
    number would be read as music).

    A run's conclusions rest on nothing else: the census, the route and the falsifier all live in
    `tools/title_prompts.py`, whose own selftest this file's --selftest does not duplicate."""
    import struct
    import tempfile
    from pathlib import Path

    failures = 0
    total = 0

    def check(name: str, got: object, want: object) -> None:
        nonlocal failures, total
        total += 1
        if got == want:
            print(f"  ok   {name}: {got!r}")
        else:
            failures += 1
            print(f"  FAIL {name}: got {got!r}, expected {want!r}")

    class FixtureClient:
        """A `dbgclient.LiveClient` that answers from a table, so the readers can be exercised without
        a product. It raises on any command the table does not hold, which is the same refusal the real
        endpoint's `? <cmd>` reply produces."""

        def __init__(self, table: dict[str, str]) -> None:
            self.table = table
            self.sent: list[str] = []

        def send(self, line: str) -> str:
            self.sent.append(line)
            if line in self.table:
                return self.table[line]
            if line.startswith(SERVER_TIMEOUT_PREFIX):
                return self.table[SERVER_TIMEOUT_PREFIX]
            return f"? {line}  (try 'help')\n"

    # --- read_bytes: the full answer, the short answer, and the unparsable one ---
    check("read_bytes decodes a full answer",
          read_bytes(FixtureClient({"r 80173C70 4": "80173C70: 01 02 03 04\n"}), 0x80173C70, 4),
          b"\x01\x02\x03\x04")
    total += 1
    try:
        read_bytes(FixtureClient({"r 80173C70 8": "80173C70: 01 02 03 04\n"}), 0x80173C70, 8)
    except Refusal as error:
        print(f"  ok   a SHORT byte read is refused, not padded: {error}")
    else:
        failures += 1
        print("  FAIL a short read was padded, so the absent tail reads as zero")
    total += 1
    try:
        read_bytes(FixtureClient({"r 80173C70 2": "80173C70: ZZ YY\n"}), 0x80173C70, 2)
    except Refusal as error:
        print(f"  ok   an unparsable read is refused: {error}")
    else:
        failures += 1
        print("  FAIL an unparsable read decoded anyway")
    # The address prefix is a hex address, so a parser that split on the FIRST colon would be reading
    # the reply's own label as data.
    check("read_bytes does not read the address prefix as data",
          read_bytes(FixtureClient({"r 80173C70 1": "80173C70: AB\n"}), 0x80173C70, 1), b"\xab")

    # --- picture_diff: the discriminator, on synthetic pixel buffers ---
    def frame(width: int, height: int, pixels: bytes) -> dict:
        return {"path": Path("fixture.ppm"), "width": width, "height": height, "pixels": pixels,
                "total": width * height, "error": None}

    flat = bytes(bytearray([10, 20, 30]) * 32)
    same = picture_diff(frame(8, 4, flat), frame(8, 4, flat))
    check("identical frames -> 0 differing", same["different"], 0)
    check("identical frames -> no box", same["box"], None)
    check("identical frames -> mean 0", same["mean"], 0.0)

    moved = bytearray(flat)
    for y in (2, 3):
        for x in (2, 3, 4):
            base = (y * 8 + x) * 3
            moved[base] = min(255, moved[base] + 5)
    band = picture_diff(frame(8, 4, flat), frame(8, 4, bytes(moved)))
    check("known band -> 6 differing pixels", band["different"], 6)
    check("known band -> box names where it moved", band["box"], (2, 2, 3, 2))
    check("known band -> mean channel delta 5/3", round(band["mean"], 4), round(5 / 3, 4))

    one = bytearray(flat)
    one[0] = 1  # a single-LSB change must be reported, not rounded away
    check("1-LSB change is not rounded away", picture_diff(frame(8, 4, flat),
                                                            frame(8, 4, bytes(one)))["different"], 1)

    mismatched = picture_diff(frame(8, 4, flat), frame(4, 4, bytes(48)))
    check("mismatched sizes are NOT COMPARED", mismatched["different"], None)
    check("mismatched sizes say why", mismatched["reason"], "captures are different sizes")

    # --- guest_execution: the two lines must not merge ---
    merged = ("guest: calls=7 translated_blocks=7 executed_blocks=7 executed_instructions=999\n"
              "fallback: calls=0 instructions=0 refused_calls=0 compilation_failed=0\n")
    counters, raw = guest_execution(FixtureClient({"guest": merged}))
    check("guest counters keep the two lines apart",
          (counters["guest"]["executed_instructions"], counters["fallback"]["instructions"]), (999, 0))
    check("the verbatim reply is returned so a parsed number can be checked", raw.startswith("guest:"), True)
    total += 1
    try:
        guest_execution(FixtureClient({"guest": "no counters here\n"}))
    except Refusal as error:
        print(f"  ok   a `guest` reply with no counters is refused: {error}")
    else:
        failures += 1
        print("  FAIL a counterless `guest` reply was read as all-zero")

    # --- ask(): the three replies that are not answers ---
    total += 1
    try:
        ask(FixtureClient({}), "guest")
    except Refusal as error:
        print(f"  ok   an unimplemented command is refused as a stale build: {str(error)[:96]}...")
    else:
        failures += 1
        print("  FAIL an unimplemented command was answered")
    # The timeout notice is what the SERVER sends back for a line it could not service, so the fixture
    # answers that line with the notice. Two attempts, no answer: the retries are attempts, not reads.
    timing_out = FixtureClient({"frame": f"{SERVER_TIMEOUT_PREFIX} no frame in 4s)\n"})
    total += 1
    try:
        ask(timing_out, "frame", retries=2)
    except Refusal as error:
        print(f"  ok   a persistent endpoint timeout is refused: {str(error)[:96]}...")
    else:
        failures += 1
        print("  FAIL a persistent timeout was read as an answer")
    check("a retried timeout counts as an attempt, not an answer", len(timing_out.sent), 2)
    # ... and a timeout that CLEARS is an answer, not a hole: the endpoint recovers and the caller is
    # not left believing the product died.
    recovering = FixtureClient({"frame": f"{SERVER_TIMEOUT_PREFIX} no frame in 4s)\n"})
    recovering.table["frame"] = "frame=42 interp=0 total=42 paused=0 disp=(0,0)\n"
    check("a timeout that clears is retried into an answer", frame_of(recovering), 42)

    # --- wav_report: silence must say SILENCE ---
    # Built chunk by chunk, because a hand-typed RIFF header that is one field short still parses as a
    # plausible WAV with plausible numbers — which is the failure this reader has to survive.
    with tempfile.TemporaryDirectory(dir=str(REPO / "scratch")) as scratch:
        def wav_bytes(pcm: bytes) -> bytes:
            fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
            return (b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(pcm)) + b"WAVE"
                    + b"fmt " + struct.pack("<I", len(fmt)) + fmt
                    + b"data" + struct.pack("<I", len(pcm)) + pcm)

        silent_pcm = bytes(200)  # 100 stereo frames, every sample zero
        wav = Path(scratch) / "silent.wav"
        wav.write_bytes(wav_bytes(silent_pcm))
        silence = wav_report(wav)
        check("a zero-peak WAV is reported as SILENT", "SILENT" in silence["verdict"], True)
        check("a zero-peak WAV reports its own seconds", round(silence["seconds"], 6),
              round(200 / 88200, 6))
        check("a zero-peak WAV reports a peak of exactly zero", silence["peak"], 0)
        loud = Path(scratch) / "loud.wav"
        loud.write_bytes(wav_bytes(struct.pack("<hh", 30000, -30000) + bytes(196)))
        check("a non-silent WAV reports its peak", wav_report(loud)["peak"], 30000)
        check("a non-silent WAV does not say SILENCE", "SILENT" in wav_report(loud)["verdict"], False)
        missing = wav_report(Path(scratch) / "absent.wav")
        check("an absent WAV says absent, not zero", missing["present"], False)
        empty = Path(scratch) / "empty.wav"
        empty.write_bytes(b"")
        check("an empty WAV is reported as too short, not as silence", "too short" in
              wav_report(empty)["verdict"], True)
        not_a_wav = Path(scratch) / "other.wav"
        not_a_wav.write_bytes(b"ID3" + bytes(60))
        check("a file that is not RIFF/WAVE says so", "not a RIFF/WAVE file" in
              wav_report(not_a_wav)["verdict"], True)

    # --- a DYING product must still produce a report, not a traceback --------------------------
    # This case exists because the first version of this tool raised ConnectionResetError straight out
    # of the route loop and lost every number it had already taken. A driver whose subject dies and
    # which then reports nothing has turned a measured frontier back into an unmeasured question, so
    # the death is an OUTCOME the run records, and this asserts it.
    class DyingClient:
        """Answers a whole census and then refuses, the way a crashed product's socket does."""

        def __init__(self, polls: int) -> None:
            self.polls = polls
            self.asked = 0

        def send(self, line: str) -> str:
            self.asked += 1
            if self.asked > self.polls * (2 + len(POLL_READS) + 2):
                raise ConnectionResetError(104, "Connection reset by peer")
            if line.startswith("frame"):
                return "frame=1000 interp=0 total=1000 paused=0 disp=(0,0)\n"
            if line == "scene":
                # The park's own classified display list, so the fixture's census decodes the
                # measured 2 prims rather than an absent one.
                return ("[scene] f7 OT@0x80000000 — classified display list:\n"
                        "[scene] f7 totals: poly=1 rect=0 line=0 fill=0 vramcopy=0 upload=0 env=1\n")
            if line == "guest":
                return ("guest: calls=1 translated_blocks=1 executed_blocks=1 "
                        "executed_instructions=1 host_dispatches=0 cache_hits=1 cache_misses=1 "
                        "invalidations=0 faults=0\n"
                        "fallback: calls=0 instructions=0 refused_calls=0 compilation_failed=0\n")
            if line == "cvars":
                return "env audit: 0 PSXPORT_* set -> 0 declared, 0 legacy, 0 UNKNOWN\n"
            if line.startswith("shot "):
                return "shot -> (refused in this fixture)\n"
            # The pad drive commands. A fixture that cannot answer them is not a fixture of a route
            # that taps and a window that holds — it is a fixture of the census, and it fails with an
            # IndexError from the byte-read fallback below the moment the route offers an edge.
            if line.split()[0] in ("press", "release", "tap", "hold"):
                return f"{line}\n"
            count = int(line.split()[2])
            payload = " ".join("00" for _ in range(count))
            return f"{line.split()[1]}: {payload}\n"

        def close(self) -> None:
            pass

    class TapKillerClient(DyingClient):
        """A front end that reads Start (unkD == 1) and a socket that dies DURING a tap's read-back.

        This is the case the route's guard missed, and it is not hypothetical: the tap witness reads
        the guest's own words back once per round trip for the whole edge, so it is the longest single
        stretch of endpoint traffic in the route, and this title's measured 0x26010006 stage-load fault
        lands at presented field ~1300-3600 — right where the first tap happens. The guard closed after
        the census, so the exception escaped `run_route` and the run printed no report at all."""
        def __init__(self) -> None:
            super().__init__(polls=10**9)
            self.taps = 0
            self.dead = False

        def send(self, line: str) -> str:
            if self.dead:
                raise ConnectionResetError(104, "Connection reset by peer")
            if line.startswith("tap "):
                self.taps += 1
                if self.taps == 1:
                    # The tap is accepted; the read-back that should witness it finds a dead socket.
                    self.dead = True
                    return f"tap {line.split()[1]} {line.split()[2]}\n"
            if line.startswith("r ") and line.split()[1].upper() == f"{prompts.GAME_INFO:08X}":
                # unkD is at game_info + 0x0D, and the only front-end state whose own code reads Start
                # is unkD == 1. Without this the fixture would offer no tap and the case would pass
                # without ever reaching the call site it exists to cover.
                raw = bytearray(int("00", 16) for _ in range(int(line.split()[2])))
                raw[0x0D] = 1  # accept_input is game_info + 0x0D, and 1 is the state that reads Start
                return f"{line.split()[1]}: " + " ".join(f"{b:02x}" for b in raw) + "\n"
            return super().send(line)

    tap_killer = TapKillerClient()
    tap_session = Session(tap_killer)
    raised_out: BaseException | None = None
    try:
        tap_session.run_route(budget_frames=100000, budget_seconds=30.0, poll_seconds=0.0,
                              shot_every=0, tap_frames=4)
    except BaseException as error:  # noqa: BLE001 - the point of the case is that this must not happen
        raised_out = error
    check("a product that dies DURING a tap witness does NOT raise out of the route",
          raised_out, None)
    check("... it is RECORDED as how the run ended instead", tap_session.stopped is not None, True)
    check("... and the census it had already taken survives", len(tap_session.screens) >= 1, True)
    check("... and the tap is counted as offered", tap_killer.taps, 1)

    class HoldKillerClient(DyingClient):
        """Answers until the hold window's first `frame` poll, then dies.

        The hold window is one `frame` poll every 50 ms for the whole hold, and this title's measured
        0x26010006 stage-load fault lands at presented field ~1200-2800 — exactly where a hold that
        follows a long route happens. The window used to let that raise out of `main` and the run
        printed no report at all."""
        def __init__(self) -> None:
            super().__init__(polls=10**9)
            self.pressing = False
            self.dead = False

        def send(self, line: str) -> str:
            if line.startswith("press ") or line.startswith("release "):
                self.pressing = True
            if self.pressing and self.dead:
                raise ConnectionResetError(104, "Connection reset by peer")
            if self.pressing and line.startswith("frame"):
                self.dead = True
            return super().send(line)

    hold_killer = HoldKillerClient()
    hold_session = Session(hold_killer)
    hold_raised: BaseException | None = None
    try:
        hold_session.hold_window(["right"], 0.2)
    except BaseException as error:  # noqa: BLE001 - the point of the case is that this must not happen
        hold_raised = error
    check("a product that dies DURING a hold window does NOT raise out of it", hold_raised, None)
    check("... and the hold is RECORDED as a SKIP, not as a zero",
          hold_session.hold_log[0].get("skipped"), True)
    check("... and a skipped hold claims nothing about movement",
          hold_session.hold_log[0]["moved"], False)

    dying = DyingClient(polls=3)
    session = Session(dying)
    session.run_route(budget_frames=100000, budget_seconds=30.0, poll_seconds=0.0, shot_every=0)
    check("a product that dies is RECORDED as how the run ended", session.stopped is not None, True)
    check("... and the run kept the census it had already taken", len(session.screens) >= 1, True)
    check("... with a denominator, not a bare list", session.observations, len(session.screens))
    check("... and names the frame it died at", isinstance(session.stopped_at_frame, int), True)
    check("... and a dead product is not reported as an all-zero run", session.observations > 0, True)
    check("the hold window is skipped, not attempted, once the product is gone", session.alive(), False)
    # --- the scene leg: the prim count decides it, and the colour count is reported beside it ----
    # THE CASE THAT MATTERS: a picture with thousands of distinct colours and the guest's own 2 prims
    # is NOT a scene. The 2026-09-27 run produced exactly that — 14,276 colours at 98.51% non-black,
    # uninitialised VRAM, captured one instruction after the guest segfaulted — and a colour-count test
    # called it a scene. Both answers are asserted here so the test that decided it cannot be quietly
    # changed back.
    quiet = "[scene] f9 totals: poly=1 rect=0 line=0 fill=0 vramcopy=0 upload=0 env=1"
    check("the park's classified display list really is the measured 2 prims",
          scene_prims(quiet)[0], prompts.PARK_PRIMS)
    busy = "[scene] f9 totals: poly=1840 rect=96 line=0 fill=12 vramcopy=3 upload=0 env=1"
    check("a frame with real geometry is counted", scene_prims(busy)[0], 1840 + 96 + 12 + 3 + 1)
    check("a totals line that is absent is -1, not zero", scene_prims("[scene] f9 nothing here")[0], -1)
    check("a frame with the park's 2 prims is NOT a scene, whatever its colour count",
          prompts.leg3_from_captures([prompts.PARK_PRIMS]), False)
    check("a frame with real geometry DOES reach the scene leg",
          prompts.leg3_from_captures([prompts.PARK_PRIMS, 1952]), True)
    check("an unread prim count does not reach the scene leg",
          prompts.leg3_from_captures([-1, -1]), False)
    check("no captures at all does not reach the scene leg", prompts.leg3_from_captures([]), False)

    # --- the picture census: the park's own number is still reported, and is NOT the test ----------
    # The colour count stays in the report because it is a real property of every capture, and the
    # park's measured value is still worth asserting. What it is NOT is the scene discriminator, and
    # the assertion below is that it would pass on a frame that is not a scene — which is exactly why
    # the leg moved to the prim count.
    park_pixels = bytes(bytearray([8, 8, 16] + [0, 0, 0]) * 32)
    colours = {park_pixels[index:index + 3].hex() for index in range(0, len(park_pixels), 3)}
    check("the park's own picture really is the measured 2 colours", len(colours), prompts.PARK_COLOURS)
    check("so a colour count DOES separate the park from uninitialised VRAM — which is why it is "
          "not allowed to be the scene test", len(colours) > prompts.PARK_COLOURS, False)
    check("the two scene thresholds are the park's two MEASURED values, not magic constants",
          (prompts.PARK_COLOURS, prompts.PARK_PRIMS), (2, 2))

    # --- the per-field input-path observer: BOTH ANSWERS, and the format guard ------------------------
    # A stage verdict that has only ever printed "the edge did not arrive" is a tool that cannot
    # support the opposite claim, and the whole point of measuring the stages is to be able to say the
    # edge landed. So the fixture below is built to make it say BOTH, from the same reader, by moving
    # ONE value: the resolved mask and the guest packet. Everything else is held identical, so a change
    # in the verdict is attributable to that value and not to the reader.
    # The fixture is pinned to the SHIPPING spelling of every field, measured from a real
    # 2026-09-27 run's log rather than from what a formatter "should" print: `repl(on=...)` is an
    # `int` member and prints `1`, while the three `gate(...)` fields are `bool` members and print
    # `true`. A fixture that spelled both the same way passed against a parser that only accepted
    # one of them, which is how the first live reading of this observer reported "broken at repl"
    # for a product that had written the tap into guest memory. Both spellings are exercised below.
    def observer_line(phase: str, *, tap: int = 0xF7FF, tap_n: int = 0, buttons: int = 0xFFFF,
                      on: bool = True, gate: bool = True, slot0_buttons: int | None = None,
                      init: bool = True, irq: bool = True, bool_spelling: str = "true",
                      vbl: int = 100) -> str:
        written = tap if slot0_buttons is None else slot0_buttons
        # Pad::fillBuffer's own layout, reproduced here only as FIXTURE data: byte 0 status, byte 1
        # pad id, bytes 2..3 the ACTIVE LOW mask. Packed little-endian into one word that puts the
        # button halfword in the HIGH half and the status/id pair in the low half — which is exactly
        # what a real run recorded (0xFFF74100 for a 0xFFF7 button mask). The record carries the
        # packed word AND the halfword read back out of it, and the reader cross-checks the two — see
        # the refusal case below, which is the byte-order mistake the frontier probe shipped in both
        # directions.
        slot0 = ((written & 0xFFFF) << 16) | 0x0041
        flag = ((lambda value: "true" if value else "false") if bool_spelling == "true"
                else (lambda value: "1" if value else "0"))
        return (f"[{INPUT_PATH_CHANNEL}] {phase}: vbl={vbl} repl(on={flag(on)} tap=0x{tap:04X} "
                f"tap_n={tap_n} hold=0xFFFF) resolved(buttons=0x{buttons:04X}) "
                f"gate(initialized={flag(init)} irq_started={flag(irq)} "
                f"shouldService={flag(gate)}) "
                f"guest(slot0_bytes=0x{slot0:08X} slot0_buttons=0x{written:04X} "
                f"slot1_bytes=0x00FFFFFF slot1_buttons=0x0000 held=0x0000 pressed=0x0000)")

    # A record whose packed bytes and reported halfword DISAGREE is a line this reader refuses, and
    # the refusal must be counted. This is the exact shape of the mistake the first live reading made:
    # slice the packed word's low half and a delivered 0xFFF7 button halfword reads as the 0x4100
    # status/id header. Resolving such a line in favour of either field is a guess, so neither is used.
    selfrefuse = Path("scratch") / "live_probe"
    selfrefuse.mkdir(parents=True, exist_ok=True)
    inconsistent = selfrefuse / "inconsistent.log"
    inconsistent.write_text(
        observer_line("pre-service", tap_n=4).replace("slot0_buttons=0xF7FF", "slot0_buttons=0x4100")
        + "\n"
        + observer_line("post-service", tap_n=3, buttons=0xF7FF, slot0_buttons=0xF7FF,
                        vbl=101) + "\n")
    inconsistent_rows, inconsistent_skipped, inconsistent_refused = parse_input_path_counts(inconsistent)
    check("a line whose bytes and halfword disagree is REFUSED, not interpreted",
          inconsistent_refused, 1)
    check("... and it is not counted as a parsed line", len(inconsistent_rows), 1)
    check("... and the refused pre-service line is a HOLE, not a passing field",
          input_path_verdict(inconsistent_rows, 1)["unpaired_lines"], 1)
    check("... and the refused line is not read as an edge field",
          input_path_verdict(inconsistent_rows, 1)["edge_fields"], 0)

    # The reader must accept the real shipping spelling — an `int` member as 1/0 and a `bool` member
    # as true/false in the SAME line. This is the case that would have caught the wrong verdict.
    spellings = Path("scratch") / "live_probe"
    spellings.mkdir(parents=True, exist_ok=True)
    mixed = spellings / "spelling.log"
    mixed.write_text("\n".join([
        observer_line("pre-service", tap_n=4, bool_spelling="int"),
        observer_line("post-service", tap_n=3, buttons=0xF7FF, slot0_buttons=0xF7FF,
                      bool_spelling="int"),
    ]) + "\n")
    mixed_rows, _ = parse_input_path_log(mixed)
    mixed_verdict = input_path_verdict(mixed_rows, 1)
    check("a real line mixes an int member (1) and bool members (true) and the reader takes both",
          (mixed_rows[0]["on"], mixed_rows[0]["gate"]), (True, True))
    check("... and such a line is NOT reported as broken at `repl`",
          mixed_verdict["broken_at"], None)
    check("... and reaches the guest packet", mixed_verdict["delivered_fields"], 1)

    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        # DELIVERED: the tap mask is resolved into `buttons` AND the guest's packet carries it.
        good = Path(directory) / "delivered.log"
        good.write_text("\n".join([
            observer_line("pre-service", tap_n=4),
            observer_line("post-service", tap_n=3, buttons=0xF7FF, slot0_buttons=0xF7FF),
            observer_line("pre-service", tap_n=3),
            observer_line("post-service", tap_n=2, buttons=0xF7FF, slot0_buttons=0xF7FF),
        ]) + "\n")
        rows, skipped = parse_input_path_log(good)
        verdict = input_path_verdict(rows, 1)
        check("the reader parses every observer line it was given", len(rows), 4)
        check("a well-formed log skips nothing", skipped, 0)
        check("a delivered edge is counted at every field", verdict["edge_fields"], 2)
        check("a delivered edge has NO stage that disagrees", verdict["broken_at"], None)
        check("... so there is no stage short of the guest's own memory",
              verdict["last_correct_stage"], None)
        check("... and both fields reached the guest packet", verdict["delivered_fields"], 2)

        # THE OPPOSITE ANSWER, from the same reader: the mask resolves but the gate is closed, so the
        # framework never writes the packet. This is the shape issue 0030's symptom has, and a reader
        # that could not produce it could not have found the cause.
        gated = Path(directory) / "gated.log"
        gated.write_text("\n".join([
            observer_line("pre-service", tap_n=4),
            observer_line("post-service", tap_n=3, buttons=0xF7FF, gate=False, slot0_buttons=0xFFFF),
        ]) + "\n")
        gated_verdict = input_path_verdict(parse_input_path_log(gated)[0], 1)
        check("a closed gate is named as the first stage that disagreed",
              gated_verdict["broken_at"], "gate")
        check("... so the last stage correct is `resolved`",
              gated_verdict["last_correct_stage"], "resolved")
        check("... and no field reached the guest packet", gated_verdict["delivered_fields"], 0)

        # The one that decides between them: the gate open but the packet still idle. That isolates
        # the write itself from the gate, which is the distinction the two cases above do not make.
        wrote = Path(directory) / "notwrote.log"
        wrote.write_text("\n".join([
            observer_line("pre-service", tap_n=4),
            observer_line("post-service", tap_n=3, buttons=0xF7FF, gate=True, slot0_buttons=0xFFFF),
        ]) + "\n")
        wrote_verdict = input_path_verdict(parse_input_path_log(wrote)[0], 1)
        check("an open gate that still does not write names `guest`",
              wrote_verdict["broken_at"], "guest")
        check("... so the last stage correct is `gate`", wrote_verdict["last_correct_stage"], "gate")

        # A mask that never resolves: the break is between the REPL mask and Pad::buttons.
        unresolved = Path(directory) / "unresolved.log"
        unresolved.write_text("\n".join([
            observer_line("pre-service", tap_n=4),
            observer_line("post-service", tap_n=3, buttons=0xFFFF, slot0_buttons=0xFFFF),
        ]) + "\n")
        unresolved_verdict = input_path_verdict(parse_input_path_log(unresolved)[0], 1)
        check("a mask that never resolves names `resolved`", unresolved_verdict["broken_at"], "resolved")
        check("... so the last stage correct is `repl`",
              unresolved_verdict["last_correct_stage"], "repl")

        # NO EDGE AT ALL is not a pass. A run that asked no question of the path must say so, and this
        # is the case that keeps "0 of 0" from reading as "the path is fine".
        idle = Path(directory) / "idle.log"
        idle.write_text("\n".join([
            observer_line("pre-service"),
            observer_line("post-service"),
        ]) + "\n")
        idle_verdict = input_path_verdict(parse_input_path_log(idle)[0], 0)
        check("a run that offered no edge counts no edge field", idle_verdict["edge_fields"], 0)
        check("... and therefore has no broken stage to name", idle_verdict["broken_at"], None)

        # A LOG FORMAT CHANGE must be counted, not silently dropped: an unreadable observer line and a
        # silent observer are the same shape otherwise, and that is the confusion the parse counts
        # exist to remove.
        drifted = Path(directory) / "drifted.log"
        drifted.write_text("\n".join([
            observer_line("pre-service", tap_n=4),
            f"[{INPUT_PATH_CHANNEL}] post-service: repl(on=true tap=0xF7FF) resolved(buttons=0xF7FF)"
            "  <-- the body changed, the channel did not",
        ]) + "\n")
        drifted_rows, drifted_skipped = parse_input_path_log(drifted)
        check("a line this reader cannot parse IS COUNTED", drifted_skipped, 1)
        check("... and is not counted as a parsed field", len(drifted_rows), 1)
        check("... and a log with NO channel in it yields nothing rather than everything",
              parse_input_path_log(Path(directory) / "absent.log")[0], [])
        # The framework's own config echo NAMES the channel without being a record of it. Selecting
        # by substring counted two such lines as unparsable observer records and put a phantom
        # "2 line(s) skipped" into a report about the input path; the selector is the log's channel
        # TAG, and this pins that.
        echo = Path(directory) / "echo.log"
        echo.write_text(
            "[2026-09-27T21:59:10.704Z] [cfg] active: PSXPORT_DEBUG=x4-music-cd,x4-input-path ...\n"
            "[2026-09-27T21:59:10.704Z] [cfg]   PSXPORT_DEBUG = x4-music-cd,x4-input-path [env]\n"
            + observer_line("pre-service", tap_n=4) + "\n"
            + observer_line("post-service", tap_n=3, buttons=0xF7FF, slot0_buttons=0xF7FF) + "\n")
        echo_rows, echo_skipped, echo_refused = parse_input_path_counts(echo)
        check("a config echo that NAMES the channel is not an observer record",
              (len(echo_rows), echo_skipped, echo_refused), (2, 0, 0))

        # An unpaired half-line is a hole, not a passing field.
        half = Path(directory) / "half.log"
        half.write_text(observer_line("pre-service", tap_n=4) + "\n")
        half_verdict = input_path_verdict(parse_input_path_log(half)[0], 1)
        check("an unpaired pre-service line is a hole", half_verdict["unpaired_lines"], 1)
        check("... and is NOT counted as an edge field", half_verdict["edge_fields"], 0)

    if failures:
        print(f"  selftest: {failures} of {total} case(s) FAILED")
        return 1
    print(f"  selftest: {total - failures}/{total} cases behaved as required.")
    print("  The load-bearing pairs are: a short read RAISING (so an absent tail is never read as zero),")
    print("  two identical frames reporting zero differing pixels AND a box-less result (so 'this")
    print("  capture changed' is a claim the differencer can also refuse), and a zero-peak WAV saying")
    print("  SILENCE (so this title's measured movie-XA capture is never read as music).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=5974, help="live endpoint port (default 5974)")
    parser.add_argument("--executable", type=Path, default=EXECUTABLE)
    parser.add_argument("--budget-frames", type=int, default=60000,
                        help="presented frames the whole window may spend (default 60000). Measured on "
                             "this tree, 15,000 presented fields take about 38s unpaced, so this is "
                             "roughly 150s — chosen because the post-movie boundary has been MEASURED at "
                             "field 974 in one run and 13,153 in another, and a budget that stopped "
                             "short of the later one would report 'the movie never finished' about a "
                             "run that had simply not waited long enough")
    parser.add_argument("--budget-seconds", type=float, default=900.0)
    parser.add_argument("--poll-seconds", type=float, default=0.30,
                        help="wall clock between census polls; each poll is at least "
                             f"{2 + len(POLL_READS)} presented frames wide")
    parser.add_argument("--shot-every", type=int, default=4000,
                        help="photograph every N presented frames (0 disables the periodic capture)")
    parser.add_argument("--hold", nargs="*", default=["right"], metavar="BUTTON",
                        help="buttons to hold after the window (default: right); pass none to skip")
    parser.add_argument("--seconds", type=float, default=6.0, help="how long to hold them")
    parser.add_argument("--narrow", action="store_true",
                        help="run the 4:3 leg (PSXPORT_X4_WIDESCREEN=0, 960x720 sink) instead of the "
                             "shipping 16:9 leg")
    parser.add_argument("--tap-frames", type=int, default=4,
                        help="how many presented fields each offered tap spans (default 4). A tap is an "
                             "edge, so it must span more than one field to be an edge at all; the report "
                             "prints this against what one endpoint read costs in presented frames, "
                             "because a read that costs more frames than the tap spans fields CANNOT "
                             "witness the tap and its negative is not evidence of non-delivery")
    parser.add_argument("--connect-timeout", type=float, default=180.0)
    parser.add_argument("--input-path-trace", action="store_true",
                        help="enable the title's per-field input-path observer channel, so the stages "
                             "between the endpoint and the guest's own libpad packet buffer are sampled "
                             "once per DELIVERED FIELD instead of once per poll. Costs O(fields) log "
                             "lines, so it is off by default; a report that says the channel was off is "
                             "reporting that the path was NOT MEASURED, never that it worked or did not")
    parser.add_argument("--selftest", action="store_true",
                        help="exercise the readers on fixtures; launches no product and drives nothing")
    arguments = parser.parse_args()

    if arguments.selftest:
        return selftest()

    matched, scanned, disagreements = prompts.verify_address_owners(REPO)
    print(f"[live] guest-address owners: {matched} of {scanned} declaration(s) still agree")
    for line in disagreements:
        print(f"[live]   {line}")
    if disagreements:
        raise Refusal("REFUSED: a guest address this tool reads is no longer declared by the source "
                      "that owns it, or at a different value. Read the disagreement above and the "
                      "cited file before trusting any number below.")

    others = running_instances()
    if others:
        raise Refusal("REFUSED: refusing to start a second product instance; already running:\n  "
                      + "\n  ".join(others))
    resolved = EXECUTABLE.parent.parent / "psxport_resolved.txt"
    if resolved.is_file():
        fields = dict(line.split("=", 1) for line in resolved.read_text(errors="replace").splitlines()
                      if "=" in line)
        print(f"[live] product: {EXECUTABLE.relative_to(REPO)}  framework {fields.get('commit', '?')[:12]}"
              f" ({fields.get('dir', '?')})")
    print(f"[live] boot image: {IMAGE.relative_to(REPO)}  settings: {SETTINGS.relative_to(REPO)}")
    print(f"[live] log: {LOG.relative_to(REPO)}  audio sink: {WAV.relative_to(REPO)}  "
          f"screenshots: {SHOT_DIR.relative_to(REPO)}")

    wide = "0" if arguments.narrow else "1"
    sink = "960x720" if arguments.narrow else "1284x720"
    process = launch(arguments.port, sink, wide, LOG, WAV,
                     input_path_trace=arguments.input_path_trace)
    client: LiveClient | None = None
    try:
        client = connect(arguments.port, arguments.connect_timeout, LOG)
        session = Session(client)
        session.input_path_trace = arguments.input_path_trace
        session.tap_fields = arguments.tap_frames
        print(f"[live] endpoint on 127.0.0.1:{arguments.port}, product pid {process.pid}, presenting "
              f"from frame {frame_of(client)} (leg: PSXPORT_X4_WIDESCREEN={wide}, sink {sink})")
        session.sample_opening_state()
        session.run_route(arguments.budget_frames, arguments.budget_seconds, arguments.poll_seconds,
                          arguments.shot_every, tap_frames=arguments.tap_frames)
        if arguments.hold and session.alive():
            session.hold_window(list(arguments.hold), arguments.seconds)
        elif arguments.hold:
            print(f"[live] the hold window was SKIPPED: the product is no longer running, so a held "
                  f"input could not be delivered. That is a skip, not a zero.")
        failures = report(session, client, LOG)
        try:
            client.quit()
        except OSError:
            pass
        client = None
        return 1 if failures else 0
    finally:
        if client is not None:
            client.close()
        print(f"[live] product pid {process.pid} exited {kill(process)}")


if __name__ == "__main__":
    raise SystemExit(main())
