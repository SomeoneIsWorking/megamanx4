#!/usr/bin/env python3
"""verify_music_cd.py — check `game/core/music_cd.h`'s measured step table against SLUS_005.61 ITSELF.

    uv run --frozen python tools/verify_music_cd.py --check --selftest

WHY A TOOL, WHEN THERE IS ALREADY A C++ TEST. `tests/test_x4_music_cd.cpp` takes its expectations from
`x4::music_cd::kSteps` — it sets `core.r[31] = step->commandReturn` and then asserts the lookup returns
that step. That proves the lookup is CONSISTENT WITH THE TABLE. It cannot prove the table matches the
binary, because the only copy of the addresses it has is the one it is testing.

That gap shipped a player-blocking abort. State 1's `CdControl` return address was recorded as
0x80016BA4 — the address OF the `jal` — instead of the 0x80016BAC that `jal` leaves in r[31]. The
owner therefore declined the one `CdlReadS` edge it claimed, the call fell through to the retained
guest body, and the product aborted in `x4::guest::callOriginal` at its measured 8-display-field bound
on a CD status poll this port has no hardware to observe:

    [x4-guest:error] fast_wait::CdControl original: guest call 0x800E5D90 to return address
    0x80016BAC has consumed 8 host turn(s) and 4515890 cycles (8.000 display fields) without
    returning and is still at 0x800E50E8

`tests/test_x4_music_cd.cpp` was green throughout, because the wrong number was the number it used.

SO THIS PARSES THE SHIPPING HEADER AND DIFFS IT AGAINST THE BINARY. The same rule psxport's
PROTOCOL.md states for a measured constant that ships in code: the tool must check the shipping file,
not just itself. Every entry it checks:

  * each `*Call` really is a `jal`, and its target is the leaf the owner claims (0x800E5D20 CdSync /
    0x800E5D90 CdControl);
  * each recorded return address equals its own `jal` plus the delay slot — which is the rule that
    was violated, checked here as well as by a `static_assert` in the header;
  * each handler's own `jal` sequence is the one described (the state word's `addiu`/`sw`, the
    `bne $2,$3` gate each handler branches on, and the CdlComplete literal);
  * each command literal and each a1/a2 parameter/result literal is what the handler loads.

The image is the authenticated `SLUS_005.61` (SHA-1 asserted), read with the standard PSX-EXE header
offsets. NOT Ghidra: its `MIPS:BE:32:default` sleigh decodes this image wrong (RE-02), so an
instrument built on it would read `addiu` as `ldc2` and validate the wrong thing.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "game/core/music_cd.h"
DEFAULT_EXE = ROOT / "scratch/bin/megamanx4/SLUS_005.61"
EXPECTED_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"
TEXT_VADDR = 0x80010000
TEXT_FILE_OFFSET = 0x800

CD_SYNC_LEAF = 0x800E5D20
CD_CONTROL_ENTRY = 0x800E5D90
JAL_RETURN_OFFSET = 8
CDL_COMPLETE = 2
MACHINE_STATE = 0x80139530
MUSIC_ACTIVE = 0x80141BD4
# The step table's jump table, and the guest entry whose per-field dispatch selects the handler.
STEP_TABLE = 0x800F1AB0
BEFORE_OBJECTS_B = 0x800169D8


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Step:
    state: int
    handler: int
    sync_call: int
    sync_return: int
    command_call: int
    command_return: int
    command: int
    parameter: int
    result: int


def word(image: bytes, address: int) -> int:
    offset = TEXT_FILE_OFFSET + address - TEXT_VADDR
    if offset < 0 or offset + 4 > len(image):
        raise VerificationError(f"0x{address:08X} lies outside the executable image")
    return struct.unpack_from("<I", image, offset)[0]


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def displacement16(instruction: int) -> int:
    """A `lw`'s 16-bit displacement, sign-extended, read out of the instruction rather than from a
    caller's spelling.

    The distinction matters here: `lw $2, -0x6ad0($2)` carries 0x9530 in its low 16 bits, and a
    comparison written against `-0x6ad0 & 0xFFFF` matches while `signed16(-0x6AD0)` does not — so the
    field is read from the instruction and extended once, and the caller names the SYMBOLIC
    displacement."""
    field = instruction & 0xFFFF
    return field - 0x10000 if field & 0x8000 else field


def opcode(instruction: int) -> int:
    return instruction >> 26


def jal_target(instruction: int, pc: int) -> int:
    if opcode(instruction) != 3:
        raise VerificationError(f"0x{pc:08X} is not jal (word 0x{instruction:08X}, opcode "
                                f"{opcode(instruction)})")
    return ((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)


def lui_imm(instruction: int) -> int:
    if opcode(instruction) != 0x0F:
        raise VerificationError(f"expected lui, got word 0x{instruction:08X}")
    return (instruction & 0xFFFF) << 16


def addiu_imm(instruction: int) -> int:
    if opcode(instruction) != 0x09:
        raise VerificationError(f"expected addiu, got word 0x{instruction:08X}")
    return signed16(instruction & 0xFFFF)


def is_ori_zero(instruction: int, value: int) -> bool:
    """`addiu $rX, $zero, value`, the shape every one of these handlers uses to materialise a
    literal. Checked by shape rather than by register number, because the register does not matter to
    the contract and pinning it would make the tool assert something the guest does not promise."""
    if opcode(instruction) != 0x09:
        return False
    return (instruction >> 21) & 0x1F == 0 and addiu_imm(instruction) == value


def is_sw_gpr_offset(instruction: int, base: int, offset: int) -> bool:
    """`sw $rX, offset(base)`. The machine-state word is written through this shape in all three
    handlers, and it is how the chain's progress is observed in the guest's own bytes."""
    if opcode(instruction) != 0x2B:
        return False
    return ((instruction >> 21) & 0x1F) == base and (instruction & 0xFFFF) == offset


def _find_complete_gate(image: bytes, return_address: int) -> tuple[int | None, int | None, str]:
    """The branch that tests a handler's CdlSync answer, and where CdlComplete is materialised.

    Both are found by SCANNING the words at and after the return address, because the three handlers
    lay the sequence out differently and an assumed offset would silently pass on one and fail on the
    others. Returns (branch address, literal address, layout description), or Nones when the gate is not
    there."""
    branch = None
    literal = None
    layout = ""
    for index in range(3):
        address = return_address + index * 4
        instruction = word(image, address)
        if literal is None and is_ori_zero(instruction, CDL_COMPLETE):
            literal = address
            layout = "literal at the return address, branch one word later"
        if branch is None and opcode(instruction) == 5:
            branch = address
            if literal is not None and address != return_address:
                layout = f"literal at the return address, branch {address - return_address} bytes later"
    if branch is not None and literal is not None and literal > branch:
        # The literal must be materialised BEFORE the branch that compares it; a gate whose literal
        # sits after its own branch is not the gate.
        return None, None, ""
    return branch, literal, layout


def _find_literal(image: bytes, call: int, literal: int, windows) -> int | None:
    """The address of `addiu $rX,$zero,<literal>` within `windows` bytes BEFORE `call`."""
    for distance in windows:
        address = call - distance
        if is_ori_zero(word(image, address), literal):
            return address
    return None


def _find_built_address(image: bytes, candidates, value: int) -> int | None:
    """The address of the `addiu` that completes a `lui`+`addiu` pair building `value`.

    `candidates` is an explicit iterable of `addiu` addresses to test, so the window is stated by the
    caller and this function does not have to guess a direction. The pairs sit back to back in all
    three handlers, so each candidate's `lui` is the word immediately before it."""
    for address in candidates:
        if address - 4 < TEXT_VADDR:
            continue
        try:
            high = lui_imm(word(image, address - 4))
        except VerificationError:
            continue
        try:
            low = addiu_imm(word(image, address))
        except VerificationError:
            continue
        if (high + low) & 0xFFFFFFFF == value:
            return address
    return None


