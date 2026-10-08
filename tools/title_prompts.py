#!/usr/bin/env python3
"""Front-end screen model and button rule for SLUS_005.61, read from guest words; the only owner of that model.

    uv run --frozen python tools/title_prompts.py --selftest

Addresses are symbols in external/mmx4/config/symbols.us.txt or constants this repo already owns.
`func_8001DAF8` (323C.c:1597) dispatches `D_800F21B0[game_info.unk0]`, so game_info state/sub-state is the
screen. `unkD` is the accept-input flag: `func_8001E708` reads Start only when it is 1.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field


GAME_INFO = 0x80173C70  # struct GameInfo, 0x10 bytes
GAME_INFO_SIZE = 0x10
# game_info + 0x14 is the byte func_8001DDB0 waits on and 0x80016BB8 raises (decomp D_80173C84).
HANDSHAKE = 0x80173C84
GAME_INFO_PROBE_BYTES = GAME_INFO_SIZE + 8  # 24: game_info (16) .. handshake (20) and four past it

MACHINE_STATE = 0x80139530  # music_cd::kMachineState
MUSIC_ACTIVE = 0x80141BD4  # music_cd::kMusicActive
GUEST_FIELD = 0x80141BD8  # the guest's own display-field counter
STICKY_ERROR = 0x8013952C  # music_cd::kError
RESULT_BYTE = 0x80139554  # music_cd::kResult, bit 6 = shell open
# One read of 0x80139520..0x80139557 covers the sticky error, machine state and result byte.
CD_PROBE_BASE = 0x80139520
CD_PROBE_BYTES = 0x38

STREAM_PROBE_BASE = MUSIC_ACTIVE - 4  # 0x80141BD0
STREAM_PROBE_BYTES = 0x10  # .. 0x80141BD7, so music-active and the field counter are in one read

ENGINE_OBJ = 0x801721C0  # size 0x64
STAGE = 0x801721CC  # engine_obj_stage
SUBSTAGE = 0x801721CD  # engine_obj_substage
ENGINE_PROBE_BASE = ENGINE_OBJ
ENGINE_PROBE_BYTES = 0x20  # .. 0x801721DF: stage, substage, 0x17 and the checkpoint byte

PAD_HELD = 0x80166C08  # player_object.h:37 kPadHeldP1
PAD_PREV = 0x80166C0A  # player_object.h:38 kPadPrevP1
PAD_PRESSED = 0x80166C0C  # player_object.h:39 kPadPressedP1 == symbols.us.txt controller_state
PAD_PROBE_BYTES = 6
PAD_BUFFER = 0x80166D68  # game/input/pad_layout.h:16 kSlot0Buffer (0x22 bytes)
PAD_BUFFER_PROBE_BYTES = 0x22

# libpad packet as written by psxport Pad::fillBuffer (pad_input.cpp:66): [0] status, [1] pad id 0x41,
# [2..3] button mask, active low. Bytes 0..1 are a constant header, not input.
PAD_STATUS = 0x00
PAD_ID = 0x01
PAD_BUTTON = 0x02

# Offsets of `x4::guest::PlayerOffsets` (docs/re-player-object.md); the C++ lens owns them, the owner check below catches drift.
PLAYER = 0x801418C8  # player_object.h:26 kPlayerAddress
PLAYER_ACTIVE = 0x00
PLAYER_ID = 0x01
PLAYER_CHARACTER = 0x02
PLAYER_STATE = 0x04
PLAYER_X = 0x0A  # s16 integer part, what the camera follows
PLAYER_Y = 0x0E
PLAYER_ANIM = 0x47
PLAYER_HITPOINTS = 0x5C
PLAYER_PROBE_BYTES = 0x60

MISC_OBJECTS = 0x80173CA0  # 96 records of 0x60
MISC_RECORD_SIZE = 0x60
MISC_RECORD_COUNT = 96

# XA/BGM jump table indexed by the machine state (music_cd.h kStepTable).
STEP_TABLE = 0x800F1AB0
# func_8001DAF8's own game-state jump table.
GAME_STATE_TABLE = 0x800F21B0

# Psy-Q pad bits (external/mmx4/include/psy-q-4.0/LIBETC.H:14-35).
PAD_START = 1 << 11  # PADstart = PADh
PAD_SELECT = 1 << 8  # PADselect = PADk

# The post-movie park (docs/issues/0028): every frame is 2 distinct colours (#080810, #000000).
# Colour count is not the scene test: uninitialised VRAM can carry thousands of colours.
PARK_COLOURS = 2
# At the park the guest submits 2 prims per frame (full-screen black rect + Gouraud triangle); the scene test is the guest's submitted prims.
PARK_PRIMS = 2
# The park is game state 1, sub-state 2.
PARK_GAME_STATE = 1
PARK_SUB_STATE = 2
# The XA/BGM machine runs only while music_cd::kMusicActive is 2 (gate at 0x800169D8).
POST_MOVIE_MUSIC_ACTIVE = 2
# Falsifier claim (docs/issues/0029): D_80173C84 reaches 2 and func_8001DDB0 leaves sub-state 2.
FALSIFIER_HANDSHAKE = 2


@dataclass(frozen=True)
class Screen:
    """One observation of the front end, decoded from guest words this run actually read."""

    game_state: int
    sub_state: int
    unk4: int
    unk_a: int
    accept_input: int
    previous_state: int
    handshake: int
    machine_state: int
    music_active: int
    guest_field: int
    sticky_error: int
    result_byte: int
    stage: int
    substage: int
    pad_held: int
    pad_previous: int
    pad_pressed: int
    pad_status: int
    pad_id: int
    pad_button: int
    player_active: int
    player_id: int
    player_character: int
    player_state: int
    player_x: int
    player_y: int
    player_anim: int
    player_hitpoints: int
    misc_populated: int = 0
    scene_prims: int = -1
    scene_totals: str = ""

    @property
    def controller_state(self) -> int:
        """The decomp's `controller_state`: the pressed edge word the front end tests."""
        return self.pad_pressed

    @property
    def shell_open(self) -> bool:
        """`music_cd::kShellOpenBit`; `func_80016B58` returns before its `CdlReadS` while it is set."""
        return bool(self.result_byte & (1 << 6))

    @property
    def in_music_machine(self) -> bool:
        return self.music_active == POST_MOVIE_MUSIC_ACTIVE

    @property
    def at_park(self) -> bool:
        """Whether this observation is the post-movie park."""
        return (self.game_state == PARK_GAME_STATE and self.sub_state == PARK_SUB_STATE
                and self.handshake != FALSIFIER_HANDSHAKE)

    @property
    def draws_a_scene(self) -> bool:
        """Whether the guest submitted more geometry than the park does; -1 (unread) is not False."""
        return self.scene_prims > PARK_PRIMS

    @property
    def falsifier_closed(self) -> bool:
        """The handshake byte reached 2, so `func_8001DDB0` ran its advance arm."""
        return self.handshake == FALSIFIER_HANDSHAKE

    def describe(self) -> str:
        return (f"game_info={self.game_state}/{self.sub_state} unk4={self.unk4} unkA={self.unk_a} "
                f"unkD={self.accept_input} handshake={self.handshake} "
                f"machine={self.machine_state} music_active={self.music_active} "
                f"field={self.guest_field} err={self.sticky_error} "
                f"result=0x{self.result_byte:02X}{' (shell open)' if self.shell_open else ''} "
                f"stage={self.stage}/{self.substage} "
                f"prims={'not read' if self.scene_prims < 0 else self.scene_prims} "
                f"pad held=0x{self.pad_held:04X} prev=0x{self.pad_previous:04X} "
                f"pressed=0x{self.pad_pressed:04X} packet(status=0x{self.pad_status:02X} "
                f"id=0x{self.pad_id:02X} button=0x{self.pad_button:04X} active-low) "
                f"player(active={self.player_active} id={self.player_id} "
                f"char={self.player_character} state={self.player_state} "
                f"xy={self.player_x},{self.player_y} anim={self.player_anim} "
                f"hp={self.player_hitpoints}) misc={self.misc_populated}/{MISC_RECORD_COUNT}")


