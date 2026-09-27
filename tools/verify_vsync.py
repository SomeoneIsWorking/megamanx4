#!/usr/bin/env python3
"""Verify MMX4's VBlank wait/IRQ contract directly from the retail executable."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from config_windows import platform_hle_windows

# The instruction readers are NOT reimplemented here. They are the same measurements
# tools/verify_str_completion.py makes about the same executable, and a second copy of a decoder is a
# second thing that can be wrong: whichever one is right is not the one a reader checked.
from verify_str_completion import (
    VerificationError,
    expect_address,
    expect_branch,
    expect_word,
    signed16,
    word,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
SYNC_HEADER = ROOT / "game/core/vsync_sync.h"
SYNC_SOURCE = ROOT / "game/core/vsync_sync.cpp"
FRAME_SOURCE = ROOT / "game/core/x4_frame_driver.cpp"
CONFIG_SOURCE = ROOT / "game/core/game_config.cpp"
# The movie-scoped alias header was DELETED, not renamed. It existed only so two call sites kept
# compiling while the VSync entry moved out of the movie's ownership, and keeping it would have
# left the entry able to acquire a second owner again. So this gate now asserts the header is ABSENT
# and that no source still reaches the VSync owner through the old namespace.
MOVIE_HEADER = ROOT / "game/core/movie_field.h"

EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"
TEXT_VADDR = 0x80010000
TEXT_FILE_OFFSET = 0x800

VSYNC = 0x800E4DB0
WAIT = 0x800E4EF8
WAIT_END = 0x800E4F94
IRQ_INIT = 0x800E56A4
IRQ_HANDLER = 0x800E56FC
IRQ_TABLE = 0x8011DC30
VBLANK_COUNTER = 0x8011DC50

# The entry's own state, and the two CELLS that name the registers its return value samples. The
# cells are inside the loaded text image, so their values come from the file; and no instruction in
# the resident text ever stores either of them, which is what makes them the image's own constants
# rather than something this port may choose. `verify_register_cells` proves the second half.
LAST_SAMPLE = 0x8011CB8C
LAST_SYNC = 0x8011CB90
GPUSTAT_CELL = 0x8011CB84
RCNT1_CELL = 0x8011CB88
GPUSTAT = 0x1F801814
RCNT1 = 0x1F801110

# The per-mode decision tree, address by address. This is what `x4::vsync::fieldsForMode` and
# `serveVSync` reproduce, and the field counts are DERIVED from it rather than chosen.
MODE_QUERY_BRANCH = 0x800E4DE8   # bgez a0 -> the wait arms
MODE_ONE_COMPARE = 0x800E4E04    # beq a0,1 -> the epilogue, skipping both waits and both stores
MODE_ZERO_BRANCH = 0x800E4E0C    # blez a0 -> the mode-0 target
MODE_N_BASE = 0x800E4E14         # mode >= 2: the target starts from kLastSync
MODE_N_BIAS = 0x800E4E20         # ... minus one
MODE_N_ADD = 0x800E4E28          # ... plus the mode
MODE_ZERO_BASE = 0x800E4E2C      # mode 0: the target IS kLastSync
SECOND_WAIT_COUNTER = 0x800E4E5C # the second wait samples the counter
SECOND_WAIT_TARGET = 0x800E4E68  # ... and asks for one past it
RETRACE_GATE = 0x800E4E70        # and v0,0x0040 -> the GPUSTAT arm
LAST_SYNC_STORE = 0x800E4ECC
LAST_SAMPLE_STORE = 0x800E4EDC
EPILOGUE_JR = 0x800E4EF0
WAIT_SPIN_SHIFT = 0x800E4EFC     # a1 << 15: the wait's a1 is a SPIN BUDGET
WAIT_SPIN_ABORT = 0x800E4F38     # ... spent when it reaches -1

# The mode every one of the 42 sites passes, as the image states it. Counted by the census below and
# not transcribed, because a transcribed list is a list that can go stale without failing.
EXPECTED_SITE_COUNT = 42


@dataclass(frozen=True)
class Inputs:
    exe: bytes
    header: str
    source: str
    frame: str
    config: str
    movie: str = ""
    call_sites: dict = dataclasses.field(default_factory=dict)


def jal_target(instruction: int, pc: int) -> int:
    if instruction >> 26 != 3:
        raise VerificationError(f"0x{pc:08X} is not jal (word 0x{instruction:08X})")
    return ((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)


def expect_jal(image: bytes, pc: int, target: int, label: str) -> None:
    actual = jal_target(word(image, pc), pc)
    if actual != target:
        raise VerificationError(
            f"{label}: jal at 0x{pc:08X} targets 0x{actual:08X}, want 0x{target:08X}"
        )


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def built_address(image: bytes, lui_pc: int, low_pc: int) -> int:
    upper = word(image, lui_pc)
    lower = word(image, low_pc)
    if upper >> 26 != 0x0F:
        raise VerificationError(f"0x{lui_pc:08X} is not lui")
    reg = (upper >> 16) & 0x1F
    opcode = lower >> 26
    base = (lower >> 21) & 0x1F
    if base != reg or opcode not in {0x09, 0x20, 0x21, 0x23, 0x28, 0x29, 0x2B}:
        raise VerificationError(f"0x{low_pc:08X} does not consume the lui register")
    return ((upper & 0xFFFF) << 16) + signed16(lower & 0xFFFF)


def expect_address(
    image: bytes, lui_pc: int, low_pc: int, expected: int, label: str
) -> None:
    actual = built_address(image, lui_pc, low_pc) & 0xFFFFFFFF
    if actual != expected:
        raise VerificationError(f"{label}: 0x{actual:08X}, want 0x{expected:08X}")


def expect_immediate(
    image: bytes, pc: int, opcode: int, rt: int, rs: int, imm: int, label: str
) -> None:
    instruction = word(image, pc)
    fields = (
        instruction >> 26,
        (instruction >> 16) & 0x1F,
        (instruction >> 21) & 0x1F,
        instruction & 0xFFFF,
    )
    expected = (opcode, rt, rs, imm & 0xFFFF)
    if fields != expected:
        raise VerificationError(
            f"{label}: word 0x{instruction:08X} has fields {fields}, want {expected}"
        )


def c_string(image: bytes, address: int) -> str:
    offset = TEXT_FILE_OFFSET + address - TEXT_VADDR
    end = image.find(b"\0", offset)
    if end < 0:
        raise VerificationError(f"unterminated string at 0x{address:08X}")
    return image[offset:end].decode("ascii")


def source_constant(text: str, name: str) -> int:
    match = re.search(rf"\b{name}\s*=\s*(0x[0-9A-Fa-f]+)u?\s*;", text)
    if not match:
        raise VerificationError(f"source constant {name} is missing")
    return int(match.group(1), 16)


def jump_target(instruction: int, pc: int) -> int:
    if instruction >> 26 != 0x02:
        raise VerificationError(f"0x{pc:08X} is not j (word 0x{instruction:08X})")
    return ((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)


def expect_jump(image: bytes, pc: int, target: int, label: str) -> None:
    actual = jump_target(word(image, pc), pc)
    if actual != target:
        raise VerificationError(f"{label}: j at 0x{pc:08X} targets 0x{actual:08X}, want 0x{target:08X}")


# The mode dispatch's branches are bgez (REGIMM) and blez, neither of which is the beq/bne family
# verify_str_completion's branch_target covers. This is the missing instruction FORMS, not a second
# decoder for the ones already covered: the mode dispatch's first branch is the bgez that decides
# whether a negative mode ever reaches a wait.
MODE_BRANCH_OPCODES = frozenset({0x01, 0x04, 0x05, 0x06, 0x07})


def expect_mode_branch(image: bytes, pc: int, target: int, label: str) -> None:
    instruction = word(image, pc)
    if instruction >> 26 not in MODE_BRANCH_OPCODES:
        raise VerificationError(f"{label}: 0x{pc:08X} is not a branch (word 0x{instruction:08X})")
    actual = (pc + 4) + (signed16(instruction & 0xFFFF) << 2)
    if actual != target:
        raise VerificationError(
            f"{label}: branch at 0x{pc:08X} goes to 0x{actual:08X}, want 0x{target:08X}"
        )


# MIPS memory opcodes and LUI, for a writer census that depends on no dataflow at all. A constant-
# propagating sweep can MISS a writer, and a missed writer is exactly what would make "nothing stores
# this cell" a false claim.
MEMORY_OPCODES = frozenset(
    {0x09, 0x0D, 0x20, 0x21, 0x23, 0x24, 0x25, 0x28, 0x29, 0x2A, 0x2B, 0x30, 0x38, 0x0F}
)
STORE_OPCODES = frozenset({0x28, 0x29, 0x2A, 0x2B, 0x38})


def store_sites(image: bytes, addresses: tuple[int, ...]) -> dict[int, list[int]]:
    """Every `sw`/`sh`/`sb`/`sw*` whose 16-bit immediate is the low half of one of `addresses`.

    Deliberately dumb and over-reporting: an address reachable as `lui` + `addiu` with a displacement,
    as `lui` + `ori`, or through a pointer all appear or do not appear here, and the claim this backs
    is only ever "no instruction in the resident text names this word with a store immediate".
    """
    found: dict[int, list[int]] = {address: [] for address in addresses}
    resident = len(image) - TEXT_FILE_OFFSET
    for index in range(resident // 4):
        instruction = struct.unpack_from("<I", image, TEXT_FILE_OFFSET + index * 4)[0]
        if instruction >> 26 not in STORE_OPCODES:
            continue
        immediate = instruction & 0xFFFF
        for address in addresses:
            if immediate in (address & 0xFFFF, (address - 0x10000) & 0xFFFF):
                found[address].append(TEXT_VADDR + index * 4)
    return found


def call_sites(image: bytes, target: int) -> list[int]:
    """Every `jal` or `j` in the resident image whose destination is `target`.

    BOTH forms reach this entry and they are not interchangeable for a reader: a `jal` site sets r[31]
    itself, a `j` site does not. libetc VSync's epilogue is `lw ra / ... / jr ra`, so r[31] is the
    right continuation for either, but the CENSUS has to count both to be 42.
    """
    sites: list[int] = []
    resident = len(image) - TEXT_FILE_OFFSET
    for index in range(resident // 4):
        instruction = struct.unpack_from("<I", image, TEXT_FILE_OFFSET + index * 4)[0]
        if instruction & 0xFC000000 != 0x0C000000:
            continue
        pc = TEXT_VADDR + index * 4
        if (((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)) == target:
            sites.append(pc)
    return sites


def delay_slot_mode(image: bytes, pc: int) -> int | None:
    """The mode a call/j site passes, when its DELAY SLOT states one.

    A `jal`/`j` delay slot runs BEFORE its callee, so `addiu a0,zero,K` there is the argument the leaf
    actually receives and overrides whatever a0 held. `None` means the site does not state a mode and
    the value is register-determined, which is a fact about the image rather than a hole in the census.
    """
    slot = word(image, pc + 4)
    if slot >> 26 == 0x09 and ((slot >> 16) & 0x1F) == 4:  # addiu a0,zero,K
        immediate = slot & 0xFFFF
        return immediate - 0x10000 if immediate & 0x8000 else immediate
    if slot == 0x00002021:  # addu a0,zero,zero — this compiler's `move a0,zero`
        return 0
    return None


def verify_mode_contract(inputs: Inputs) -> list[str]:
    """The per-mode decision tree, address by address. This is the whole owner."""
    image = inputs.exe
    epilogue = 0x800E4EE0
    expect_word(image, MODE_QUERY_BRANCH, 0x04810005, "bgez a0 leaves the query arm")
    expect_mode_branch(image, MODE_QUERY_BRANCH, 0x800E4E00, "a non-negative mode skips the query")
    expect_jump(image, 0x800E4DF8, epilogue, "the query arm returns straight from the epilogue")
    expect_word(image, MODE_ONE_COMPARE, 0x10820036, "mode 1 is compared against a literal 1")
    expect_mode_branch(image, MODE_ONE_COMPARE, epilogue, "mode 1 returns without waiting")
    expect_word(image, MODE_ZERO_BRANCH, 0x18800007, "a non-positive mode takes the mode-0 target")
    expect_mode_branch(image, MODE_ZERO_BRANCH, MODE_ZERO_BASE, "mode 0 targets kLastSync itself")
    expect_address(image, MODE_ZERO_BASE, MODE_ZERO_BASE + 4, LAST_SYNC, "mode-0 target")
    expect_address(image, MODE_N_BASE, MODE_N_BASE + 4, LAST_SYNC, "mode>=2 target base")
    expect_word(image, MODE_N_BIAS, 0x2442FFFF, "mode>=2 target is biased by -1")
    expect_word(image, MODE_N_ADD, 0x00441021, "mode>=2 target adds the mode")
    expect_address(image, 0x800E4E58, SECOND_WAIT_COUNTER, VBLANK_COUNTER, "the second wait")
    expect_word(image, SECOND_WAIT_TARGET, 0x24840001, "the second wait asks for one past the counter")
    expect_address(image, LAST_SYNC_STORE - 4, LAST_SYNC_STORE, LAST_SYNC, "last-sync store")
    expect_address(image, LAST_SAMPLE_STORE - 4, LAST_SAMPLE_STORE, LAST_SAMPLE, "last-sample store")
    expect_word(image, RETRACE_GATE, 0x02021024, "the GPUSTAT arm is `and v0,s0,v0`")
    expect_word(image, EPILOGUE_JR, 0x03E00008, "the epilogue is jr ra / nop")
    return [
        f"libetc VSync 0x{VSYNC:08X} per mode, from the image: mode < 0 returns "
        f"[0x{VBLANK_COUNTER:08X}] with no wait and no state write (0x{MODE_QUERY_BRANCH:08X}); "
        f"mode 1 returns at 0x{MODE_ONE_COMPARE:08X} skipping BOTH waits and BOTH stores; mode 0 "
        f"targets 0x{LAST_SYNC:08X} and mode >= 2 targets it plus mode - 1 "
        f"(0x{MODE_N_BASE:08X}/0x{MODE_N_BIAS:08X}/0x{MODE_N_ADD:08X}); the second wait always asks "
        f"for the counter plus one. So the host fields a mode costs are max(mode, 1) for mode != 1"
    ]


def verify_wait_helper_budget(inputs: Inputs) -> list[str]:
    """The wait helper's a1 is a SPIN BUDGET, not a field count. Without this the counts are a guess."""
    image = inputs.exe
    expect_word(image, WAIT_SPIN_SHIFT, 0x00052BC0, "the wait shifts a1 left by 15")
    expect_word(image, WAIT_SPIN_ABORT, 0x1443000C, "the wait compares the decremented budget with -1")
    expect_address(image, 0x800E4F04, 0x800E4F08, VBLANK_COUNTER, "the wait's counter load")
    expect_address(image, 0x800E4F6C, 0x800E4F70, VBLANK_COUNTER, "the wait's loop counter load")
    expect_word(image, 0x800E4F10, 0x0044102A, "the wait spins while the counter is below its target")
    return [
        "the wait helper 0x800E4EF8 spends a1<<15 iterations before its retail 'VSync: timeout\\n' "
        "abort, so a1 bounds SPINS and never adds a field: the field count is entirely in a0, which "
        "is what fieldsForMode is derived from"
    ]


