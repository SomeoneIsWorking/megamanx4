#!/usr/bin/env python3
"""Play the Mega Man X4 port over its live debug server, census the front end's state machine and report what it did.

    uv run --frozen python tools/live_play.py
    uv run --frozen python tools/live_play.py --budget-frames 30000 --poll-seconds 0.4
    uv run --frozen python tools/live_play.py --hold right --seconds 8
    uv run --frozen python tools/live_play.py --selftest

The transport is `external/psxport/tools/dbgclient.py`; the menu model is `tools/title_prompts.py`.
The endpoint services one command per presented frame, so each census is a few contiguous `r` reads.
Taps are offered only where `title_prompts.wants_start` says the guest reads the pad (`unkD == 1`).
The run refuses rather than report zero when the endpoint never answers, a command is unimplemented,
census reads keep timing out, frames present without guest blocks, a held input moves no guest word,
or an address is no longer declared by its owning source.
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

# Framework owners: agent_environment (launch policy), present_geometry (image reader), dbgclient (live endpoint).
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

# Debug channel carrying `music_cd`'s tally, so the owner being reached is observable.
MUSIC_CD_CHANNEL = "x4-music-cd"
# Per-field input-path observer (game/input/input_path.cpp); opt-in via `--input-path-trace` because it is O(fields) lines.
INPUT_PATH_CHANNEL = "x4-input-path"
SERVER_TIMEOUT_PREFIX = "(debug server:"
# The libpad button halfword with nothing pressed; active low, so a held button clears its bit.
IDLE_ACTIVE_LOW = 0xFFFF

# `misc_objects` (0x1800 bytes) and the raw pad buffer are read on demand, not per poll.
POLL_READS = (
    (prompts.GAME_INFO, prompts.GAME_INFO_PROBE_BYTES, "game_info + handshake"),
    (prompts.CD_PROBE_BASE, prompts.CD_PROBE_BYTES, "CD machine state / error / result"),
    (prompts.STREAM_PROBE_BASE, prompts.STREAM_PROBE_BYTES, "music-active + guest field counter"),
    (prompts.ENGINE_PROBE_BASE, prompts.ENGINE_PROBE_BYTES, "engine_obj stage/substage"),
    (prompts.PAD_HELD, prompts.PAD_PROBE_BYTES, "pad 1 held / previous / pressed"),
    # Read every poll: the only level that shows whether a pad is attached and idle.
    (prompts.PAD_BUFFER, 4, "libpad packet: status, id and the active-low button halfword"),
    (prompts.PLAYER, prompts.PLAYER_PROBE_BYTES, "player object lens"),
)


SCENE_TOTALS = re.compile(
    r"totals:\s*poly=(-?\d+)\s+rect=(-?\d+)\s+line=(-?\d+)\s+fill=(-?\d+)\s+vramcopy=(-?\d+)\s+"
    r"upload=(-?\d+)\s+env=(-?\d+)")


def scene_prims(reply: str) -> tuple[int, str]:
    """The guest's classified display-list total and the verbatim totals line; -1 (unread) is not zero."""
    line = next((line for line in reply.splitlines() if "totals:" in line), "")
    match = SCENE_TOTALS.search(line)
    if not match:
        return -1, line.strip()
    return sum(int(value) for value in match.groups()), line.strip()


class Refusal(SystemExit):
    """A run that cannot honestly report the thing it was asked to report."""


# Per-field input-path observer line (game/input/input_path.cpp), printed either side of Pad::serviceFrame.
# The tap countdown is decremented inside serviceFrame, so the pre-service `tap_n` and the post-service
# `buttons` must be paired. Each stage is compared with the previous stage's value.
# Select by the bracketed channel tag the logger owns; a substring test also matched the config echo.
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

# Stages in the order the edge travels them. `endpoint` is measured from the reply to `tap`, not per field.
FIELD_STAGES = ("repl", "resolved", "gate", "guest")
# The last correct stage when each per-field stage is the first to break.
STAGE_BEFORE = {"repl": "endpoint", "resolved": "repl", "gate": "resolved", "guest": "gate"}


def truthy(token: str) -> bool:
    """A boolean as the product prints it: `int` members print 1/0, `bool` members true/false."""
    return token.strip().lower() in {"1", "true"}