@dataclass
class Leg:
    """One route leg: a name, the question that ends it, and the pad button offered meanwhile (None = wait it out)."""

    name: str
    reached: "callable"
    button: str | None = None
    why: str = ""


# Every cell `decode` requires and its byte count; the driver must poll all of them.
PROBE_REQUIREMENTS: dict[int, int] = {
    GAME_INFO: GAME_INFO_PROBE_BYTES,
    CD_PROBE_BASE: CD_PROBE_BYTES,
    STREAM_PROBE_BASE: STREAM_PROBE_BYTES,
    ENGINE_PROBE_BASE: ENGINE_PROBE_BYTES,
    PAD_HELD: PAD_PROBE_BYTES,
    PAD_BUFFER: 4,
    PLAYER: PLAYER_PROBE_BYTES,
}


def _u8(raw: bytes, index: int) -> int:
    return raw[index]


def _u16(raw: bytes, index: int) -> int:
    """A little-endian halfword out of a byte read."""
    return raw[index] | (raw[index + 1] << 8)


def _s16(raw: bytes, index: int) -> int:
    """A signed little-endian halfword (the player lens position fields are s16)."""
    value = _u16(raw, index)
    return value - 0x10000 if value >= 0x8000 else value


def _s8(raw: bytes, index: int) -> int:
    value = raw[index]
    return value - 0x100 if value >= 0x80 else value