def verify_register_cells(inputs: Inputs) -> list[str]:
    """The two cells the return value samples, their image values, and that nothing writes them."""
    image = inputs.exe
    for cell, register, name in (
        (GPUSTAT_CELL, GPUSTAT, "GPUSTAT"),
        (RCNT1_CELL, RCNT1, "root counter 1"),
    ):
        actual = word(image, cell)
        if actual != register:
            raise VerificationError(
                f"the cell at 0x{cell:08X} holds 0x{actual:08X} in the retail image, want the "
                f"{name} address 0x{register:08X}"
            )
    stores = store_sites(image, (GPUSTAT_CELL, RCNT1_CELL))
    for address, sites in stores.items():
        if sites:
            raise VerificationError(
                f"0x{address:08X} is stored at {['0x%08X' % s for s in sites]}; the owner reads the "
                "register this cell names, and a writer would make the register a runtime choice "
                "instead of the image's own constant"
            )
    # The two state words the entry keeps are its own: only it reads and only it writes them, so the
    # owner maintaining them is faithful bookkeeping rather than invented state.
    for word_address, label in ((LAST_SYNC, "last-sync"), (LAST_SAMPLE, "last-sample")):
        sites = store_sites(image, (word_address,))[word_address]
        allowed = {LAST_SYNC_STORE, LAST_SAMPLE_STORE} & set(sites)
        if not allowed or set(sites) - allowed:
            raise VerificationError(
                f"the {label} word 0x{word_address:08X} is stored at {['0x%08X' % s for s in sites]}, "
                "which is not exactly the entry's own two stores"
            )
    return [
        f"0x{GPUSTAT_CELL:08X} and 0x{RCNT1_CELL:08X} hold 0x{GPUSTAT:08X} and 0x{RCNT1:08X} in the "
        f"retail image and are named by loads only — the owner reads the registers out of the guest's "
        f"own cells. 0x{LAST_SYNC:08X} and 0x{LAST_SAMPLE:08X} are written at exactly "
        f"0x{LAST_SYNC_STORE:08X} and 0x{LAST_SAMPLE_STORE:08X}, which is this entry, and read "
        f"nowhere else"
    ]


