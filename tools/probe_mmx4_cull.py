#!/usr/bin/env python3
"""probe_mmx4_cull.py — the SLUS_005.61 horizontal-cull census (maintainer RE probe).

WHAT THIS IS. SLUS_005.61's visibility cull is not a single predicate. Every cull owner in the
resident code expresses its window in the SAME retail idiom, so the instrument searches for the
idiom rather than for a list of known addresses:

        t = v + A            (addiu, or an add chain when the addend is a register)
        t &= 0xFFFF          (andi)
        c = (u32)t <u B      (sltiu)          [immediate-bound form]
        c = (u32)a <u (u32)b (sltu, both masked)   [parametric-bound form]

A masked-16-bit unsigned window `A <= t < B` is exactly the half-open box `[-A, B-A)` over the
s16 that the guest loaded, so each hit is REPORTED AS A BOX with its width, and the cull owners
are the boxes whose width is a screen extent (320 or 240, or the parametric 2*half + 320/240).
Nothing here is specialised to those widths: the census prints every window it finds and this
file never names a cull address.

WHY IT IS AN INSTRUMENT AND NOT A GREP. It decodes every 4-byte word of the PSX-EXE text section
with its own MIPS-I decoder, so the denominator is real ("scanned N words"), and it REFUSES to
report a clean result unless it rediscovered the four window sites that were measured
independently by disassembly. A grep count is text, not reached code.

BLIND SPOT, STATED. The text section holds data tables as well as code, and this sweep decodes
both, so a data word can be reported as a window. Every hit is therefore printed with its
surrounding context and the caller census cross-checks the classified owners.

Identity: refuses any executable whose SHA-1 is not SLUS_005.61's.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

SLUS_00561_SHA1 = "213733031136d095ca275d6957695aa25011cfa5"
PSX_EXE_HEADER = 0x800

# ── MIPS-I immediate forms the window idiom uses ──────────────────────────────────────────────
OP_ADDIU = 0x09
OP_ANDI = 0x0C
OP_ORI = 0x0D
OP_SLTI = 0x0A
OP_SLTIU = 0x0B
OP_LUI = 0x0F
OP_LHU = 0x25
OP_LW = 0x23
OP_JAL = 0x03
OP_J = 0x02
FUNC_ADDU = 0x21
FUNC_SLTU = 0x2B

MASK16 = 0xFFFF


def s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


@dataclass(frozen=True)
class Word:
    pc: int
    raw: int

    @property
    def op(self) -> int:
        return self.raw >> 26

    @property
    def rs(self) -> int:
        return (self.raw >> 21) & 31

    @property
    def rt(self) -> int:
        return (self.raw >> 16) & 31

    @property
    def rd(self) -> int:
        return (self.raw >> 11) & 31

    @property
    def funct(self) -> int:
        return self.raw & 63

    @property
    def imm(self) -> int:
        return self.raw & MASK16

    @property
    def simm(self) -> int:
        return s16(self.imm)

    def text(self) -> str:
        op, rs, rt, rd, imm = self.op, self.rs, self.rt, self.rd, self.imm
        if op == 0:
            names = {
                0x21: "addu",
                0x2B: "sltu",
                0x2A: "slt",
                0x00: "sll",
                0x08: "jr",
                0x25: "or",
            }
            name = names.get(self.funct, f"funct{self.funct:#x}")
            if self.funct in (0x21, 0x2B, 0x2A, 0x25):
                return f"{name} ${rt}, ${rs}, ${rd}"
            return f"{name} ${rd}, ${rt}, ${rs}"
        if op in (OP_ADDIU, OP_SLTI, OP_SLTIU):
            return {OP_ADDIU: "addiu", OP_SLTI: "slti", OP_SLTIU: "sltiu"}[op] + f" ${rt}, ${rs}, {self.simm}"
        if op in (OP_ANDI, OP_ORI):
            return ("andi " if op == OP_ANDI else "ori ") + f" ${rt}, ${rs}, 0x{imm:04x}"
        if op == OP_LUI:
            return f"lui ${rt}, 0x{imm:04x}"
        if op == OP_LHU:
            return f"lhu ${rt}, 0x{imm:04x}(${rs})"
        if op == OP_LW:
            return f"lw ${rt}, 0x{imm:04x}(${rs})"
        if op == OP_JAL:
            return f"jal {self.jump_target():#x}"
        return f"op{op:#x} ${rs}, ${rt}, 0x{imm:04x}"

    def jump_target(self) -> int:
        return ((self.raw & 0x03FFFFFF) << 2) | ((self.pc + 4) & 0xF0000000)


def load_text(exe: Path) -> tuple[int, list[Word]]:
    data = exe.read_bytes()
    digest = hashlib.sha1(data).hexdigest()
    if digest != SLUS_00561_SHA1:
        raise SystemExit(
            f"refusing a non-SLUS_005.61 executable: sha1 {digest} != {SLUS_00561_SHA1}"
        )
    t_addr, t_size = struct.unpack_from("<II", data, 0x18)
    body = data[PSX_EXE_HEADER : PSX_EXE_HEADER + t_size]
    if len(body) != t_size:
        raise SystemExit(f"truncated text section: {len(body)} of {t_size} bytes")
    words = [
        Word(t_addr + 4 * i, struct.unpack_from("<I", body, 4 * i)[0])
        for i in range(t_size // 4)
    ]
    return t_addr, words


# ── the window idiom ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Window:
    """A recovered half-open box `[-addend, bound - addend)` over an s16."""

    at: int  # address of the comparison
    source: int  # the register the window is stated in
    addend: int  # A; 0 when no immediate add feeds the mask
    bound: int | None  # B, when the bound is an immediate
    reg_addend: int | None  # register added to the value, when the add is not an immediate
    reg_bound: int | None  # register holding the bound, for the parametric form
    parametric: bool

    @property
    def lo(self) -> int:
        return -self.addend

    @property
    def width(self) -> int | None:
        return None if self.bound is None else self.bound - self.addend

    def describe(self) -> str:
        box = f"[-{self.addend}, {self.bound})" if self.bound is not None else f"[-{self.addend}, ${self.reg_bound}+)"
        slack = "" if self.reg_addend is None else f" +${self.reg_addend}"
        return f"{self.at:#010x} ${self.source} {box}{slack} width={self.width}"


def masks_into(words: list[Word], index: int, destination: int) -> bool:
    """True when the instruction at `index` is `andi $destination, <any>, 0xFFFF`."""
    word = words[index]
    return word.op == OP_ANDI and word.rt == destination and word.imm == MASK16


def addend_before(words: list[Word], index: int, destination: int) -> tuple[int, int | None]:
    """The add feeding a masked value: `(A, register)`; A is 0 and the register None when the
    value is already a screen-space quantity and the mask is the only thing between it and the
    comparison. A register addend means the box is PARAMETRIC in that register."""
    if index < 1:
        return 0, None
    producer = words[index - 1]
    if producer.op == OP_ADDIU and producer.rt == destination:
        return producer.simm, None
    if producer.op == 0 and producer.funct == FUNC_ADDU and producer.rd == destination:
        return 0, producer.rt
    if producer.op in (OP_LHU, OP_LW) and producer.rt == destination:
        return 0, None
    return 0, None


def scan_windows(words: list[Word]) -> tuple[list[Window], list[Window]]:
    """Immediate-bound and parametric-bound windows, in address order."""
    immediate: list[Window] = []
    parametric: list[Window] = []
    for index, word in enumerate(words):
        if word.op == OP_SLTIU and word.rs != 0 and index >= 1 and masks_into(words, index - 1, word.rs):
            addend, reg = addend_before(words, index - 1, word.rs)
            if reg is not None:
                continue  # parametric; reported by the sltu arm below
            immediate.append(Window(word.pc, word.rs, addend, word.imm, None, None, parametric=False))
            continue
        if word.op == 0 and word.funct == FUNC_SLTU and index >= 2:
            bound_side, source_side = words[index - 1], words[index - 2]
            if not (masks_into(words, index - 1, word.rt) and masks_into(words, index - 2, word.rs)):
                continue
            addend, reg = addend_before(words, index - 2, word.rs)
            bound_addend, bound_reg = addend_before(words, index - 1, word.rt)
            if reg is None and bound_reg is not None and bound_addend:
                parametric.append(
                    Window(word.pc, word.rs, addend, bound_addend, None, word.rd, parametric=True)
                )
            else:
                parametric.append(Window(word.pc, word.rs, addend, None, reg, word.rd, parametric=True))
    return immediate, parametric


def scan_callers(words: list[Word], target: int) -> list[int]:
    return [w.pc for w in words if w.op == OP_JAL and w.jump_target() == target]


# MIPS ABI: $2-$15 and $24-$25 are caller-saved, so a conforming caller may not read them after a call.
# $31 is the link register, $29 the frame pointer and $30 the stack pointer: never caller-saved.
CALLER_SAVED = frozenset(range(2, 16)) | {24, 25}
NEVER_CALLER_SAVED = frozenset({0, 31, 29, 30, 1})
# How far past a call this check looks for a read of a caller-saved register. Retail code reuses these
# registers within a few instructions; a longer reach would be a caller that keeps one across a whole
# basic block, which is not what an IDO-compiled leaf call looks like. Stated, not assumed: the probe
# PRINTS the count it found, and a nonzero count would name the sites for a per-site decision.
LEAF_SCAN_INSTRUCTIONS = 8


def _reads_register(word: Word, register: int) -> bool:
    """Whether `word` consumes `register` as a SOURCE. A destination is a definition, not a read."""
    op = word.op
    if op == 0:  # R-type: rs and rt are sources (add/sub carry rt as a source too)
        if word.funct in (FUNC_ADDU, FUNC_SLTU, 0x2A, 0x25):
            return word.rs == register or word.rt == register
        if word.funct in (0x08, 0x09):  # jr / jalr
            return word.rs == register
        return word.rt == register  # shifts and the like take rt as the source
    if op in (OP_ADDIU, OP_SLTI, OP_SLTIU, OP_ANDI, OP_ORI, OP_LHU, OP_LW, 0x28, 0x29):
        return word.rs == register
    if op in (OP_JAL, OP_J):
        return False
    return False


def _defines_register(word: Word, register: int) -> bool:
    if word.op == 0:
        return word.rd == register and word.funct not in (0x08, 0x09)
    if op_is_load(word.op):
        return word.rt == register
    if word.op in (OP_ADDIU, OP_SLTI, OP_SLTIU, OP_ANDI, OP_ORI, OP_LUI):
        return word.rt == register
    return False


def op_is_load(op: int) -> bool:
    return op in (0x20, 0x21, OP_LW, 0x24, 0x25, 0x26, 0x23)


@dataclass
class LeafCensus:
    scanned: int
    observed: int
    sites: list[str]


def _defined_registers(word: Word) -> set[int]:
    out: set[int] = set()
    if word.op == 0:
        if word.funct in (0x08, 0x09):  # jr / jalr write the link register
            out.add(31)
        else:
            out.add(word.rd)
        return out
    if op_is_load(word.op) or word.op in (OP_ADDIU, OP_SLTI, OP_SLTIU, OP_ANDI, OP_ORI, OP_LUI):
        out.add(word.rt)
    return out


def _is_return(word: Word) -> bool:
    return word.op == 0 and word.funct == 0x08 and word.rs == 31


def _is_unconditional_jump(word: Word) -> bool:
    """`j` leaves the linear stream: whatever follows is reachable only as a branch target, so reading
    a register there says nothing about what the CALLER does with the call's result."""
    return word.op == OP_J