def decode(raw_blocks: dict[int, bytes], *, scene_prims: int = -1, scene_totals: str = "") -> Screen:
    """Decode one census from the named byte reads; a missing block raises rather than reading as zero."""
    game = raw_blocks.get(GAME_INFO)
    cd = raw_blocks.get(CD_PROBE_BASE)
    stream = raw_blocks.get(STREAM_PROBE_BASE)
    engine = raw_blocks.get(ENGINE_PROBE_BASE)
    pad = raw_blocks.get(PAD_HELD)
    buffer = raw_blocks.get(PAD_BUFFER)
    player = raw_blocks.get(PLAYER)
    for name, block, want in (("game_info", game, GAME_INFO_PROBE_BYTES),
                              ("cd state", cd, CD_PROBE_BYTES),
                              ("stream state", stream, STREAM_PROBE_BYTES),
                              ("engine_obj", engine, ENGINE_PROBE_BYTES),
                              ("pad trio", pad, PAD_PROBE_BYTES),
                              ("pad packet", buffer, 4),
                              ("player object", player, PLAYER_PROBE_BYTES)):
        if block is None or len(block) < want:
            got = "absent" if block is None else f"{len(block)} of {want} bytes"
            raise ValueError(f"census is missing the {name} read ({got}); a cell that was not read is "
                             f"not zero")
    misc = raw_blocks.get(MISC_OBJECTS)
    return Screen(
        game_state=_u8(game, 0x00),
        sub_state=_u8(game, 0x01),
        unk4=_u16(game, 0x04),
        unk_a=_u8(game, 0x0A),
        accept_input=_u8(game, 0x0D),
        previous_state=_u8(game, 0x0E),
        handshake=_u8(game, HANDSHAKE - GAME_INFO),
        machine_state=_u16(cd, MACHINE_STATE - CD_PROBE_BASE),
        music_active=_u8(stream, MUSIC_ACTIVE - STREAM_PROBE_BASE),
        guest_field=_u8(stream, GUEST_FIELD - STREAM_PROBE_BASE),
        sticky_error=_u16(cd, STICKY_ERROR - CD_PROBE_BASE),
        result_byte=_u8(cd, RESULT_BYTE - CD_PROBE_BASE),
        stage=_u8(engine, STAGE - ENGINE_PROBE_BASE),
        substage=_u8(engine, SUBSTAGE - ENGINE_PROBE_BASE),
        pad_held=_u16(pad, PAD_HELD - PAD_HELD),
        pad_previous=_u16(pad, PAD_PREV - PAD_HELD),
        pad_pressed=_u16(pad, PAD_PRESSED - PAD_HELD),
        pad_status=_u8(buffer, PAD_STATUS),
        pad_id=_u8(buffer, PAD_ID),
        pad_button=_u16(buffer, PAD_BUTTON),
        player_active=_u8(player, PLAYER_ACTIVE),
        player_id=_u8(player, PLAYER_ID),
        player_character=_u8(player, PLAYER_CHARACTER),
        player_state=_u8(player, PLAYER_STATE),
        player_x=_s16(player, PLAYER_X),
        player_y=_s16(player, PLAYER_Y),
        player_anim=_u8(player, PLAYER_ANIM),
        player_hitpoints=_s8(player, PLAYER_HITPOINTS),
        misc_populated=count_misc_populated(misc) if misc is not None else 0,
        scene_prims=scene_prims,
        scene_totals=scene_totals,
    )


def count_misc_populated(raw: bytes | None) -> int:
    """How many complete `MISC_OBJECTS` records have either of their first two ID bytes non-zero (the park has 1)."""
    if raw is None:
        return 0
    complete = len(raw) // MISC_RECORD_SIZE
    populated = 0
    for index in range(complete):
        base = index * MISC_RECORD_SIZE
        if raw[base] or raw[base + 1]:
            populated += 1
    return populated



def leg_post_movie(screen: Screen) -> bool:
    """The movie phase is over: the XA/BGM machine is entered (`kMusicActive == 2`, gate at 0x800169D8)."""
    return screen.in_music_machine


def leg_left_park(screen: Screen) -> bool:
    """The falsifier's intermediate claim: sub-state 2 released the guest."""
    return screen.falsifier_closed and screen.sub_state != PARK_SUB_STATE


def wants_start(screen: Screen) -> bool:
    """Whether the front end's own code reads Start: `func_8001E708` does only while `unkD == 1`."""
    return screen.accept_input == 1


ROUTE: tuple[Leg, ...] = (
    Leg("post-movie XA/BGM machine entered", leg_post_movie, button=None,
        why="waited out: nothing on this leg reads the pad before the movie ends, and the falsifier's "
            "state word is only meaningful once the machine is running"),
    Leg("sub-state 2 released (issue 0029's intermediate falsifier)", leg_left_park, button="start",
        why="`func_8001E708` reads Start while unkD==1, and this is the state that sets unkD=1"),
    Leg("a stage scene is on screen", None, button=None,
        why="judged from the guest's own CLASSIFIED DISPLAY LIST, not from the picture: the park submits "
            f"{PARK_PRIMS} prims per frame and a scene submits more, while a colour count cannot tell a "
            "scene from uninitialised VRAM. `reached` is None because the answer is a property of the "
            "captures rather than of one screen. The colour count of every capture is printed beside "
            "the prim count, and a capture with many colours and few prims is reported as a MISMATCH "
            "rather than as a scene."),
)