def verify_mode_census(inputs: Inputs) -> list[str]:
    """Every site in the image, counted from the image, with the mode its delay slot states."""
    image = inputs.exe
    sites = call_sites(image, VSYNC)
    if len(sites) != EXPECTED_SITE_COUNT:
        raise VerificationError(
            f"libetc VSync 0x{VSYNC:08X} has {len(sites)} jal/j call site(s), want "
            f"{EXPECTED_SITE_COUNT}"
        )
    tally: dict[str, int] = {}
    for site in sites:
        mode = delay_slot_mode(image, site)
        key = "register-determined" if mode is None else f"VSync({mode})"
        tally[key] = tally.get(key, 0) + 1
    # A `jal` and a `j` to the same entry are the same override key, and the census has to include
    # both: five of these sites are tail calls whose delay slot states no mode.
    expected = {"VSync(0)": 7, "VSync(2)": 4, "VSync(3)": 11, "VSync(-1)": 14}
    for key, count in expected.items():
        if tally.get(key) != count:
            raise VerificationError(
                f"{key} has {tally.get(key, 0)} site(s) in the image, want {count} ({tally})"
            )
    if sum(expected.values()) + tally.get("register-determined", 0) != EXPECTED_SITE_COUNT:
        raise VerificationError(f"the mode census does not account for all sites: {tally}")
    if "VSync(1)" in tally:
        raise VerificationError(
            f"a site passes mode 1, whose measured contract waits for nothing at all: {tally}"
        )
    return [
        f"all {EXPECTED_SITE_COUNT} sites of libetc VSync, counted from the image by each site's own "
        f"delay slot: {tally}. Mode 1 is passed by NO site, so the measured `wait for nothing` arm is "
        f"real but unreachable; and because a `jal`'s delay slot runs BEFORE its callee, these are the "
        f"modes the leaf actually receives, not the modes the surrounding code appears to set"
    ]