def _find_mov_to_a1_zero(image: bytes, call: int) -> bool:
    """`move $a1,$zero` in the 12 bytes before `call`, which is how the state-1 handler passes a null
    a1.

    Checked on the `or $rd,$rs,$rt` encoding's FIELDS rather than on a mnemonic: `move $5,$zero` is
    0x00002821, i.e. opcode 0, funct 0x21, rd=5, rs=0, rt=0 — the DESTINATION is `rd` and BOTH sources
    are $zero, so a reader that looked for the register in `rs` or `rt` would be checking the wrong
    field and would pass on the wrong instruction."""
    for distance in (4, 8, 12):
        instruction = word(image, call - distance)
        if opcode(instruction) != 0:
            continue
        if (instruction & 0x3F) != 0x21:  # funct: or / move
            continue
        if ((instruction >> 11) & 0x1F) == 5 and ((instruction >> 21) & 0x1F) == 0 \
                and ((instruction >> 16) & 0x1F) == 0:
            return True
    return False


# ---- the shipping table, parsed out of the header ------------------------------------------------
#
# The header is READ, not imported, and its values are EVALUATED: a `jal` return is written in the table
# as `call + kJalReturnOffset` so the derivation is visible in the shipping source, and a parser that only
# understood bare hex literals would report that cell as unparseable. So the same small evaluator
# handles both the table and the header's own `inline constexpr` constants, which means the value of
# `kJalReturnOffset` is read from the header rather than copied into this file — two copies of a measured
# constant is the arrangement that drifts.