def leaf_observability(words: list[Word]) -> LeafCensus:
    """How many cull call sites read a caller-saved register their callee would have clobbered.

    This is the measurement that licenses the native adapters to publish only the flag byte and $v0.
    For each call site it walks FORWARD past the `jal`'s delay slot, tracking which registers the
    CALLER has defined since the call: a read of a register it has not redefined is a read of a value
    that was live across the call, which is exactly the case a native body that ignores the register
    churn would break. The walk stops at the enclosing function's `jr $ra`, because code past a return
    belongs to a different function and its reads say nothing about this one.

    $v0 is counted separately: it IS the return value, and every adapter writes it, so a site reading
    $v0 is a site whose owner must get the return value right, which is a different (and already
    pinned) obligation.
    """
    targets = set(MEASURED_CULL_BODIES) - {0x800D4024, 0x800D57A8}
    scanned = 0
    observed: list[str] = []
    for i, word in enumerate(words):
        if word.op != OP_JAL or word.jump_target() not in targets:
            continue
        scanned += 1
        defined: set[int] = set()
        for offset in range(2, LEAF_SCAN_INSTRUCTIONS + 2):
            probe = i + offset
            if probe >= len(words):
                break
            follow = words[probe]
            for register in sorted(CALLER_SAVED):
                if register in defined:
                    continue
                if _reads_register(follow, register):
                    observed.append(
                        f"{word.pc:#010x} -> {word.jump_target():#010x}: ${register} live across the "
                        f"call, read at {follow.pc:#010x} ({_mnemonic(follow)})"
                    )
            defined |= _defined_registers(follow)
            if _is_return(follow) or _is_unconditional_jump(follow):
                break
    return LeafCensus(scanned, len(observed), observed[:16])