def verify_shipping_owner(inputs: Inputs) -> list[str]:
    """The entry is SERVED, by the title, for every mode the retail body defines."""
    if inputs.movie:
        raise VerificationError(
            "game/core/movie_field.h exists again, so the libetc VSync entry can acquire a second "
            "owner: the whole point of vsync_sync.{h,cpp} is that one file owns the entry for all 42 "
            "call sites, and an alias header is how that regressed once already"
        )
    for token, label in (
        ("kVblankCounter = 0x8011DC50u", "the measured VBlank counter"),
        ("kRegisterCell0 = 0x8011CB84u", "the GPUSTAT cell"),
        ("kRegisterCell1 = 0x8011CB88u", "the RCNT1 cell"),
        ("kLastSample = 0x8011CB8Cu", "the last-sample word"),
        ("kLastSync = 0x8011CB90u", "the last-sync word"),
        ("mode == 1 ? 0u : (mode == 0 ? 1u", "the field-count rule"),
    ):
        if token not in inputs.header:
            raise VerificationError(f"vsync_sync.h is missing {label} ({token!r})")
    for token, label in (
        ('guest::install(core, kVSync, "vsync::serveVSync", serveVSync)', "the entry install"),
        ("yieldField(c, returnAddress, threads)", "the field wait"),
        ("bios_threads::from(c)", "the parkable task seam"),
        ("kLastSync, c.mem_r32(kVblankCounter)", "the last-sync write"),
        ("kLastSample, c.mem_r32(c.mem_r32(kRegisterCell1))", "the last-sample write"),
        ("ExecutionExitReason::FrameBoundary", "the field boundary exit"),
        ("returnAddress,", "the r[31] resume the exit states"),
        ("inTaskFiber()", "the refusal when there is no task to park"),
    ):
        if token not in inputs.source:
            raise VerificationError(f"vsync_sync.cpp is missing {label} ({token!r})")
    # The two call sites that used the alias now name vsync directly, and nothing may reach the owner
    # through the old namespace again.
    for path, text in inputs.call_sites.items():
        for gone, label in (
            ("x4::movie::", "the deleted namespace alias"),
            ('#include "movie_field.h"', "the deleted header"),
            ("movie::registerOverrides", "the old registration spelling"),
        ):
            if gone in text:
                raise VerificationError(f"{path} still reaches the VSync owner via {label} ({gone})")
    return [
        "x4::vsync owns the whole libetc VSync entry: the query arm, the per-mode field counts, both "
        "state words and the r[31] frame-boundary exit, with a refusal that names the site when a "
        "positive mode has no retail task to park. The movie-scoped alias header that used to sit "
        "beside it is deleted rather than renamed, so the entry cannot acquire a second owner"
    ]