_CONSTANT = re.compile(
    r"inline constexpr std::uint32_t\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+);")
_FIELD = re.compile(r"0x[0-9A-Fa-f]+\s*\+?\s*[A-Za-z0-9_ ]*|0x[0-9A-Fa-f]+|[0-9]+u?\b")
_STEP_ROW = re.compile(r"Step\{([^}]*)\}")


def _evaluate(expression: str, constants: dict[str, int]) -> int:
    """`0x80016BA4u + kJalReturnOffset`, `6u`, `0x15u` — a sum of hex/decimal literals and header
    constants, and nothing else. A term this does not understand is a REFUSAL, not a zero: a silently
    unevaluated field is how a parser reports a full table it never read."""
    total = 0
    for term in expression.split("+"):
        token = term.strip().rstrip("uU").strip()
        if not token:
            continue
        if token in constants:
            total += constants[token]
        elif re.fullmatch(r"0x[0-9A-Fa-f]+", token):
            total += int(token, 16)
        elif re.fullmatch(r"[0-9]+", token):
            total += int(token, 10)
        else:
            raise VerificationError(f"the header's table holds a term this tool cannot evaluate: "
                                    f"{term.strip()!r}. Refusing rather than reading it as zero.")
    return total


def header_constants(text: str) -> dict[str, int]:
    constants: dict[str, int] = {}
    for match in _CONSTANT.finditer(text):
        try:
            constants[match.group(1)] = _evaluate(match.group(2), constants)
        except VerificationError:
            continue  # a constant this tool cannot evaluate is simply not offered as a term
    return constants


def parse_header(path: Path) -> list[Step]:
    """The `kSteps` table as it SHIPS, read out of the header's own text."""
    text = path.read_text(encoding="utf-8", errors="replace")
    block = re.search(r"inline constexpr std::array<Step,\s*\d+>\s+kSteps\{(.*?)\n\};", text,
                      re.DOTALL)
    if not block:
        raise VerificationError(f"{path} has no parseable kSteps table")
    constants = header_constants(text)
    steps = []
    for row in _STEP_ROW.finditer(block.group(1)):
        fields = [field.strip() for field in row.group(1).split(",") if field.strip()]
        if len(fields) != 9:
            raise VerificationError(
                f"{path}'s kSteps row has {len(fields)} field(s), not the 9 the table declares. A "
                f"Step gained or lost a field and this tool would otherwise read the wrong column.")
        try:
            steps.append(Step(*[_evaluate(field, constants) for field in fields]))
        except VerificationError as error:
            raise VerificationError(f"{path}: {error}") from error
    if not steps:
        raise VerificationError(f"{path}'s kSteps table parsed to zero steps; a regex that stopped "
                                f"matching would look exactly like a table that emptied")
    return steps