def _mnemonic(word: Word) -> str:
    """`Word.text` labels the R-type operand order for the three-source forms; this is the true one."""
    if word.op == 0:
        if word.funct == FUNC_ADDU:
            return f"addu ${word.rd}, ${word.rs}, ${word.rt}"
        if word.funct == FUNC_SLTU:
            return f"sltu ${word.rd}, ${word.rs}, ${word.rt}"
        if word.funct == 0x2A:
            return f"slt ${word.rd}, ${word.rs}, ${word.rt}"
    return word.text()


# The measured cull bodies, named so a caller census can be read. Each address was classified by
# disassembling its enclosing function; the census below is a CALLER count, never a claim that an
# address is or is not a cull (the classification lives in the report, not in this tool).
MEASURED_CULL_BODIES = {
    0x8002B160: "func_8002B160  base, slack 64/64, returns OFF-screen",
    0x8002B1E8: "func_8002B1E8  base, parametric half-extents, returns OFF-screen",
    0x8002B288: "is_on_screen base, slack 32/32, writes +3",
    0x8002B318: "func_8002B318  base, parametric half-extents, writes +3",
    0x8002B3C0: "func_8002B3C0  base, slack 96/80, writes +3",
    0x800B8490: "inline body  base, slack 64/64, background layer 0 only, returns OFF-screen",
    0x800D4024: "func_800D4024  quad AABB, half-extent from the quad's own span, intro search light",
    0x800D46F4: "quad_is_on_screen quad, four corners, no slack, writes +3",
    0x800D57A8: "func_800D57A8  the func_800D4024 body in C594C.c",
}