def verify(inputs: Inputs, *, check_digest: bool = True) -> list[str]:
    digest = hashlib.sha1(inputs.exe).hexdigest()
    if check_digest and digest != EXPECTED_SHA1:
        raise VerificationError(
            f"executable SHA-1 {digest}, want retail {EXPECTED_SHA1}"
        )

    checks: list[str] = []

    # VSync retains its own guest-visible policy and calls only the narrow wait helper twice.
    expect_address(
        inputs.exe, 0x800E4DF0, 0x800E4DF4, VBLANK_COUNTER, "VSync(-1) counter query"
    )
    expect_jal(inputs.exe, 0x800E4E40, WAIT, "VSync first wait")
    expect_jal(inputs.exe, 0x800E4E64, WAIT, "VSync next-field wait")
    checks.append("VSync calls the same counter wait twice and keeps its query path")

    # The helper's entire reason to exist is the counter wait. Its timeout string provides an
    # independent retail classification; no matching-decomp symbol is consulted.
    expect_address(
        inputs.exe, 0x800E4F04, 0x800E4F08, VBLANK_COUNTER, "wait initial counter load"
    )
    expect_address(
        inputs.exe, 0x800E4F6C, 0x800E4F70, VBLANK_COUNTER, "wait loop counter load"
    )
    expect_address(
        inputs.exe, 0x800E4F40, 0x800E4F44, 0x80011900, "wait timeout string"
    )
    if c_string(inputs.exe, 0x80011900) != "VSync: timeout\n":
        raise VerificationError("retail wait diagnostic is not 'VSync: timeout\\n'")
    if word(inputs.exe, 0x800E4F8C) != 0x03E00008 or word(inputs.exe, 0x800E4F90) != 0:
        raise VerificationError(
            "wait helper does not end in jr ra / nop at measured boundary"
        )
    checks.append(
        "wait helper spins on the IRQ counter and occupies [0x800E4EF8,0x800E4F94)"
    )

    # IRQ init: zero the same counter, clear exactly 8 callbacks, register handler for IRQ 0.
    expect_address(inputs.exe, 0x800E56A8, 0x800E56AC, IRQ_TABLE, "IRQ callback table")
    expect_address(
        inputs.exe, 0x800E56C4, 0x800E56C8, VBLANK_COUNTER, "IRQ counter clear"
    )
    expect_jal(inputs.exe, 0x800E56CC, 0x800E57A0, "IRQ callback-table clear")
    expect_immediate(inputs.exe, 0x800E56D0, 0x09, 5, 0, 8, "callback count")
    expect_address(
        inputs.exe, 0x800E56D4, 0x800E56D8, IRQ_HANDLER, "IRQ handler address"
    )
    expect_jal(inputs.exe, 0x800E56DC, 0x800E4FC4, "IRQ registrar call")
    if word(inputs.exe, 0x800E56E0) != 0x00002021:
        raise VerificationError(
            "IRQ registrar delay slot does not set a0 = 0 (IRQ VBlank)"
        )
    checks.append("init registers 0x800E56FC for IRQ 0 after clearing 8 callback slots")

    # IRQ handler: one tick, then an exact eight-entry indirect callback walk.
    expect_address(
        inputs.exe, 0x800E56FC, 0x800E5700, VBLANK_COUNTER, "handler counter read"
    )
    expect_immediate(inputs.exe, 0x800E5720, 0x09, 2, 2, 1, "handler counter increment")
    expect_address(
        inputs.exe, 0x800E5724, 0x800E5728, VBLANK_COUNTER, "handler counter write"
    )
    expect_address(
        inputs.exe, 0x800E5714, 0x800E5718, IRQ_TABLE, "handler callback cursor"
    )
    if word(inputs.exe, 0x800E5744) & 0x3F != 9:
        raise VerificationError("handler callback site is not jalr")
    expect_immediate(inputs.exe, 0x800E5750, 0x0A, 2, 17, 8, "handler callback bound")
    checks.append("IRQ-0 handler increments once and walks exactly 8 callbacks")

    # Independently classify the observed runtime chain. The retail literal says CD_init, while
    # the actual call edges lead from the retry wrapper to CD initialization/command code and then
    # to VSync(-1) for a 960-field deadline.
    expect_jal(inputs.exe, 0x800E5ADC, 0x800E5C14, "observed retry -> reset edge")
    expect_jal(inputs.exe, 0x800E5C3C, 0x800E74DC, "observed reset -> CD init edge")
    expect_address(inputs.exe, 0x800E74E0, 0x800E74E4, 0x80011BF4, "CD init diagnostic")
    if c_string(inputs.exe, 0x80011BF4) != "CD_init:":
        raise VerificationError(
            "0x800E74DC does not reference the retail 'CD_init:' literal"
        )
    expect_jal(inputs.exe, 0x800E7638, 0x800E6E14, "CD init -> command edge")
    expect_jal(inputs.exe, 0x800E6FDC, VSYNC, "CD command -> VSync query edge")
    expect_immediate(inputs.exe, 0x800E6FE0, 0x09, 4, 0, -1, "VSync(-1) mode")
    checks.append(
        "retail bodies reproduce the observed CD-init -> command -> VSync chain"
    )

    # Shipping wiring moves the field boundary into the native frame driver and traps the FULL
    # VSync entry. The old helper remains retail evidence only; it is not an admitted HLE window.
    if (
        source_constant(inputs.header, "kVSync") != VSYNC
        or source_constant(inputs.header, "kVSyncEntryEnd") != VSYNC + 4
    ):
        raise VerificationError(
            "shipping full-VSync trap constants disagree with the retail entry"
        )
    # WHY `spu_audio.frameLogic()` IS NOT AMONG THESE. The framework's own header
    # (runtime/psx/spu_audio.h) documents it as the SBS/dual-core variant — "advance XA for game logic
    # only, no output" — and lists it as called from game_tomba2.cpp's frame body, which is a
    # two-Game title. This list used to require BOTH frameLogic() and frame(), which is Tomba! 2's call
    # pattern asserted at a single-core title: X4 owns one Game, mixes one field of samples per
    # display field, and has no second core to advance XA for. The expectation was red on the shipping
    # source and nobody had looked at whether the SOURCE or the EXPECTATION was wrong.
    #
    # The ordering below is the real content and it is unchanged: the pad is serviced, then the SPU
    # mixes its field, then the presentation commits that field. Requiring frameLogic() as well would
    # assert another title's architecture, not a stronger audio contract.
    for token in (
        "kVblankHandler = 0x800E56FCu",
        "kSetInterruptTable = 0x8011CB98u",
        "const uint32_t vblankHandler = c->mem_r32",
        "guest::call(c, vblankHandler)",
        "c->game->pad.serviceFrame()",
        "c->game->spu_audio.frame()",
        "c->game->presentation.commit(c, 1)",
    ):
        if token not in inputs.source:
            raise VerificationError(
                f"shipping synchronization source is missing {token!r}"
            )
    # ...and the field order itself, which is what the token list cannot express.
    ordered = ("c->game->pad.serviceFrame()", "c->game->spu_audio.frame()",
               "c->game->presentation.commit(c, 1)")
    positions = [inputs.source.find(token) for token in ordered]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise VerificationError(
            "the shipping field order is not pad.serviceFrame() -> spu_audio.frame() -> "
            f"presentation.commit(): {list(zip(ordered, positions))}"
        )
    try:
        window_lo, window_hi = platform_hle_windows(inputs.config)
    except ValueError as exc:
        raise VerificationError(str(exc)) from exc
    if (
        window_lo[0] != "x4::vsync::kVSync"
        or window_hi[0] != "x4::vsync::kVSyncEntryEnd"
    ):
        raise VerificationError(
            "GameConfig does not admit only the full VSync entry"
        )
    if ".vsyncTrap = x4::vsync::kVSync" not in inputs.config:
        raise VerificationError(
            "GameConfig does not fail-fast the full VSync entry"
        )
    if inputs.frame.count("fieldService_(core)") != 1:
        raise VerificationError(
            "X4FrameDriver must service exactly one display field per step"
        )
    if "0x800E4DB0u" in inputs.frame or "kVSync" in inputs.frame:
        raise VerificationError(
            "X4FrameDriver still dispatches guest VSync instead of owning the boundary"
        )
    for retired in ("wait_for_counter", "register_(kWait", "kWaitEnd"):
        if retired in inputs.source or retired in inputs.header:
            raise VerificationError(
                f"retired successful VSync helper remains in shipping source: {retired}"
            )
    if "gpu_present(c)" in inputs.source or "gpu_pace_frame(c)" in inputs.source:
        raise VerificationError(
            "shipping wait helper bypasses or duplicates the authoritative presentation fence"
        )
    checks.append(
        "native field service and full-entry VSync trap match the measured contract"
    )
    checks.extend(verify_mode_contract(inputs))
    checks.extend(verify_wait_helper_budget(inputs))
    checks.extend(verify_register_cells(inputs))
    checks.extend(verify_mode_census(inputs))
    checks.extend(verify_shipping_owner(inputs))
    return checks