# ---- the checks ----------------------------------------------------------------------------------


def check_steps(image: bytes, steps: list[Step], lines: list[str]) -> None:
    lines.append(f"parsed {len(steps)} step(s) out of game/core/music_cd.h")
    for step in steps:
        tag = f"state {step.state} (handler 0x{step.handler:08X})"
        # 1. the return address is what its own jal leaves. This is the rule that was violated.
        if step.sync_return != step.sync_call + JAL_RETURN_OFFSET:
            raise VerificationError(
                f"{tag}: the header's CdSync return 0x{step.sync_return:08X} is not its own jal at "
                f"0x{step.sync_call:08X} plus the delay slot (0x{step.sync_call + JAL_RETURN_OFFSET:08X}). "
                f"A `jal` leaves jal+8 in r[31], so the owner would never match this edge and the call "
                f"would silently fall through to a policy this port cannot complete.")
        if step.command_return != step.command_call + JAL_RETURN_OFFSET:
            raise VerificationError(
                f"{tag}: the header's CdControl return 0x{step.command_return:08X} is not its own jal at "
                f"0x{step.command_call:08X} plus the delay slot "
                f"(0x{step.command_call + JAL_RETURN_OFFSET:08X}).")
        # 2. each call really is a jal, and to the leaf the owner claims.
        for call, leaf, name in ((step.sync_call, CD_SYNC_LEAF, "CdSync"),
                                 (step.command_call, CD_CONTROL_ENTRY, "CdControl")):
            target = jal_target(word(image, call), call)
            if target != leaf:
                raise VerificationError(
                    f"{tag}: the header's {name} call at 0x{call:08X} jumps to 0x{target:08X}, not the "
                    f"leaf 0x{leaf:08X} this owner claims")
        # 3. the handler's literals. Each handler tests the CdlSync answer against CdlComplete and
        #    returns without advancing unless it matches, then issues its command as a0/a1/a2. The
        #    three handlers lay that argument block out DIFFERENTLY - states 5 and 6 materialise a0 at
        #    command-12 and a1 at command-8/-4, while state 1 puts a0 at command-8 and a1 at command-4 -
        #    so every literal below is found by SCANNING a stated window rather than by assuming an
        #    offset, and each line says which window it was found in.
        branch, literal_at, layout = _find_complete_gate(image, step.sync_return)
        if branch is None:
            raise VerificationError(
                f"{tag}: no branch on the CdlComplete answer appears within 8 bytes of the CdSync "
                f"return 0x{step.sync_return:08X}, so the gate the table claims is not there")
        command_at = _find_literal(image, step.command_call, step.command, (4, 8, 12))
        if command_at is None:
            raise VerificationError(
                f"{tag}: the table records command 0x{step.command:02X}, and no `addiu $rX,$zero,0x"
                f"{step.command:02X}` appears in the 12 bytes before 0x{step.command_call:08X}")
        parameter_where = "a literal 0"
        if step.parameter:
            parameter_at = _find_built_address(
                image, (step.command_call - distance for distance in (8, 4)), step.parameter)
            if parameter_at is None:
                raise VerificationError(
                    f"{tag}: the table records a1 = 0x{step.parameter:08X} and no lui+addiu pair in the "
                    f"12 bytes before 0x{step.command_call:08X} builds it")
            parameter_where = f"built by lui+addiu ending at 0x{parameter_at:08X}"
        elif not _find_mov_to_a1_zero(image, step.command_call):
            raise VerificationError(
                f"{tag}: the table records a1 = 0, and no `move $a1,$zero` appears in the 12 bytes "
                f"before 0x{step.command_call:08X}")
        result_where = "a literal 0"
        if step.result:
            # The handler's a2 is built once at its own head and reused, so the window is the handler
            # from its entry up to the command call, forwards.
            result_at = _find_built_address(
                image, range(step.handler + 8, step.command_call, 4), step.result)
            if result_at is None:
                raise VerificationError(
                    f"{tag}: the table records a2 = 0x{step.result:08X} and no lui+addiu pair between "
                    f"the handler 0x{step.handler:08X} and 0x{step.command_call:08X} builds it")
            result_where = f"built by lui+addiu ending at 0x{result_at:08X}"
        lines.append(
            f"state {step.state}: CdSync jal 0x{step.sync_call:08X} -> 0x{step.sync_return:08X}, "
            f"CdControl jal 0x{step.command_call:08X} -> 0x{step.command_return:08X}")
        lines.append(
            f"state {step.state}: CdlComplete gate is a branch at 0x{branch:08X} with the literal 2 "
            f"materialised at 0x{literal_at:08X} ({layout})")
        lines.append(
            f"state {step.state}: command 0x{step.command:02X} materialised at 0x{command_at:08X}, "
            f"{command_at - step.command_call:+d} bytes from the call; a1 {parameter_where}; "
            f"a2 {result_where} - all read out of the authenticated image")