def parse_input_path_counts(log: Path) -> tuple[list[dict], int, int]:
    """Every observer line, how many did not match, and how many disagreed with themselves."""
    parsed: list[dict] = []
    skipped = 0
    refused = 0
    if not log.is_file():
        return parsed, skipped, refused
    for line in log.read_text(errors="replace").splitlines():
        if not INPUT_PATH_TAG.search(line):
            continue
        match = INPUT_PATH_LINE.search(line.strip())
        if not match:
            skipped += 1
            continue
        row = match.groupdict()
        # The line carries the packet bytes and the halfword read back from them; a disagreement is a refused line.
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
    """Where the edge died: the last stage at which it was still correct, over every edge field.

    Pre/post lines are paired; an unpaired line is counted, never treated as a passing field. For each
    field whose pre-service `tap_n` > 0 the expected mask is `repl_tap`, and the stages are compared in order:

        repl      the drive was armed (`on`) with a non-idle mask
        resolved  post-service `buttons` == the mask the pre-service line used
        gate      the framework's BIOS-pad gate permits the write
        guest     the guest's slot-0 packet button halfword == the resolved mask

    The answer is the earliest broken stage across all edge fields.
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
    # A trailing pre-service line with no partner is counted as a hole.
    if pending is not None:
        unpaired += 1

    for entry in fields:
        pre, post, expected = entry["pre"], entry["post"], entry["expected"]
        stages = entry["stages"]
        stages["repl"] = bool(pre["on"] and expected != IDLE_ACTIVE_LOW)
        stages["resolved"] = post["buttons"] == expected
        stages["gate"] = post["gate"]
        # The observer's mem_r16 read of the halfword at +2, not this tool's slice of the bytes.
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
    # A non-zero `pressed` is the guest acknowledging the edge (its router converts the active-low packet).
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
    """One command, refusing the three replies that are not answers.

    The server's timeout notice, an empty reply (socket closed) and a `? <line>` reply (command not in
    this binary: a stale build) all raise. A timeout is retried, since a stalled frame mid-movie is
    legitimate.
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
    """One guest byte read; the reply is `ADDR: HH HH ...`, split on the last colon.

    A short reply raises. `tolerate_hole` is for the best-effort reads (the `misc_objects` sweep and pad words
    around a hold) and returns b"" for a short answer or an exhausted timeout."""
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
    """Real presented frames; this title has no temporal path, so `interp` stays 0."""
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
    """The dynarec's counters from the running process, plus the raw reply.

    The `guest:` and `fallback:` lines both name `calls` and `instructions`, so they stay in separate dicts."""
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
    """The configuration the product is running now, with the layer each value came from and the env variables that matched no knob."""
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
    """Read `misc_objects` (96 x 0x60 bytes, 256 per command) and count populated records with `title_prompts.count_misc_populated`."""
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
    """Photograph what is presented and measure it: distinct colours, non-black share, and for later captures the fraction of changed pixels.

    The park clear colour is RGB(8,8,16), so a non-black share alone cannot tell a frozen picture from a live one (docs/issues/0028)."""
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
    """Pixels that differ between two captures, with their denominator and bounding box."""
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
    """What the headless audio sink captured, from the file's own header; a zero-peak file is reported as silence."""
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
    """Any other product instance on this machine."""
    listing = subprocess.run(["ps", "-eo", "pid,etimes,args"], capture_output=True, text=True,
                             check=True).stdout
    return [line.strip() for line in listing.splitlines()
            if "megamanx4_port" in line and "ps -eo" not in line]