# The third leg's `reached` is None: the run judges it from the captures, not from a screen.


def leg3_from_captures(prim_counts: list[int]) -> bool:
    """The third leg: some capture submitted more prims than the park does (an unread count of -1 never qualifies)."""
    return any(count > PARK_PRIMS for count in prim_counts)


def census_tally(screens: list[Screen], frames: list[int]) -> dict:
    """The census summary: observations, per (game state, sub state) counts, and the presented frames each pair held."""
    pairs: dict[tuple[int, int], dict] = {}
    for screen, frame in zip(screens, frames):
        key = (screen.game_state, screen.sub_state)
        entry = pairs.setdefault(key, {"observations": 0, "first_frame": frame, "last_frame": frame,
                                       "handshakes": set(), "machine_states": set(),
                                       "at_park": 0})
        entry["observations"] += 1
        entry["last_frame"] = frame
        entry["handshakes"].add(screen.handshake)
        entry["machine_states"].add(screen.machine_state)
        if screen.at_park:
            entry["at_park"] += 1
    for entry in pairs.values():
        entry["handshakes"] = sorted(entry["handshakes"])
        entry["machine_states"] = sorted(entry["machine_states"])
        entry["frames_held"] = entry["last_frame"] - entry["first_frame"] + 1
    machine_states: dict[int, int] = {}
    for screen in screens:
        machine_states[screen.machine_state] = machine_states.get(screen.machine_state, 0) + 1
    # Held, previous and pressed each get their own distribution.
    pad_words = {"held": {}, "previous": {}, "pressed": {}}
    for screen in screens:
        for name, value in (("held", screen.pad_held), ("previous", screen.pad_previous),
                            ("pressed", screen.pad_pressed)):
            pad_words[name][value] = pad_words[name].get(value, 0) + 1
    return {
        "observations": len(screens),
        "first_frame": frames[0] if frames else None,
        "last_frame": frames[-1] if frames else None,
        "frames_covered": (frames[-1] - frames[0]) if frames else 0,
        "game_states": pairs,
        "machine_states": machine_states,
        "handshake_reached": any(s.falsifier_closed for s in screens),
        "park_observations": sum(1 for s in screens if s.at_park),
        "accept_input_ones": sum(1 for s in screens if s.accept_input == 1),
        "pad_words": pad_words,
        "musics": {s.music_active for s in screens},
    }



_OWNER_STATE = re.compile(r"machine-state word 0x80139530 is (\d+)")


def owner_state_steps(music_cd_lines: list[str]) -> list[int]:
    """The machine-state word as the owner logged it at each step it served.

    The 6 -> 5 -> 1 chain completes inside one display field, which a coarse census cannot resolve."""
    steps = []
    for line in music_cd_lines:
        match = _OWNER_STATE.search(line)
        if match:
            steps.append(int(match.group(1)))
    return steps


def falsifier_verdict(tally: dict, music_cd_lines: list[str]) -> tuple[str, str]:
    """Issue 0029's falsifier, as one of five verdicts with the evidence behind it.

    ADVANCED: the state word was 6 and left 6. REFUSED-BY-OWNER / FALSIFIER FIRES / NOT REACHED: it
    stayed at 6 and the owner refused / logged the leaf / logged nothing. NOT EXERCISED: it was never 6
    in the census or the owner's log.
    """
    census_states = tally["machine_states"]
    observations = tally["observations"]
    owner_steps = owner_state_steps(music_cd_lines)
    # Union of the coarse census and the owner's per-step log.
    combined = dict(census_states)
    for state in owner_steps:
        combined[state] = combined.get(state, 0) + 1
    sources = (f"census samples {dict(sorted(census_states.items()))} over {observations} "
               f"observation(s); the owner's per-step log recorded {owner_steps}")

    if not combined:
        return ("UNMEASURED",
                f"no observation of the machine-state word 0x{MACHINE_STATE:08X} was taken, by the census "
                f"or by the owner's log, so this run cannot answer the falsifier")
    if 6 not in combined:
        return ("NOT EXERCISED",
                f"the machine-state word 0x{MACHINE_STATE:08X} was never 6 in either source — "
                f"{sources} — so this run never reached the state the falsifier is about and says "
                f"NOTHING about whether the substituted owner works")
    moved = {state: count for state, count in combined.items() if state != 6}
    served = [line for line in music_cd_lines if "CdSync 0x800E5D20 served" in line]
    refusals = [line for line in music_cd_lines if "refused" in line.lower()]

    if moved:
        reached = ("yes" if tally["handshake_reached"] else "no")
        return ("ADVANCED",
                f"the machine-state word 0x{MACHINE_STATE:08X} was 6 and then left it: {sources}. The "
                f"handshake byte 0x{HANDSHAKE:08X} reached {FALSIFIER_HANDSHAKE}: {reached} by the "
                f"census's own observation(s), and the owner served {len(served)} CdSync edge(s). The "
                f"substituted CdSync owner was reached and the chain moved. Note WHICH source saw the "
                f"6: the whole 6-5-1 chain completes inside one display field, so a census sampling once "
                f"per ~100 fields may not resolve it, and the owner's per-step log is the record that "
                f"does")
    if refusals:
        return ("REFUSED-BY-OWNER",
                f"the machine-state word stayed 6 ({sources}) and the owner logged {len(refusals)} "
                f"refusal line(s); the first is: {refusals[0]}")
    if served:
        return ("FALSIFIER FIRES",
                f"the machine-state word 0x{MACHINE_STATE:08X} is still 6 in every observation either "
                f"source recorded ({sources}) while the owner served {len(served)} CdSync edge(s) — the "
                f"substituted owner WAS reached and the state word still did not move, so issue 0029's "
                f"mechanism is wrong a third time. First served line: {served[0]}")
    return ("NOT REACHED",
            f"the machine-state word is still 6 in all {observations} observation(s) and the owner "
            f"logged no CdSync edge at all, so the leaf was never offered on those observations. That is "
            f"NOT evidence that the owner is wrong; it is an absent measurement")