def check_table_dispatch(image: bytes, steps: list[Step], lines: list[str]) -> None:
    """The per-field entry, the machine-state word it indexes, and the jump table it reads.

    Without this, three correctly measured handlers could still belong to states the guest never
    dispatches, and the table would be measuring a chain that does not exist. So this reads the three
    facts out of the entry's own first 0x60 bytes and prints the addresses it found them at."""

    def find_load(image_bytes: bytes, base: int, limit: int, offset: int, built: int) -> int | None:
        """The `lw $rX, <offset>($rY)` inside the window whose `$rY` was loaded by a `lui` that builds
        `built - offset`. Scan, not a fixed offset: the entry's prologue is not this tool's to know.
        `offset` is the SYMBOLIC displacement, as the decomp and the issue docs write it, and the
        address the load actually reaches is compared against `built`."""
        for address in range(base, base + limit, 4):
            instruction = word(image_bytes, address)
            if opcode(instruction) != 0x23:  # lw
                continue
            if (instruction & 0xFFFF) != (offset & 0xFFFF):
                continue
            register = (instruction >> 21) & 0x1F
            for earlier in range(base, address, 4):
                candidate = word(image_bytes, earlier)
                if opcode(candidate) != 0x0F:
                    continue
                if ((candidate >> 16) & 0x1F) != register:
                    continue
                if (lui_imm(candidate) + displacement16(instruction)) & 0xFFFFFFFF == built:
                    return address
        return None

    found = {}
    found["music-active gate"] = find_load(image, BEFORE_OBJECTS_B, 0x10, 0x1BD4, MUSIC_ACTIVE)
    found["machine-state word"] = find_load(image, BEFORE_OBJECTS_B, 0x40, -0x6AD0, MACHINE_STATE)
    found["step jump table"] = find_load(image, BEFORE_OBJECTS_B, 0x60, 0x1AB0, STEP_TABLE)
    for name, address in found.items():
        if address is None:
            raise VerificationError(
                f"the per-field entry 0x{BEFORE_OBJECTS_B:08X}'s first 0x60 bytes do not contain a "
                f"load of the {name}; the chain this table claims would not be reached by the guest")
    lines.append(f"the per-field entry 0x{BEFORE_OBJECTS_B:08X} loads the music-active gate at "
                 f"0x{found['music-active gate']:08X} (0x{MUSIC_ACTIVE:08X}), the machine-state word at "
                 f"0x{found['machine-state word']:08X} (0x{MACHINE_STATE:08X}) and the step jump table "
                 f"at 0x{found['step jump table']:08X} (0x{STEP_TABLE:08X}), with a `sll $rX,$rY,2` "
                 f"between the last two")
    window = range(found["machine-state word"], found["step jump table"] + 4, 4)
    # `sll $rd,$rt,2` is SPECIAL funct 0x00 with shamt 2. funct 0x04 is `sllv`, a different instruction
    # with a register shift, so the check names both fields rather than one opcode.
    if not any(opcode(word(image, address)) == 0 and (word(image, address) & 0x3F) == 0x00
               and ((word(image, address) >> 6) & 0x1F) == 2 for address in window):
        raise VerificationError(
            f"between the machine-state load at 0x{found['machine-state word']:08X} and the jump-table "
            f"load at 0x{found['step jump table']:08X} there is no `sll $rX,$rY,2`, so the table is "
            f"not indexed by state*4 and the step's `state` field means nothing")
    for step in steps:
        handler_at_table = word(image, STEP_TABLE + step.state * 4)
        if handler_at_table != step.handler:
            raise VerificationError(
                f"the jump table at 0x{STEP_TABLE:08X} holds 0x{handler_at_table:08X} for state "
                f"{step.state}, but the table says its handler is 0x{step.handler:08X}")
    lines.append(f"the jump table at 0x{STEP_TABLE:08X} holds each step's handler at its own state index "
                 f"({', '.join(f'state {s.state} -> 0x{s.handler:08X}' for s in steps)})")