def load_inputs(exe_path: Path) -> Inputs:
    if not exe_path.is_file():
        raise VerificationError(f"missing executable: {exe_path}")
    return Inputs(
        exe_path.read_bytes(),
        SYNC_HEADER.read_text(),
        SYNC_SOURCE.read_text(),
        FRAME_SOURCE.read_text(),
        CONFIG_SOURCE.read_text(),
        MOVIE_HEADER.read_text() if MOVIE_HEADER.is_file() else "",
        {
            "game/core/x4_runtime.cpp": (ROOT / "game/core/x4_runtime.cpp").read_text(),
            "tests/test_x4_runtime.cpp": (ROOT / "tests/test_x4_runtime.cpp").read_text(),
        },
    )


def mutate_word(image: bytes, address: int, replacement: int) -> bytes:
    changed = bytearray(image)
    offset = TEXT_FILE_OFFSET + address - TEXT_VADDR
    struct.pack_into("<I", changed, offset, replacement)
    return bytes(changed)


def expect_refusal(name: str, inputs: Inputs) -> str:
    try:
        verify(inputs, check_digest=False)
    except VerificationError as exc:
        return f"PASS negative {name}: {exc}"
    raise VerificationError(f"negative {name} was accepted")


def selftest(inputs: Inputs) -> list[str]:
    results = [f"PASS positive retail: {len(verify(inputs))} contract groups"]
    wrong_edge = Inputs(
        mutate_word(inputs.exe, 0x800E5ADC, 0),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(expect_refusal("broken observed call edge", wrong_edge))
    wrong_bound = Inputs(
        mutate_word(inputs.exe, 0x800E5750, 0x2A220007),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(expect_refusal("seven callback slots", wrong_bound))
    wrong_config = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source,
        inputs.frame,
        # Anchored on the .windowHi initializer, not on the bare constant name: the constant also
        # appears in the static_assert above the table, and replacing THAT would leave the window
        # exactly as shipping while making the case look like it mutated something.
        inputs.config.replace(
            ".windowHi = {x4::vsync::kVSyncEntryEnd,", ".windowHi = {x4::vsync::kVSync,", 1
        ),
        inputs.movie,
    )
    results.append(expect_refusal("collapsed executable window", wrong_config))
    raw_present = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source.replace(
            "c->game->presentation.commit(c, 1)", "gpu_present(c)", 1
        ),
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(expect_refusal("raw present without frame fence", raw_present))
    hardcoded_boot_handler = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source.replace(
            "guest::call(c, vblankHandler)", "guest::call(c, kVblankHandler)", 1
        ),
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(
        expect_refusal("hardcoded boot handler drops live IRQ chain", hardcoded_boot_handler)
    )
    no_pad_service = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source.replace("c->game->pad.serviceFrame()", "", 1),
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(expect_refusal("missing pad field service", no_pad_service))
    no_spu_service = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source.replace("c->game->spu_audio.frame()", "", 1),
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(expect_refusal("missing SPU field service", no_spu_service))
    no_field_boundary = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source,
        inputs.frame.replace("fieldService_(core)", "", 1),
        inputs.config,
        inputs.movie,
    )
    results.append(expect_refusal("missing native field boundary", no_field_boundary))
    no_vsync_trap = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config.replace(".vsyncTrap = x4::vsync::kVSync", ".vsyncTrap = 0", 1),
        inputs.movie,
    )
    results.append(expect_refusal("missing full VSync trap", no_vsync_trap))
    # ── the entry owner, one negative per claim it makes ──────────────────────────────────────────
    # A verifier that only proves the positive case has not shown that its checks can fail, and the
    # claims below are the ones `x4::vsync::serveVSync` is built on.
    no_mode_query = Inputs(
        mutate_word(inputs.exe, MODE_QUERY_BRANCH, 0x04810000),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(expect_refusal("a mode dispatch that does not branch on the sign", no_mode_query))
    no_mode_one = Inputs(
        mutate_word(inputs.exe, MODE_ONE_COMPARE, 0x10820000),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(expect_refusal("a mode-1 arm that does not return early", no_mode_one))
    wrong_mode_zero_target = Inputs(
        mutate_word(inputs.exe, MODE_ZERO_BASE + 4, 0x8C42DC50),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(
        expect_refusal("a mode-0 wait that targets neither field counter", wrong_mode_zero_target)
    )
    no_second_wait = Inputs(
        mutate_word(inputs.exe, SECOND_WAIT_TARGET, 0x00000000),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(
        expect_refusal("a second wait that does not ask for the next field", no_second_wait)
    )
    spin_budget = Inputs(
        mutate_word(inputs.exe, WAIT_SPIN_SHIFT, 0x00000000),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(
        expect_refusal("a wait helper whose a1 is not a spin budget", spin_budget)
    )
    wrong_register_cell = Inputs(
        mutate_word(inputs.exe, RCNT1_CELL, 0x00000000),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(
        expect_refusal("a cell that does not name the HBlank root counter", wrong_register_cell)
    )
    extra_state_writer = Inputs(
        mutate_word(inputs.exe, LAST_SYNC_STORE + 0x40, 0xAC22CB90),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(
        expect_refusal("a second writer of the last-sync word", extra_state_writer)
    )
    extra_site = Inputs(
        # 0x8001CA60 is `addiu s0,zero,30` — a word no call site occupies — so this genuinely ADDS a
        # 43rd caller rather than moving an existing one, which is the shape of drift the census is for.
        mutate_word(inputs.exe, 0x8001CA60, 0x0C03936C),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(expect_refusal("a 43rd call site of the VSync entry", extra_site))
    wrong_site_mode = Inputs(
        mutate_word(inputs.exe, 0x8001CA5C, 0x24040003),
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(expect_refusal("a site that passes VSync(3) instead of VSync(2)", wrong_site_mode))
    owner_without_exit = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source.replace(
            "ExecutionExitReason::FrameBoundary", "ExecutionExitReason::BudgetExhausted", 1
        ),
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(
        expect_refusal("an owner whose field wait is not a frame boundary", owner_without_exit)
    )
    owner_without_refusal = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source.replace("inTaskFiber()", "true", 1),
        inputs.frame,
        inputs.config,
        inputs.movie,
    )
    results.append(
        expect_refusal("an owner that cannot tell a parkable caller from one it cannot park",
                       owner_without_refusal)
    )
    # A SECOND OWNER, two ways, because the alias header is gone and a second owner can now only come
    # back through a call site that reaches the entry by the old namespace or the old spelling. The
    # header's own absence is checked by the real read above, so mutating a call site is the only way
    # this verifier can still be shown to catch the regression it exists for.
    two_owners = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        inputs.movie,
        {**inputs.call_sites,
         "game/core/x4_runtime.cpp":
             inputs.call_sites["game/core/x4_runtime.cpp"].replace(
                 "vsync::registerOverrides", "movie::registerOverrides")},
    )
    results.append(expect_refusal("a second owner of the VSync entry", two_owners))
    resurrect_alias = Inputs(
        inputs.exe,
        inputs.header,
        inputs.source,
        inputs.frame,
        inputs.config,
        "namespace movie = vsync;\n",
        inputs.call_sites,
    )
    results.append(expect_refusal("the deleted alias header returning", resurrect_alias))
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify retail evidence and shipping wiring",
    )
    parser.add_argument(
        "--selftest", action="store_true", help="prove the verifier accepts and refuses"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.check and not args.selftest:
        raise VerificationError("choose --check and/or --selftest")
    inputs = load_inputs(args.exe)
    if args.check:
        checks = verify(inputs)
        for check in checks:
            print(f"PASS: {check}")
        print(
            f"PASS — {len(checks)} retail VBlank contract groups; SHA-1 {EXPECTED_SHA1}"
        )
    if args.selftest:
        results = selftest(inputs)
        print("\n".join(results))
        print(f"PASS — selftest {len(results)}/{len(results)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