def launch(port: int, sink: str, wide: str, log: Path, wav: Path,
           input_path_trace: bool = False) -> subprocess.Popen:
    """The product: headless, silent, unpaced, live endpoint on this run's own port.

    `agent_environment` refuses without a named settings file. PSXPORT_DEBUG_SERVER lifts the headless
    frame cap (native_boot.cpp). PSXPORT_DEBUG is set at launch so the movie phase is observed.
    PSXPORT_PRESENT_SINK fixes the readback size (1284x720 is 4/3 of the 428-wide widescreen
    projection). The caller's environment is kept so the product finds a Vulkan ICD and a config dir.
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
    log.write_text("")  # the logger appends
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
    """The play-through; every step counts what it did."""

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
        # Distinct pad-word values seen while a tap was witnessed, and taps that changed no packet word.
        self.pad_words_seen: dict[str, set[int]] = {}
        self.tap_unwitnessed = 0
        self.tap_witnessed = 0
        # Recorded rather than inferred from the log, so a channel that was off is not read as "nothing wrong".
        self.input_path_trace = False
        # Tap length, and what one endpoint read costs in presented frames; a read costing more than a tap spans cannot witness it.
        self.tap_fields = 4
        self.read_cost_samples = 0
        self.read_cost_frames = 0
        # Read-back samples actually taken, to divide commands by samples.
        self.tap_probes = 0
        # Sampled once the endpoint answers and kept, since asking again after a crash finds a closed socket.
        self.opening: dict = {}
        # How the run ended; None means the window was spent normally. Printed first so a crash is not read as a verdict.
        self.stopped: str | None = None
        self.stopped_at_frame: int | None = None

    def sample_opening_state(self) -> None:
        """Configuration, dynarec counters and present counter, taken while the product is alive (`cvars` only here; it does not change)."""
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

    def census(self) -> tuple[prompts.Screen, int, int]:
        """One census: front-end state machine, pad words, raw pad word, player lens and the presented-frame interval.

        The poll list is checked against the decoder's required cells so a missing read cannot decode as zero."""
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
            # An unread display list leaves the prim count at -1, which means "not read", not "no scene".
            screen = prompts.decode(blocks)
        frame_after = frame_of(self.client)
        self.observations += 1
        # Re-sampled each poll so the last good reading survives a product that dies.
        try:
            self.opening["guest"] = guest_execution(self.client)
            self.opening["frame"] = presented(self.client)
        except (OSError, Refusal):
            pass
        return screen, frame_after, frame_before

    def record(self, screen: prompts.Screen, frame: int) -> None:
        self.screens.append(screen)
        self.frames.append(frame)


    def tap(self, button: str, frames: int, screen: prompts.Screen) -> None:
        """Issue a pad edge spanning `frames` presented frames and read the guest's pad words back over it.

        A press+release inside one frame can be invisible to the guest. Every distinct value seen is
        recorded: a delivered tap must show in `packet`, and a decoded one also in `pressed`. One read
        costs many presented frames (see `measure_read_cost`), so the delivery verdict comes from the
        per-field observer.
        """
        ask(self.client, f"tap {button} {frames}")
        self.answers += 1
        self.pad_commands += 1
        seen: dict[str, set[int]] = {"packet": set(), "held": set(), "pressed": set()}
        # The read-back must land in the edge, not span it; bounded because each read costs many presented frames.
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
        # Only-idle means the edge was not delivered; an empty set cannot occur since idle is itself an observation.
        if seen["packet"] and seen["packet"] <= {IDLE_ACTIVE_LOW}:
            self.tap_unwitnessed += 1
        else:
            self.tap_witnessed += 1

    def measure_read_cost(self, samples: int = 12) -> float | None:
        """Presented frames one endpoint read costs, or None if it could not be measured.

        The read-back is only sound if a read is finer than the edge (issue 0030).
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
        """Did the edge reach the guest's words, and at which level?

        `Pad::fillBuffer` (pad_input.cpp:66) writes status, id, then an active-low button mask at +2.
        `packet` is what the host wrote to the libpad buffer; held/previous/pressed is the guest's decoded
        trio. An edge can reach the first and not the second.
        """
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
        """Hold buttons for a wall-clock window and report what moved in the guest's words.

        Pad words are sampled before the press too. A product that dies inside the window is a recorded
        outcome, not an exception, so the report still prints what was measured.
        """
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
            # Recorded so the report prints the skipped window.
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
        # Settle before sampling: the release is only accepted at the endpoint until the guest's router runs.
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
        """A capture, or None; a dead product ends the run instead of raising."""
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

    def run_route(self, budget_frames: int, budget_seconds: float, poll_seconds: float,
                  shot_every: int, tap_frames: int = 4) -> None:
        """Poll the census across the window, photograph it, and offer a pad edge only where the front end reads one."""
        print(f"[live] route: watching the front end for up to {budget_frames} presented frames / "
              f"{budget_seconds:.0f}s, censusing every {poll_seconds:.2f}s, photographing every "
              f"{shot_every or 'no'} frame(s), tapping over {tap_frames} field(s) per edge")
        # Measured before any tap so the report can say whether the read-back could witness the edges.
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
            # Every step is guarded, including the frame poll, so a crash is a reported outcome.
            try:
                now = frame_of(self.client)
                spent = now - first
                if spent >= budget_frames or time.monotonic() - started > budget_seconds:
                    print(f"[live] window spent at presented frame {now} ({spent} frames of route, "
                          f"{self.observations} observations, {self.answers} menu answers)")
                    break
                # Only a timed-out read is a census hole; any other refusal means the product is gone.
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
                # The tap witness is inside the guard too: the product can die during a tap.
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
                # Tap only where the front end reads the pad and the screen has been still for a poll.
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
                # The product is gone: record it and still report what was measured.
                self.stopped = (f"the product stopped answering the endpoint "
                                f"({type(error).__name__}: {str(error).splitlines()[0][:140]})")
                self.stopped_at_frame = self.frames[-1] if self.frames else None
                print(f"[live] {self.stopped} after presented frame {self.stopped_at_frame}. The "
                      f"census, the legs reached, the taps and the captures so far are still "
                      f"reported below.")
                break
        # Final photograph, guarded because the product may be gone.
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
    """Everything the run measured, with its denominators.

    The endpoint may already be gone, so live queries are wrapped and report NOT MEASURED instead of a zero."""
    census = prompts.census_tally(session.screens, session.frames)
    # The scene leg is judged on the guest's prims; many colours with few prims is a false positive.
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
    # `misc_objects` is read once, reported as populated / records read (the park has 1 of 96).
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
    # Report the read-back's cost first: a read costing more frames than a tap spans reports idle for a delivered tap (issue 0030).
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
    # Reported whether or not the observer was enabled, so "no lines" is not read as "no finding".
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
    # Latest per-poll sample; `when` says which, since counters from the end of the run are not the census's set.
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
              "no temporal path (X4Runtime::renderCapabilities). That is out of scope for this "
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
    """Kill by the PID this tool launched, never by name."""
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=30)
    return process.returncode


def selftest() -> int:
    """The analysis half of this tool on fixtures: no product is launched.

    Each function carrying a conclusion has a case that would change its answer. The census, route and
    falsifier live in `tools/title_prompts.py`, whose selftest is separate."""
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
        """A `dbgclient.LiveClient` answering from a table; it raises on any command the table lacks."""

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

    # read_bytes: full, short and unparsable answers
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
    # The address prefix is hex, so splitting on the first colon would read the label as data.
    check("read_bytes does not read the address prefix as data",
          read_bytes(FixtureClient({"r 80173C70 1": "80173C70: AB\n"}), 0x80173C70, 1), b"\xab")

    # picture_diff on synthetic pixel buffers
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

    # guest_execution: the two lines must not merge
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

    # ask(): the three replies that are not answers
    total += 1
    try:
        ask(FixtureClient({}), "guest")
    except Refusal as error:
        print(f"  ok   an unimplemented command is refused as a stale build: {str(error)[:96]}...")
    else:
        failures += 1
        print("  FAIL an unimplemented command was answered")
    # The server answers a line it could not service with the timeout notice; two attempts, no answer.
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
    # ... and a timeout that clears is an answer, not a hole.
    recovering = FixtureClient({"frame": f"{SERVER_TIMEOUT_PREFIX} no frame in 4s)\n"})
    recovering.table["frame"] = "frame=42 interp=0 total=42 paused=0 disp=(0,0)\n"
    check("a timeout that clears is retried into an answer", frame_of(recovering), 42)

    # wav_report: silence must say SILENCE
    # Built chunk by chunk; a hand-typed header one field short still parses as a plausible WAV.
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

    # A dying product must still produce a report, not a traceback.
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
                # The park's classified display list: 2 prims.
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
            # The pad drive commands; the route offers edges and holds.
            if line.split()[0] in ("press", "release", "tap", "hold"):
                return f"{line}\n"
            count = int(line.split()[2])
            payload = " ".join("00" for _ in range(count))
            return f"{line.split()[1]}: {payload}\n"

        def close(self) -> None:
            pass

    class TapKillerClient(DyingClient):
        """A front end that reads Start (unkD == 1) and a socket that dies during a tap's read-back."""
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
                    # The tap is accepted; the read-back finds a dead socket.
                    self.dead = True
                    return f"tap {line.split()[1]} {line.split()[2]}\n"
            if line.startswith("r ") and line.split()[1].upper() == f"{prompts.GAME_INFO:08X}":
                # unkD is at game_info + 0x0D; the route offers a tap only when it is 1.
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
        """Answers until the hold window's first `frame` poll, then dies."""
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
    # Scene leg: the prim count decides it; thousands of colours with the park's 2 prims is not a scene.
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

    # Picture census: the park's colour count is still reported but is not the scene test.
    park_pixels = bytes(bytearray([8, 8, 16] + [0, 0, 0]) * 32)
    colours = {park_pixels[index:index + 3].hex() for index in range(0, len(park_pixels), 3)}
    check("the park's own picture really is the measured 2 colours", len(colours), prompts.PARK_COLOURS)
    check("so a colour count DOES separate the park from uninitialised VRAM — which is why it is "
          "not allowed to be the scene test", len(colours) > prompts.PARK_COLOURS, False)
    check("the two scene thresholds are the park's two MEASURED values, not magic constants",
          (prompts.PARK_COLOURS, prompts.PARK_PRIMS), (2, 2))

    # Per-field input-path observer: one fixture says both "delivered" and "broken" by moving one value.
    # The fixture uses the shipping spelling: `repl(on=...)` is an int and prints 1, `gate(...)` fields are bool and print true.
    def observer_line(phase: str, *, tap: int = 0xF7FF, tap_n: int = 0, buttons: int = 0xFFFF,
                      on: bool = True, gate: bool = True, slot0_buttons: int | None = None,
                      init: bool = True, irq: bool = True, bool_spelling: str = "true",
                      vbl: int = 100) -> str:
        written = tap if slot0_buttons is None else slot0_buttons
        # Fixture packet word: status/id in the low half, the active-low button halfword in the high half (0xFFF74100 for mask 0xFFF7).
        slot0 = ((written & 0xFFFF) << 16) | 0x0041
        flag = ((lambda value: "true" if value else "false") if bool_spelling == "true"
                else (lambda value: "1" if value else "0"))
        return (f"[{INPUT_PATH_CHANNEL}] {phase}: vbl={vbl} repl(on={flag(on)} tap=0x{tap:04X} "
                f"tap_n={tap_n} hold=0xFFFF) resolved(buttons=0x{buttons:04X}) "
                f"gate(initialized={flag(init)} irq_started={flag(irq)} "
                f"shouldService={flag(gate)}) "
                f"guest(slot0_bytes=0x{slot0:08X} slot0_buttons=0x{written:04X} "
                f"slot1_bytes=0x00FFFFFF slot1_buttons=0x0000 held=0x0000 pressed=0x0000)")

    # A record whose packed bytes and reported halfword disagree is refused and counted, not resolved in favour of either.
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

    # The reader accepts an int member as 1/0 and a bool member as true/false in the same line.
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
        # Delivered: the tap mask resolves into `buttons` and the guest packet carries it.
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

        # Opposite answer: the mask resolves but the gate is closed, so the packet is never written (issue 0030).
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

        # Gate open but packet still idle: isolates the write from the gate.
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

        # No edge at all is not a pass.
        idle = Path(directory) / "idle.log"
        idle.write_text("\n".join([
            observer_line("pre-service"),
            observer_line("post-service"),
        ]) + "\n")
        idle_verdict = input_path_verdict(parse_input_path_log(idle)[0], 0)
        check("a run that offered no edge counts no edge field", idle_verdict["edge_fields"], 0)
        check("... and therefore has no broken stage to name", idle_verdict["broken_at"], None)

        # A log format change is counted, not dropped.
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
        # The config echo names the channel without being a record; the selector is the channel tag.
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
    framework_dir = (REPO / "external" / "psxport").resolve()
    print(f"[live] product: {EXECUTABLE.relative_to(REPO)}  framework {framework_dir}")
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