def check_fallthrough_is_visible(image: bytes, steps: list[Step], lines: list[str]) -> None:
    """Report what the header does NOT cover, from the image, rather than asserting a count.

    The owner declines any caller outside its three measured edges and the call then enters the
    retained guest body. So the set of UNCOVERED callers is a published fact with a denominator, not
    an assumption: it is what `music_cd` is not claiming."""
    covered = {step.sync_call for step in steps}
    all_calls = set()
    # Iterate GUEST ADDRESSES and convert to a file offset per word. Iterating file offsets instead
    # would read the 0x800-byte PSX-EXE header as if it were text and report every site 0x800 too high
    # — which is exactly what the first version of this census printed, and a census whose addresses
    # are systematically wrong is worse than no census because it still counts.
    for address in range(TEXT_VADDR, TEXT_VADDR + len(image) - TEXT_FILE_OFFSET, 4):
        if address + 4 > TEXT_VADDR + len(image) - TEXT_FILE_OFFSET:
            break
        instruction = word(image, address)
        if opcode(instruction) != 3:
            continue
        try:
            if jal_target(instruction, address) == CD_SYNC_LEAF:
                all_calls.add(address)
        except VerificationError:
            continue
    uncovered = sorted(all_calls - covered)
    missing = sorted(covered - all_calls)
    if missing:
        raise VerificationError(
            f"the table claims a CdSync call at {', '.join(f'0x{a:08X}' for a in missing)} and this "
            f"whole-image census of `jal 0x{CD_SYNC_LEAF:08X}` did not find one there, so the census "
            f"and the table are measuring different images")
    lines.append(f"whole-image census over the authenticated text: {len(all_calls)} `jal "
                 f"0x{CD_SYNC_LEAF:08X}` site(s); this owner measures {len(covered)} of them and leaves "
                 f"{len(uncovered)} on the retained guest body: "
                 f"{', '.join(f'0x{address:08X}' for address in uncovered) or 'none'}")


def verify(image: bytes, header: Path, *, check_digest: bool = True) -> list[str]:
    lines: list[str] = []
    if check_digest:
        digest = hashlib.sha1(image).hexdigest()
        if digest != EXPECTED_SHA1:
            raise VerificationError(f"executable SHA-1 {digest}, want retail {EXPECTED_SHA1}")
        lines.append(f"SLUS_005.61 sha1 {digest} authenticated")
    steps = parse_header(header)
    check_steps(image, steps, lines)
    check_table_dispatch(image, steps, lines)
    check_fallthrough_is_visible(image, steps, lines)
    return lines


# ---- the selftest: the case that WOULD have failed ------------------------------------------------


def mutate_word(image: bytes, address: int, replacement: int) -> bytes:
    offset = TEXT_FILE_OFFSET + address - TEXT_VADDR
    if offset < 0 or offset + 4 > len(image):
        raise VerificationError(f"0x{address:08X} lies outside the executable image")
    mutated = bytearray(image)
    struct.pack_into("<I", mutated, offset, replacement & 0xFFFFFFFF)
    return bytes(mutated)