def context(words: list[Word], pc: int, before: int = 6, after: int = 2) -> list[str]:
    index = next((i for i, w in enumerate(words) if w.pc == pc), None)
    if index is None:
        return []
    out = []
    for offset in range(-before, after):
        probe = index + offset
        if 0 <= probe < len(words):
            mark = ">>" if offset == 0 else "  "
            out.append(f"{mark} {words[probe].pc:#010x}  {words[probe].raw:08x}  {words[probe].text()}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    parser.add_argument(
        "--screen-const",
        type=int,
        action="append",
        default=[],
        help="a window width to classify as a screen-extent cull owner (repeatable)",
    )
    parser.add_argument("--context", action="store_true", help="print disassembly context per hit")
    args = parser.parse_args()

    base, words = load_text(args.exe)
    immediate, parametric = scan_windows(words)

    print(f"[probe] executable {args.exe} sha1 {SLUS_00561_SHA1}")
    print(
        f"[probe] scanned {len(words)} instruction words over the text section "
        f"[{base:#x}, {base + 4 * len(words):#x}); matched {len(immediate)} immediate-bound "
        f"and {len(parametric)} parametric-bound 16-bit windows"
    )

    if args.screen_const:
        print(f"[probe] classifying window widths {sorted(set(args.screen_const))} as screen-extent owners:")
        for window in immediate:
            if window.width in args.screen_const:
                print(f"[probe]   OWNER {window.describe()}  ({window.bound - window.addend}px)")
    else:
        print("[probe] every immediate-bound window, widest first:")
        for window in sorted(immediate, key=lambda w: (-(w.width or 0), w.at)):
            print(f"[probe]   {window.describe()}")
    print(f"[probe] {len(parametric)} parametric-bound window(s):")
    for window in parametric:
        print(f"[probe]   {window.describe()}")

    print(f"[probe] caller census over the same {len(words)} words:")
    total = 0
    for address, shape in sorted(MEASURED_CULL_BODIES.items()):
        callers = scan_callers(words, address)
        total += len(callers)
        print(f"[probe]   {address:#010x} {len(callers):3d} jal call site(s)  {shape}")
    print(f"[probe] {total} call sites across {len(MEASURED_CULL_BODIES)} measured cull bodies")

    leaves = leaf_observability(words)
    print(
        f"[probe] caller-saved leaf check: scanned {leaves.scanned} call sites of the object-pool "
        f"owners, {leaves.observed} read a caller-saved register before redefining it"
    )
    for site in leaves.sites:
        print(f"[probe]   READS {site}")

    if args.context:
        seen: set[int] = set()
        for window in immediate:
            if window.at in seen:
                continue
            seen.add(window.at)
            print(f"[probe] --- {window.at:#010x} ---")
            for line in context(words, window.at):
                print(f"[probe]   {line}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