_SOURCES = {
    "title_prompts.py": ("GAME_INFO", "MACHINE_STATE", "MUSIC_ACTIVE", "CONTROLLER_STATE", "HANDSHAKE"),
    "music_cd.h": ("kMachineState", "kMusicActive", "kResult", "kShellOpenBit"),
    "pad_layout.h": ("kSlot0Buffer",),
}


def verify_address_owners(repo_root) -> tuple[int, int, list[str]]:
    """Every address this model reads must still be declared at the same value by its owning source; reports matched of scanned."""
    import re as _re
    from pathlib import Path

    root = Path(repo_root)
    owners = {
        "tools/title_prompts.py": [("GAME_INFO", GAME_INFO), ("MACHINE_STATE", MACHINE_STATE),
                                   ("MUSIC_ACTIVE", MUSIC_ACTIVE), ("PAD_PRESSED", PAD_PRESSED),
                                   ("HANDSHAKE", HANDSHAKE), ("ENGINE_OBJ", ENGINE_OBJ),
                                   ("MISC_OBJECTS", MISC_OBJECTS), ("STEP_TABLE", STEP_TABLE),
                                   ("PLAYER", PLAYER)],
        "game/media/music_cd.h": [("kMachineState", MACHINE_STATE), ("kMusicActive", MUSIC_ACTIVE),
                                 ("kError", STICKY_ERROR), ("kResult", RESULT_BYTE),
                                 ("kStepTable", STEP_TABLE)],
        "game/input/pad_layout.h": [("kSlot0Buffer", PAD_BUFFER)],
        "game/title/player_object.h": [("kPlayerAddress", PLAYER), ("kPadHeldP1", PAD_HELD),
                                      ("kPadPressedP1", PAD_PRESSED)],
    }
    matched = 0
    scanned = 0
    disagreements: list[str] = []
    for relative, declarations in owners.items():
        path = root / relative
        if not path.is_file():
            disagreements.append(f"{relative} is missing; this model reads addresses it owns")
            scanned += len(declarations)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, value in declarations:
            scanned += 1
            pattern = _re.compile(rf"\b{_re.escape(name)}\b[^=\n]*=\s*(0x)?([0-9A-Fa-f]{{7,8}})u?\b")
            found = pattern.search(text)
            if not found:
                disagreements.append(f"{relative} no longer declares {name} at 0x{value:08X}")
            elif int(found.group(2), 16) != value:
                disagreements.append(f"{relative} declares {name} = 0x{int(found.group(2), 16):08X}, "
                                     f"this model reads 0x{value:08X}")
            else:
                matched += 1
    return matched, scanned, disagreements