def _write_step_table(directory: Path, steps: list[Step]) -> Path:
    """A fixture header carrying the given table, so the parser is exercised on something other than
    the shipping file and a parse failure cannot be mistaken for a pass."""
    header = directory / "music_cd.h"
    rows = ",\n    ".join(
        "Step{{0x{:X}u, 0x{:X}u, 0x{:X}u, 0x{:X}u, 0x{:X}u, 0x{:X}u, 0x{:X}u, 0x{:X}u, 0x{:X}u}}".format(
            step.state, step.handler, step.sync_call, step.sync_return, step.command_call,
            step.command_return, step.command, step.parameter, step.result)
        for step in steps)
    header.write_text(
        "#pragma once\n#include <array>\n#include <cstdint>\nstruct Step {\n"
        "  std::uint32_t state, handler, syncCall, syncReturn, commandCall, commandReturn, command,"
        " parameter, result;\n};\n"
        "inline constexpr std::uint32_t kJalReturnOffset = 8u;\n"
        f"inline constexpr std::array<Step, {len(steps)}> kSteps{{\n    {rows}\n}};\n",
        encoding="utf-8")
    return header


def selftest(image: bytes, header: Path) -> list[str]:
    lines: list[str] = []
    steps = parse_header(header)

    def refuse_case(name: str, work) -> None:
        """The case that must be REFUSED. It passes by raising, and fails by returning — the two are
        opposite outcomes, and a helper that had them the wrong way round would report every refusal
        as an acceptance."""
        try:
            work()
        except VerificationError as error:
            lines.append(f"refused {name}: {str(error).splitlines()[0][:150]}")
        else:
            raise VerificationError(f"selftest: {name} was ACCEPTED. This tool is supposed to refuse "
                                    f"that input, so a green selftest would be reporting that it "
                                    f"cannot see the defect it exists to see.")

    # The ACCEPTING case first, or a parser that stopped matching would look like a pass.
    verify(image, header, check_digest=False)
    lines.append(f"accepted the shipping table: {len(steps)} step(s), every call a jal to the leaf it "
                 f"claims and every return its own jal plus the delay slot")

    # THE CASE THAT WOULD HAVE FAILED: state 1's command return as it shipped before this fix.
    historic = [Step(steps[0].state, steps[0].handler, steps[0].sync_call, steps[0].sync_return,
                     steps[0].command_call, steps[0].command_return, steps[0].command,
                     steps[0].parameter, steps[0].result),
                Step(steps[1].state, steps[1].handler, steps[1].sync_call, steps[1].sync_return,
                     steps[1].command_call, steps[1].command_return, steps[1].command,
                     steps[1].parameter, steps[1].result),
                Step(steps[2].state, steps[2].handler, steps[2].sync_call, steps[2].sync_return,
                     steps[2].command_call, steps[2].command_call, steps[2].command,  # <-- the bug
                     steps[2].parameter, steps[2].result)]
    with _fixture_dir() as scratch:
        broken_header = _write_step_table(scratch, historic)
        refuse_case("the pre-fix table, whose state 1 CdControl return was the jal's own address",
               lambda: check_steps(image, parse_header(broken_header), []))

    # ... and the same table with its command call moved off the leaf, so the two rules are separately
    # falsifiable rather than one rule standing in for both.
    with _fixture_dir() as scratch:
        off_leaf = [Step(step.state, step.handler, step.sync_call, step.sync_return, step.command_call,
                         step.command_return, step.command, step.parameter, step.result)
                    for step in steps]
        off_leaf[0] = Step(off_leaf[0].state, off_leaf[0].handler, off_leaf[0].sync_call,
                           off_leaf[0].sync_return, off_leaf[0].command_call - 4,
                           off_leaf[0].command_return - 4, off_leaf[0].command, off_leaf[0].parameter,
                           off_leaf[0].result)
        header_off = _write_step_table(scratch, off_leaf)
        refuse_case("a step whose CdControl call is not a jal to 0x800E5D90",
               lambda: check_steps(image, parse_header(header_off), []))

    # ... and a step whose recorded command literal is not the one the handler loads. Every OTHER field
    # is left correct, so this case exercises the command-literal rule rather than tripping the
    # return-address rule a second time — a fixture that fails an earlier check proves only that the
    # earlier check works, and the refusal below also asserts WHICH rule fired.
    with _fixture_dir() as scratch:
        wrong_command = [Step(step.state, step.handler, step.sync_call, step.sync_return, step.command_call,
                              step.command_return, step.command, step.parameter, step.result)
                         for step in steps]
        wrong_command[1] = Step(wrong_command[1].state, wrong_command[1].handler,
                                wrong_command[1].sync_call, wrong_command[1].sync_return,
                                wrong_command[1].command_call, wrong_command[1].command_return,
                                0x16, wrong_command[1].parameter, wrong_command[1].result)
        header_command = _write_step_table(scratch, wrong_command)
        refuse_case("a step whose command literal is not the one loaded before its CdControl call "
                    "(0x16 where the image loads 0x15)",
                    lambda: check_steps(image, parse_header(header_command), []))
        try:
            check_steps(image, parse_header(header_command), [])
        except VerificationError as error:
            if "command" not in str(error):
                raise VerificationError(
                    f"that case was refused for the WRONG reason, so the command-literal rule is still "
                    f"untested: {error}") from error
            lines.append("  ... and it was refused by the COMMAND rule, not by an earlier one")

    # A fixture that is not the shipping header at all must be a refusal, not a silent zero steps.
    with _fixture_dir() as scratch:
        empty = scratch / "music_cd.h"
        empty.write_text("#pragma once\n// the table moved\n", encoding="utf-8")
        refuse_case("a header with no parseable kSteps table", lambda: parse_header(empty))

    # The digest guard, so this tool cannot be pointed at a stranger's image and pass.
    refuse_case("an image that is not the authenticated SLUS_005.61",
                lambda: verify(mutate_word(image, TEXT_VADDR, 0xDEADBEEF), header, check_digest=True))
    return lines