def _fixture(overrides: dict[int, bytes] | None = None) -> dict[int, bytes]:
    """One census's worth of byte blocks at the measured post-movie park values (docs/issues/0028)."""
    blocks = {
        GAME_INFO: bytes(GAME_INFO_PROBE_BYTES),
        CD_PROBE_BASE: bytes(CD_PROBE_BYTES),
        STREAM_PROBE_BASE: bytes(STREAM_PROBE_BYTES),
        ENGINE_PROBE_BASE: bytes(ENGINE_PROBE_BYTES),
        PAD_HELD: bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
        PAD_BUFFER: bytes([0x00, 0x41, 0xFF, 0xFF]),  # status, id, active-low button word
        PLAYER: bytes(PLAYER_PROBE_BYTES),
    }
    cd = bytearray(CD_PROBE_BYTES)
    cd[MACHINE_STATE - CD_PROBE_BASE] = 0x06
    blocks[CD_PROBE_BASE] = bytes(cd)
    stream = bytearray(STREAM_PROBE_BYTES)
    stream[MUSIC_ACTIVE - STREAM_PROBE_BASE] = 0x02
    stream[GUEST_FIELD - STREAM_PROBE_BASE] = 0x2A
    blocks[STREAM_PROBE_BASE] = bytes(stream)
    engine = bytearray(ENGINE_PROBE_BYTES)
    engine[STAGE - ENGINE_PROBE_BASE] = 0x0E
    blocks[ENGINE_PROBE_BASE] = bytes(engine)
    game = bytearray(GAME_INFO_PROBE_BYTES)
    game[0] = PARK_GAME_STATE
    game[1] = PARK_SUB_STATE
    game[HANDSHAKE - GAME_INFO] = 0x01  # issue 0028: the park's handshake byte is 1, not 2
    blocks[GAME_INFO] = bytes(game)
    blocks.update(overrides or {})
    return blocks


def selftest() -> int:
    """Feed each verdict function the input that would change its answer; the owner check runs on a fixture tree."""
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

    park = decode(_fixture())
    check("park decodes to game state 1 / sub-state 2", (park.game_state, park.sub_state),
          (PARK_GAME_STATE, PARK_SUB_STATE))
    check("park decodes handshake byte 1", park.handshake, 1)
    check("park decodes machine state 6", park.machine_state, 6)
    check("park decodes music-active 2", park.music_active, POST_MOVIE_MUSIC_ACTIVE)
    check("park decodes the guest field counter", park.guest_field, 0x2A)
    check("park decodes stage 14 / substage 0", (park.stage, park.substage), (0x0E, 0))
    check("park decodes controller_state (the pressed edge word)", park.controller_state, 0)
    check("park decodes the libpad packet header as status+id, not as input",
          (park.pad_status, park.pad_id), (0x00, 0x41))
    check("park decodes the packet's own button halfword as idle (active low, 0xFFFF)",
          park.pad_button, 0xFFFF)
    # The header is the constant 0x00,0x41; only the button halfword carries input.
    pressed = decode(_fixture({PAD_BUFFER: bytes([0x00, 0x41, 0xFF, 0xE7])}))  # ~Start == 0xE7FF
    check("a pressed Start shows in the packet's button halfword",
          pressed.pad_button, 0xE7FF)
    check("... and the header bytes are unchanged by it",
          (pressed.pad_status, pressed.pad_id), (park.pad_status, park.pad_id))
    check("... so the header alone cannot tell an idle pad from a pressed one",
          (park.pad_status, park.pad_id), (pressed.pad_status, pressed.pad_id))
    check("park decodes the player lens as inactive", park.player_active, 0)
    check("park is the park", park.at_park, True)
    check("park has NOT closed the falsifier", park.falsifier_closed, False)
    check("park leaves the shell closed", park.shell_open, False)
    check("post-movie leg accepts the park", leg_post_movie(park), True)
    check("left-park leg rejects the park", leg_left_park(park), False)

    # Falsifier pass: handshake reaches 2 and sub-state 2 releases.
    cleared_game = bytearray(GAME_INFO_PROBE_BYTES)
    cleared_game[0] = PARK_GAME_STATE
    cleared_game[1] = 0x03  # func_8001DDB0's `arg0->mode++`
    cleared_game[4] = 0x0A  # its own unk4 countdown
    cleared_game[0x0A] = 0x02  # unkA, which func_8001DE20 sets on the way
    cleared_game[0x0D] = 0x01  # unkD: this is the state that sets the accept-input flag
    cleared_game[0x0E] = PARK_GAME_STATE
    cleared_game[HANDSHAKE - GAME_INFO] = FALSIFIER_HANDSHAKE
    cleared = decode(_fixture({GAME_INFO: bytes(cleared_game)}))
    check("cleared screen closes the falsifier", cleared.falsifier_closed, True)
    check("cleared screen is not the park", cleared.at_park, False)
    check("left-park leg accepts the cleared screen", leg_left_park(cleared), True)
    check("cleared screen accepts Start (unkD=1)", wants_start(cleared), True)
    check("park screen does not accept Start (unkD=0)", wants_start(park), False)

    # A census missing a read is refused, not zero-filled.
    total += 1
    try:
        broken = _fixture()
        del broken[PAD_HELD]
        decode(broken)
    except ValueError as error:
        print(f"  ok   a census missing a read is refused: {error}")
    else:
        failures += 1
        print("  FAIL a census missing a read decoded anyway, which reports an unprobed cell as zero")
    # ... including the player read.
    total += 1
    try:
        broken = _fixture()
        del broken[PLAYER]
        decode(broken)
    except ValueError as error:
        print(f"  ok   a census missing the player read is refused: {error}")
    else:
        failures += 1
        print("  FAIL a census missing the player read decoded anyway")

    # Short `misc_objects` reads only the records it has.
    total += 1
    short = bytes(MISC_RECORD_SIZE * 40)
    check("short misc_objects reports the records it read", count_misc_populated(short), 0)
    full = bytearray(MISC_RECORD_SIZE * MISC_RECORD_COUNT)
    full[0] = 0xFF  # issue 0028's one populated record
    full[MISC_RECORD_SIZE * 5] = 0xFF
    check("full misc_objects counts 2 of 96", count_misc_populated(bytes(full)), 2)

    # The falsifier's four answers.
    served = ["[x4-music-cd] CdSync 0x800E5D20 served for state 6 (0x80016E34, edge 0x80016E48) -> CdlComplete"]
    check("falsifier FIRES when the state word stays 6 with the owner serving it",
          falsifier_verdict({"observations": 9, "machine_states": {6: 9}, "handshake_reached": False},
                            served)[0], "FALSIFIER FIRES")
    check("verdict says NOT REACHED when the owner was never offered the leaf",
          falsifier_verdict({"observations": 9, "machine_states": {6: 9}, "handshake_reached": False},
                            [])[0], "NOT REACHED")
    check("verdict says ADVANCED when the state word left 6",
          falsifier_verdict({"observations": 9, "machine_states": {6: 1, 5: 4, 1: 4},
                             "handshake_reached": True}, served)[0], "ADVANCED")
    check("verdict says REFUSED-BY-OWNER when the owner refused",
          falsifier_verdict({"observations": 9, "machine_states": {6: 9}, "handshake_reached": False},
                            ["[x4-music-cd] XA/BGM CD step refused: the noblock argument is not the "
                             "image's 1"])[0], "REFUSED-BY-OWNER")
    check("verdict says UNMEASURED with no observation at all",
          falsifier_verdict({"observations": 0, "machine_states": {}, "handshake_reached": False},
                            served)[0], "UNMEASURED")
    # A run that only saw the movie phase has the word at 0, which must not read as "left 6".
    check("verdict says NOT EXERCISED when the state word was never 6",
          falsifier_verdict({"observations": 9, "machine_states": {0: 9, 7: 1},
                             "handshake_reached": False}, served)[0], "NOT EXERCISED")
    check("... and a run that only ever saw 0 says so rather than claiming an advance",
          falsifier_verdict({"observations": 9, "machine_states": {0: 9},
                             "handshake_reached": False}, [])[0], "NOT EXERCISED")
    check("... while a run that saw 6 AND something else still reads ADVANCED",
          falsifier_verdict({"observations": 9, "machine_states": {0: 4, 6: 3, 2: 2},
                             "handshake_reached": True}, served)[0], "ADVANCED")
    # The owner's per-step log is a second source for a chain that completes inside one field.
    stepped = ["[x4-music-cd] CdSync 0x800E5D20 served for state 6 ... machine-state word 0x80139530 is 6",
               "[x4-music-cd] CdControl 0x800E5D90 served for state 6 ... machine-state word 0x80139530 is 6",
               "[x4-music-cd] CdSync 0x800E5D20 served for state 5 ... machine-state word 0x80139530 is 5",
               "[x4-music-cd] CdSync 0x800E5D20 served for state 1 ... machine-state word 0x80139530 is 1"]
    check("the owner's per-step state words are read out of its log", owner_state_steps(stepped), [6, 6, 5, 1])
    check("a census that never saw 6 but whose owner log did reads ADVANCED, not NOT EXERCISED",
          falsifier_verdict({"observations": 7, "machine_states": {0: 7}, "handshake_reached": False},
                            stepped)[0], "ADVANCED")
    check("a run whose owner log never reached 6 either is NOT EXERCISED",
          falsifier_verdict({"observations": 7, "machine_states": {0: 7}, "handshake_reached": False},
                            [])[0], "NOT EXERCISED")

    # The second observation has a different machine state.
    moved_screen = decode(_fixture({CD_PROBE_BASE: bytes(
        [0] * (MACHINE_STATE - CD_PROBE_BASE) + [0x01, 0x00]
        + [0] * (CD_PROBE_BYTES - MACHINE_STATE - 2 + CD_PROBE_BASE))}))
    tallied = census_tally([park, moved_screen, cleared], [100, 200, 900])
    check("census counts its observations", tallied["observations"], 3)
    check("census counts the park observations", tallied["park_observations"], 2)
    check("census reports the frame span", tallied["frames_covered"], 800)
    check("census holds state 1/2 for 101 fields (frames 100..200 inclusive)",
          tallied["game_states"][(PARK_GAME_STATE, PARK_SUB_STATE)]["frames_held"], 101)
    check("census names the machine states it saw", tallied["machine_states"], {6: 2, 1: 1})
    # Held, previous and pressed are reported separately.
    check("census reports the three pad words as three distributions",
          sorted(tallied["pad_words"]), ["held", "pressed", "previous"])
    check("census's pressed distribution is the decomp's controller_state",
          tallied["pad_words"]["pressed"], tallied["pad_words"]["pressed"])
    # Three differing pad words must give three differing distributions.
    edged = decode(_fixture({PAD_HELD: bytes([0x11, 0x00, 0x22, 0x00, 0x33, 0x00])}))
    edged_tally = census_tally([edged, park], [10, 20])
    check("census keeps the held word, the previous word and the pressed edge apart",
          (edged_tally["pad_words"]["held"], edged_tally["pad_words"]["previous"],
           edged_tally["pad_words"]["pressed"]),
          ({0x0011: 1, 0: 1}, {0x0022: 1, 0: 1}, {0x0033: 1, 0: 1}))

    # The address-owner check must produce BOTH verdicts on a fixture tree.
    import tempfile
    with tempfile.TemporaryDirectory(dir=str(__import__("pathlib").Path.cwd() / "scratch")
                                     if (__import__("pathlib").Path.cwd() / "scratch").is_dir()
                                     else None) as scratch:
        from pathlib import Path as _Path
        tree = _Path(scratch) / "fixture"
        (tree / "tools").mkdir(parents=True)
        (tree / "game/media").mkdir(parents=True)
        (tree / "game/input").mkdir(parents=True)
        (tree / "game/title").mkdir(parents=True)
        (tree / "tools/title_prompts.py").write_text(
            f"GAME_INFO = 0x{GAME_INFO:08X}u\nMACHINE_STATE = 0x{MACHINE_STATE:08X}u\n"
            f"MUSIC_ACTIVE = 0x{MUSIC_ACTIVE:08X}u\nPAD_PRESSED = 0x{PAD_PRESSED:08X}u\n"
            f"HANDSHAKE = 0x{HANDSHAKE:08X}u\nENGINE_OBJ = 0x{ENGINE_OBJ:08X}u\n"
            f"MISC_OBJECTS = 0x{MISC_OBJECTS:08X}u\nSTEP_TABLE = 0x{STEP_TABLE:08X}u\n"
            f"PLAYER = 0x{PLAYER:08X}u\n")
        (tree / "game/media/music_cd.h").write_text(
            f"inline constexpr std::uint32_t kStepTable = 0x{STEP_TABLE:08X}u;\n"
            f"inline constexpr std::uint32_t kMachineState = 0x{MACHINE_STATE:08X}u;\n"
            f"inline constexpr std::uint32_t kMusicActive = 0x{MUSIC_ACTIVE:08X}u;\n"
            f"inline constexpr std::uint32_t kError = 0x{STICKY_ERROR:08X}u;\n"
            f"inline constexpr std::uint32_t kResult = 0x{RESULT_BYTE:08X}u;\n"
            f"inline constexpr std::uint32_t kShellOpenBit = 0x40u;\n")
        (tree / "game/input/pad_layout.h").write_text(
            f"inline constexpr std::uint32_t kSlot0Buffer = 0x{PAD_BUFFER:08X}u;\n")
        (tree / "game/title/player_object.h").write_text(
            f"inline constexpr uint32_t kPlayerAddress = 0x{PLAYER:08X}u;\n"
            f"inline constexpr uint32_t kPadHeldP1 = 0x{PAD_HELD:08X}u;\n"
            f"inline constexpr uint32_t kPadPressedP1 = 0x{PAD_PRESSED:08X}u;\n")
        matched, scanned, disagreements = verify_address_owners(tree)
        check("owner check accepts a fixture that agrees", (matched == scanned, disagreements), (True, []))
        # Now the case that WOULD fail: an owner that names a different address.
        (tree / "game/input/pad_layout.h").write_text(
            "inline constexpr std::uint32_t kSlot0Buffer = 0x80000000u;\n")
        matched, scanned, disagreements = verify_address_owners(tree)
        check("owner check refuses a disagreeing owner", matched < scanned, True)
        check("owner check NAMES the disagreement", disagreements != [], True)
        # ... and an owner that stopped declaring the address at all.
        (tree / "game/input/pad_layout.h").write_text("// the buffer moved into a typed owner\n")
        matched, scanned, disagreements = verify_address_owners(tree)
        check("owner check refuses an owner that stopped declaring it", matched < scanned, True)

    if failures:
        print(f"  selftest: {failures} of {total} case(s) FAILED")
        return 1
    print(f"  selftest: {total - failures}/{total} cases behaved as required.")
    print("  The load-bearing pairs are: the park decoding AS the park (so 'it cleared' means something),")
    print("  and the falsifier answering FIRES on a served leaf with a state word that never moved (so the")
    print("  mechanism can be retired by evidence rather than by absence of evidence).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true",
                        help="decode fixtures, run the falsifier over all four of its answers, and "
                             "check the address owners on a fixture tree; drives nothing")
    arguments = parser.parse_args()
    if arguments.selftest:
        return selftest()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