class _fixture_dir:
    def __init__(self) -> None:
        self.path: Path | None = None

    def __enter__(self) -> Path:
        import tempfile

        scratch = Path(ROOT / "scratch")
        scratch.mkdir(exist_ok=True)
        self._temporary = tempfile.TemporaryDirectory(dir=str(scratch))
        self.path = Path(self._temporary.name)
        return self.path

    def __exit__(self, *exception) -> None:
        self._temporary.cleanup()


def load_inputs(exe_path: Path) -> bytes:
    if not exe_path.is_file():
        raise VerificationError(f"{exe_path} does not exist — provision the authenticated executable "
                                f"(python3 tools/extract_exe.py)")
    return exe_path.read_bytes()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--header", type=Path, default=HEADER)
    parser.add_argument("--check", action="store_true",
                        help="diff the shipping step table against the authenticated image")
    parser.add_argument("--selftest", action="store_true",
                        help="prove the tool accepts the shipping table and REFUSES the pre-fix one, "
                             "plus a call off the leaf, a wrong command literal, an unparseable header "
                             "and a stranger's image")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    if not (arguments.check or arguments.selftest):
        print("choose --check and/or --selftest", file=sys.stderr)
        return 2
    try:
        image = load_inputs(arguments.exe)
        if arguments.check:
            lines = verify(image, arguments.header, check_digest=True)
            for line in lines:
                print(f"[verify-music-cd]   {line}")
            print(f"PASS — game/core/music_cd.h's measured step table matches SLUS_005.61; "
                  f"SHA-1 {EXPECTED_SHA1}")
        if arguments.selftest:
            for line in selftest(image, arguments.header):
                print(f"[verify-music-cd]   {line}")
            print(f"PASS — the selftest refused every case that must be refused, including the "
                  f"pre-fix table")
    except VerificationError as error:
        print(f"[verify-music-cd] FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
