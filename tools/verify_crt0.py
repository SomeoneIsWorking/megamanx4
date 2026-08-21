#!/usr/bin/env python3
"""verify_crt0.py — RE-01: re-derive Mega Man X4's crt0 boot group FROM THE BYTES.

THE QUESTION IT EXISTS TO ANSWER: what does SLUS_005.61's entry function actually do, and can the
framework's generic `crt0_setup` (external/psxport/runtime/recomp/native_boot.cpp) reproduce it?
`GameConfig`'s boot group is consumed AS A GROUP, so a single field pasted out of a reference is
worse than a zero. This tool derives every field of that group by symbolically executing the entry
function, and it prints the disassembly line that justifies each one.

METHOD: a tiny forward symbolic interpreter over the entry function, from the PS-EXE header's pc0
until `break`. It tracks only immediate-built register values (lui / addiu / addi / ori / addu-with-
zero / sll / srl / or-with-constant) — the same restriction psxport's tools/disas.py documents — and
records the four structural events a PSY-Q crt0 is made of:
  * the .bss clear loop      (`sw zero,0(rX)` + `addiu rX,rX,4` + `sltu at,rX,rY` + backward `bne`)
  * the stack-top build      (`lw` from an absolute word, an OPTIONAL bias `addi`, `or sp,rD,0x80000000`)
  * the heap base/size build (`sll 3`/`srl 3` mask, a second absolute `lw`, two `subu`)
  * the two `jal`s           (libc/heap init, then game-main) and which arg regs are live at each
Every store to an absolute address is recorded, so "this game's crt0 writes NO heap globals" is a
measurement over a complete list rather than an absence nobody looked for.

WHAT `--check` COMPARES, and why it is the only comparison that gates anything: it parses
game/core/game_config.cpp — THE FILE THAT SHIPS — and diffs its `kCrt0*`/`kPsExe*` constants against
what this run measured from the bytes. The tool keeps NO table of its own. It used to (`X4_EXPECT`),
the port kept a second copy, nothing compared them, and with both gates green `kCrt0GameMain` could be
and was set to 0x80999999. The `static_assert`s in that file check the constants' internal RELATIONS
and are worth keeping, but they are not this: `hi - lo == 0x46B20` holds just as well when both values
are wrong. `--check` also asserts every GameConfig crt0 field names its measured constant — a PARTIAL
fill is the faked-step failure and is the one state that looks like progress.

WHAT A NEGATIVE PRINTS — the point of the file. Nothing here reports a bare "ok"/"none":
  * a MALFORMED corpus of any shape EXITS 2 saying it scanned NOTHING — a missing path, a 0-byte file
    and a file of garbage all route through the same refusal (it never returns a clean empty result,
    and it never lets psexe.load's ValueError escape as a traceback, which has no exit-code contract);
  * a missing/unparseable SHIPPING file is a REFUSAL too, never "nothing to compare, pass";
  * a function with no .bss loop is REFUSED with the instruction count it walked and the events it
    did see, so "not a crt0" carries its denominator;
  * every extracted field prints with its address AND the instruction text behind it, and every field
    the shape does NOT have prints as `absent (no store to an absolute address among the N recorded)`;
  * the framework-compatibility verdict lists each incompatibility with the framework source line it
    contradicts, and prints the ones that DO match too, so a PASS is distinguishable from a no-op.

BLIND SPOTS, stated because the tool cannot see past them:
  * immediate-only tracking: a value arriving through a pointer in a register is `?`, not resolved.
  * it does not follow the backward branch of the .bss loop (it reads bounds from the first
    iteration and invalidates the counter), so a loop whose bounds are recomputed per iteration
    would be mis-read. It asserts the loop shape instead of assuming it.
  * it walks straight-line code with delay slots applied before their branch/jal; a crt0 with real
    control flow (conditional heap sizing) would need a real CFG. If that ever happens here the
    refusal path fires rather than a wrong answer, because the structural asserts would not match.
  * it says NOTHING about whether the values are right at RUNTIME — it reads the static image. The
    two absolute `lw` sites are read from the loaded text image, which is correct only because both
    lie inside .text and nothing has written them before crt0 runs. That is checked and printed.

--selftest gates BOTH classes THROUGH THE SHIPPING PATH — every case calls the same check_shipped()
that --check calls, not a pure helper beside it. The positive: the shipped constants must equal this
run's measurement (21 comparisons). The negatives sabotage each side of that comparison in turn — a
flipped immediate in the BINARY, a hand-edited constant in a copy of the SHIPPING FILE (three of them,
including one PS-EXE header fact), a hand-edited CITED SHA1, a HALF-filled GameConfig group, a wrong
resident recomp range, a wrong entry PC (main() must be refused, not partially parsed), and three
malformed-corpus shapes (missing /
0-byte / garbage) that must all refuse. The framework-source cases also delete four required crt0
mechanisms and require a contradiction each time. Current denominator: 26/26 without --cross;
with --cross, a second game's executable adds three independent cases -> 29/29.
"""
from __future__ import annotations

import argparse
import copy
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# psxport's PS-EXE loader, resolved the way CMake resolves the framework: $PSXPORT_DIR, defaulting to
# the pinned submodule. Never an absolute path, so a bare clone works.
PSXPORT = os.environ.get("PSXPORT_DIR") or os.path.join(ROOT, "external", "psxport")
sys.path.insert(0, os.path.join(PSXPORT, "tools", "recomp"))

DEFAULT_EXE = os.path.join(ROOT, "scratch", "bin", "megamanx4", "SLUS_005.61")

# ── THE RECORDED EXPECTATION IS THE SHIPPING FILE. THERE IS NO SECOND COPY ─────────────────────────
# This tool used to hold its own table (`X4_EXPECT = {...}`) of the eleven measured addresses and
# assert the BINARY still matched it. game/core/game_config.cpp held a SECOND copy as `kCrt0*`
# constants, and nothing compared the two. That is not a hypothetical: with the tool's table intact,
# `kCrt0GameMain` was set to 0x80999999, `kCrt0LibcInit` to 0xDEADBEEF and `kCrt0StackTopBase` to
# 0x80001234, and BOTH `--check` and `--selftest` passed. The tool verified itself; the static_asserts
# verified internal relations (`hi - lo == 0x46B20` holds just as well when both are wrong); the value
# that actually SHIPS was ungated.
#
# So the table is gone. `--check` now parses game/core/game_config.cpp and diffs ITS constants against
# what this run measured from the bytes, in ONE comparison — a hand-edit of either side goes red. What
# is recorded lives where it ships.
SHIPPED_FILE = os.path.join(ROOT, "game", "core", "game_config.cpp")

# shipping constant -> the measured field it must equal. `kCrt0Entry` is `= kPsExeEntry` in the file,
# which the parser resolves, so the alias is checked as an alias rather than assumed to be one.
CONST_FIELD = {
    "kPsExeEntry":       "entry",
    "kCrt0Entry":        "entry",
    "kCrt0BssZeroLo":    "bssZeroLo",
    "kCrt0BssZeroHi":    "bssZeroHi",
    "kCrt0StackTopBase": "stackTopBase",
    "kCrt0StackTopBas2": "stackTopBase2",
    "kCrt0HeapBase":     "heapBase",
    "kCrt0Gp":           "gp",
    "kCrt0LibcInit":     "libcInit",
    "kCrt0GameMain":     "gameMain",
}
# shipping constant -> PS-EXE HEADER attribute it claims to quote (measured by psexe.load, not by the
# symbolic interpreter — a second, independent side of the same file's comment block).
HEADER_CONST = {"kPsExeEntry": "entry", "kPsExeTextAddr": "load", "kPsExeTextSize": "text_size"}

# ── REQUIRED vs OPTIONAL, and this split IS the framework's contract, not this tool's opinion ──────
# external/psxport/runtime/recomp/crt0_boot.h::crt0_plan walks an explicit `req[]` list and REFUSES the
# boot when any entry is 0 — bssZeroLo, bssZeroHi, stackTopBase, stackTopBase2, heapBase, gp, libcInit,
# stackBias.declared. For THOSE fields zero means "not reverse-engineered yet", so a mix of measured
# values and zeros is the faked-step failure and is red. `gameMain`/`crt0` are required by this port for
# the same reason one layer out (native_boot dispatches gameMain; crt0_audit re-derives the group from
# the instruction stream at `crt0`, so a zero there disables the boot-time audit itself).
CFG_REQUIRED_CONST = {
    "bssZeroLo": "kCrt0BssZeroLo", "bssZeroHi": "kCrt0BssZeroHi",
    "stackTopBase": "kCrt0StackTopBase", "stackTopBase2": "kCrt0StackTopBas2",
    "heapBase": "kCrt0HeapBase", "gp": "kCrt0Gp",
    "libcInit": "kCrt0LibcInit", "gameMain": "kCrt0GameMain", "crt0": "kCrt0Entry",
}
# The two OPTIONAL fields. Zero here is NOT "unset": crt0_boot.h documents it as ABSENT — "this guest
# crt0 has no such global" — sets `p.storeHeapSize = cfg->heapSizePtr != 0`, and crt0_apply performs the
# store only under that flag. So zero is a MEASURED answer, and the only honest gate on it is a
# DIRECTIONAL comparison against the measurement: absent-and-0 passes, absent-and-nonzero is an invented
# address, and present-and-0 is a store the guest makes that the framework would silently skip. This is
# the field pair that used to be lumped into the all-or-nothing group check, which is why a correct X4
# config read as a PARTIAL fill and went red.
CFG_OPTIONAL_CONST = {"heapSizePtr": "kCrt0HeapSizePtr", "heapBasePtr": "kCrt0HeapBasePtr"}
# Every crt0-group field the initialiser must mention EXPLICITLY. A field left to implicit 0 by omission
# is invisible to review, so omission is red for optional fields too.
CFG_FIELD_CONST = {**CFG_REQUIRED_CONST, **CFG_OPTIONAL_CONST}

# The recompiler router consumes the executable's PHYSICAL text range. These expressions name the
# header constants already compared to the retail PS-X EXE, so a clean clone can compile without a
# generated header while the shipping range remains mechanically tied to the bytes.
REC_RANGE_EXPR = {
    "recMainLo": "kPsExeTextAddr & 0x1FFFFFFFu",
    "recMainHi": "(kPsExeTextAddr + kPsExeTextSize) & 0x1FFFFFFFu",
}

# The stack-top bias is a GameConfig field now (`.stackBias = {declared, value}`), so it is NOT a
# shape-only fact any more: it is SHIPPED and must be diffed like every other shipped value. Zero
# cannot double as "unset" for it — 0 is X4's real measured bias — which is exactly why crt0_boot.h
# gave it a separate `declared` flag and refuses an undeclared one.
STACKBIAS_CONST = "kCrt0StackBias"

# ── SHAPE FACTS WITH NO SHIPPING COUNTERPART, and why each one has none ────────────────────────────
#   libcArgs — which arg registers are live at the libc-init jal. A property of the CALL, asserted by
#              framework_verdict; a GameConfig field would be the wrong home for it.
X4_SHAPE = {"libcArgs": ("a0", "a1")}

# ── TEST FIXTURE, NOT A PORT VALUE ────────────────────────────────────────────────────────────────
# Tomba! 2's MAIN.EXE crt0, as recorded INDEPENDENTLY (and long before this tool existed) in
# ../Tomba2Engine/game/core/game_config.cpp. It is the extractor's strongest POSITIVE CONTROL: a
# different game, a different crt0 shape, and eleven values someone else derived by hand. If the
# extractor were echoing constants or pattern-matching X4 specifically, it could not reproduce these.
# Used only by --selftest --cross; never read by this port. (No X4 value is derived from it.)
TOMBA2_CONTROL = {
    "entry": 0x800896E0, "bssZeroLo": 0x800BE0D8, "bssZeroHi": 0x80106228,
    "stackTopBase": 0x800A3F88, "stackTopBias": -8, "stackTopBase2": 0x800A3F8C,
    "heapBase": 0x80106228, "heapSizePtr": 0x800ABEF8, "heapBasePtr": 0x800ABEF4,
    "gp": 0x800BE0D4, "libcInit": 0x80089860, "gameMain": 0x80050B08,
}

REG = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5", "t6",
       "t7", "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1", "gp", "sp",
       "fp", "ra"]


class Refused(Exception):
    """The corpus or the target is not what this tool can speak about. Never a clean empty result."""


# ── the shipping file, parsed ──────────────────────────────────────────────────────────────────────
# int32_t as well as uint32_t: the stack bias is SIGNED (four of this workspace's six executables bias
# by -8), and a parser that only saw unsigned constants would report `kCrt0StackBias` as NOT DEFINED —
# i.e. it would fail red for the wrong reason and could never gate the value.
CONST_RE = re.compile(r"^\s*static\s+constexpr\s+(?:u?int32_t)\s+(\w+)\s*=\s*([^;]+);", re.M)
CFG_OPEN_RE = re.compile(r"\bg_x4_cfg\s*=\s*\{")
FIELD_RE = re.compile(r"\.(\w+)\s*=\s*([^,\n]*)")
# `.stackBias = {declared, value}` — a BRACED field, which FIELD_RE truncates at the first comma
# ("{1"). Parsed separately so both members are gated; if this regex ever stops matching, the field
# reads as ABSENT and check_shipped fails loudly rather than skipping it.
STACKBIAS_RE = re.compile(r"\.stackBias\s*=\s*\{([^}]*)\}")


def _strip_line_comments(s: str) -> str:
    """Drop `//` tails. Needed because this file's comments legitimately WRITE things like
    `cfg->heapSizePtr` and `.bssZeroLo = 0`, and a parser that read prose as code would compare a
    sentence to a measurement."""
    return "\n".join(ln.split("//")[0] for ln in s.splitlines())


def _int_or_name(tok: str, consts: dict, where: str):
    t = tok.strip().rstrip("uU")
    try:
        return int(t, 0)
    except ValueError:
        pass
    if t in consts:
        return consts[t]
    raise Refused(f"{where}: cannot evaluate {tok.strip()!r}. This tool compares the SHIPPED value to "
                  f"the measured one, so an expression it cannot evaluate is a REFUSAL, never a skip — "
                  f"a skipped field is an ungated field.")


def parse_shipped(path: str = SHIPPED_FILE) -> dict:
    """{'consts': {name: value}, 'cfg': {field: token}, 'path': path}.

    REFUSES rather than returning a partial: a missing file, a file with no `static constexpr uint32_t`
    at all, no `g_x4_cfg` initialiser, or a value it cannot evaluate. Every one of those, returned
    quietly, would read as "the shipped constants agree with the bytes"."""
    if not os.path.isfile(path):
        raise Refused(f"{path} does not exist — the SHIPPING file was not read, so NOTHING was "
                      f"compared against the measurement. This is not a pass.")
    return parse_shipped_src(open(path, encoding="utf-8").read(), path)


def parse_shipped_src(text: str, path: str) -> dict:
    """The parser proper, over SOURCE TEXT. Split out so --selftest can feed it a deliberately
    sabotaged copy of the real file and require the comparison to go RED — the shipping path itself,
    not a helper beside it."""
    src = _strip_line_comments(text)
    consts: dict[str, int] = {}
    for m in CONST_RE.finditer(src):
        consts[m.group(1)] = _int_or_name(m.group(2), consts, f"{path}:{m.group(1)}")
    if not consts:
        raise Refused(f"{path} defines NO `static constexpr uint32_t` at all — either the file was "
                      f"rewritten in a shape this parser cannot read, or the measured constants were "
                      f"deleted. Scanned {len(src.splitlines())} comment-stripped lines, matched 0.")
    m = CFG_OPEN_RE.search(src)
    if not m:
        raise Refused(f"{path} has no `g_x4_cfg = {{` initialiser — the GameConfig this port ships "
                      f"could not be located, so its crt0 group was NOT checked.")
    i, depth, end = m.end(), 1, None
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    if end is None:
        raise Refused(f"{path}: unbalanced braces after `g_x4_cfg = {{` — refusing to guess where the "
                      f"initialiser ends.")
    body = src[m.end():end]
    cfg = {f: v.strip() for f, v in FIELD_RE.findall(body)}
    sb = STACKBIAS_RE.search(body)
    # None = the initialiser does not mention `.stackBias` at all. Kept as None rather than defaulted,
    # because a default would silently supply the very declaration crt0_plan refuses to assume.
    stackbias = [t.strip() for t in sb.group(1).split(",")] if sb else None
    # The RAW text (comments included) is kept for one reason: the file also CITES the sha1 of the
    # executable these constants were measured from, and that citation is a measured value shipped in
    # the file with nothing comparing it — the same defect one layer down. check_shipped hashes the
    # image and diffs it.
    return {"consts": consts, "cfg": cfg, "stackbias": stackbias, "path": path, "raw": text}


SHA1_RE = re.compile(r"\b[0-9a-f]{40}\b")


def check_shipped(g: dict, exe, sh: dict, exe_path: str | None = None) -> tuple[list[str], list[str]]:
    """THE comparison this tool exists for: the values game_config.cpp SHIPS vs the values measured
    from these bytes in this run. Returns (fails, lines) — `lines` is printed either way, so a PASS
    carries its denominator (which constants were compared) instead of reading as a bare 'ok'."""
    fails, lines = [], []
    consts, cfg = sh["consts"], sh["cfg"]

    for name, field in sorted(CONST_FIELD.items()):
        if name not in consts:
            fails.append(f"{name} is NOT DEFINED in {os.path.relpath(sh['path'], ROOT)} — the measured "
                         f"{field} = {fmt(g.get(field))} is then shipped nowhere")
            continue
        want, got = g.get(field, "MISSING"), consts[name]
        ok = want == got
        lines.append(f"    {'ok ' if ok else 'BAD'} {name:<20} ships {fmt(got):<12} measured "
                     f"{fmt(want):<12} ({field})")
        if not ok:
            fails.append(f"{name} ships {fmt(got)} but this run measured {field} = {fmt(want)}")

    # A generated resident function is unreachable unless this range encloses it. The first substrate
    # boot exposed the old zero/zero config as a recomp-MISS for an address rec_func_index already
    # contained. Require references to the measured header constants, not a second literal copy.
    range_values = {
        "recMainLo": exe.load & 0x1FFFFFFF,
        "recMainHi": (exe.load + len(exe.text)) & 0x1FFFFFFF,
    }
    for field, expected_token in REC_RANGE_EXPR.items():
        token = cfg.get(field)
        same = token is not None and re.sub(r"\s+", "", token) == re.sub(
            r"\s+", "", expected_token
        )
        lines.append(
            f"    {'ok ' if same else 'BAD'} {'.' + field:<20} ships "
            f"{token or '(omitted)'} -> {fmt(range_values[field])}"
        )
        if not same:
            fails.append(
                f"g_x4_cfg ships .{field} = {token or '(omitted)'}, expected {expected_token} "
                "so the resident recomp range remains tied to the measured PS-X EXE header"
            )

    # ── THE OPTIONAL PAIR, gated DIRECTIONALLY in both senses ──────────────────────────────────────
    # These two fields are the whole reason this function had to change. crt0_boot.h reads 0 as ABSENT
    # ("this guest crt0 has no such global") and performs no store; so for X4, whose only absolute store
    # is `sw ra`, 0 is the CORRECT shipped value and the previous all-or-nothing group check was
    # refusing a right config. What must still go red is a DISAGREEMENT with the measurement, either
    # way round:
    #   measured ABSENT  + shipped nonzero -> an invented address; the framework would inject a store
    #                                         the real game never makes and diverge any RAM compare.
    #   measured PRESENT + shipped 0       -> the framework would skip a store the guest DOES make,
    #                                         leaving a heap global the game later reads at 0.
    for field, cname in sorted(CFG_OPTIONAL_CONST.items()):
        measured = g.get(field)                       # None == this crt0 has no such store
        tok = cfg.get(field)                          # the struct token; omission is caught below
        shipped_const = consts.get(cname)
        if measured is None:
            if tok is not None and tok != "0":
                fails.append(f"g_x4_cfg ships .{field} = {tok}, but this crt0 stores {field} NOWHERE "
                             f"(measured over ALL {len(g['abs_stores'])} absolute stores in the "
                             f"function) — that address was invented, not measured. 0 is the value "
                             f"crt0_boot.h reads as ABSENT")
            elif shipped_const is not None:
                fails.append(f"{cname} = {fmt(shipped_const)} is defined, but this crt0 stores {field} "
                             f"NOWHERE (all {len(g['abs_stores'])} absolute stores checked) — an "
                             f"address exists in the file for a global this game does not have")
            else:
                lines.append(f"    ok  {'.' + field:<20} 0 = ABSENT, as measured (no store to {field} "
                             f"among the {len(g['abs_stores'])} absolute stores; crt0_boot.h performs "
                             f"no store and logs the count)")
        else:
            if tok is None or tok == "0":
                fails.append(f"this crt0 DOES store {field} at {fmt(measured)}, but g_x4_cfg ships "
                             f".{field} = {tok or '(omitted)'}. crt0_boot.h reads 0 as ABSENT, so the "
                             f"framework would perform NO store for a store the guest makes")
            elif shipped_const is None:
                fails.append(f"g_x4_cfg ships .{field} = {tok} but no {cname} is defined — the shipped "
                             f"value cannot be diffed against the measured {fmt(measured)}")
            elif tok != cname:
                fails.append(f"g_x4_cfg ships .{field} = {tok}, which is neither 0 nor {cname}")
            elif shipped_const != measured:
                fails.append(f"{cname} ships {fmt(shipped_const)} but this crt0 stores {field} at "
                             f"{fmt(measured)}")
            else:
                lines.append(f"    ok  {'.' + field:<20} ships {cname} = {fmt(shipped_const)}  "
                             f"measured {fmt(measured)} (PRESENT, and the store is performed)")

    # ── THE STACK BIAS, now a shipped field rather than a shape-only fact ───────────────────────────
    # `.stackBias = {declared, value}`. crt0_plan requires `declared` to be nonzero (it is in its `req[]`
    # list) precisely BECAUSE 0 is X4's real measured bias, so zero cannot double as "unset" for the
    # value. Both members are diffed: an undeclared bias would make the framework refuse the boot, and a
    # wrong value would put sp 8 bytes off AND shift the heap size by the same 8 (the biased word feeds
    # the heap-size subtraction), which boots fine and fails somewhere else entirely.
    sb, measured_bias = sh.get("stackbias"), g.get("stackTopBias")
    if sb is None:
        fails.append("the g_x4_cfg initialiser does not set .stackBias at all — crt0_plan lists "
                     "`stackBias.declared` among its REQUIRED fields and REFUSES the boot when it is 0, "
                     f"and this crt0's measured bias is {measured_bias}, for which 0 is a real value")
    elif len(sb) != 2:
        fails.append(f"g_x4_cfg's .stackBias = {{{', '.join(sb)}}} does not have exactly 2 members "
                     f"(declared, value) — refusing to guess which is which")
    else:
        dec_tok, val_tok = sb
        try:
            dec = _int_or_name(dec_tok, consts, f"{sh['path']}:.stackBias.declared")
            val = _int_or_name(val_tok, consts, f"{sh['path']}:.stackBias.value")
        except Refused as e:
            fails.append(str(e))
            dec = val = None
        if dec is not None:
            if not dec:
                fails.append(f"g_x4_cfg ships .stackBias = {{{dec_tok}, {val_tok}}} — declared = 0, and "
                             f"crt0_plan REFUSES to boot on that. This crt0's measured bias is "
                             f"{measured_bias}, so the declaration is the only thing that can say "
                             f"'0 is the answer' rather than 'nobody looked'")
            elif val != measured_bias:
                fails.append(f"g_x4_cfg ships .stackBias value {val_tok} (= {val}) but this run measured "
                             f"a bias of {measured_bias} from the instruction stream: sp would come out "
                             f"0x{((g.get('stackTopWord', 0) + val) | 0x80000000) & 0xFFFFFFFF:08X} "
                             f"instead of 0x{g.get('sp', 0):08X}")
            else:
                lines.append(f"    ok  {'.stackBias':<20} ships {{declared={dec_tok}, {val_tok}={val}}}"
                             f"  measured bias {measured_bias}")
    # …and the named constant behind it, so the value is not a bare literal nobody can diff.
    if STACKBIAS_CONST not in consts:
        fails.append(f"{STACKBIAS_CONST} is NOT DEFINED — the measured bias {measured_bias} is then "
                     f"shipped as a bare literal with no constant to cite the disassembly against")
    else:
        ok = consts[STACKBIAS_CONST] == measured_bias
        lines.append(f"    {'ok ' if ok else 'BAD'} {STACKBIAS_CONST:<20} ships "
                     f"{consts[STACKBIAS_CONST]:<12} measured {measured_bias:<12} (stackTopBias)")
        if not ok:
            fails.append(f"{STACKBIAS_CONST} ships {consts[STACKBIAS_CONST]} but this run measured a "
                         f"stack-top bias of {measured_bias}")

    hdr = {"entry": exe.entry, "load": exe.load, "text_size": exe.text_size}
    for name, attr in sorted(HEADER_CONST.items()):
        if name not in consts:
            fails.append(f"{name} is NOT DEFINED — the PS-EXE header fact it quotes is unchecked")
            continue
        ok = consts[name] == hdr[attr]
        lines.append(f"    {'ok ' if ok else 'BAD'} {name:<20} ships {fmt(consts[name]):<12} header "
                     f"{fmt(hdr[attr]):<12} (PS-EXE {attr})")
        if not ok:
            fails.append(f"{name} ships {fmt(consts[name])} but the PS-EXE header's {attr} is "
                         f"{fmt(hdr[attr])}")

    # The sha1 the file CITES for the image these constants came from. Every 40-hex token in the file
    # must be the hash of the executable actually read — a citation that names a different image is a
    # measurement attributed to bytes nobody checked. Zero tokens is reported, not failed: the file is
    # free to stop citing it, but then the denominator says so out loud.
    if exe_path and os.path.isfile(exe_path):
        import hashlib
        digest = hashlib.sha1(open(exe_path, "rb").read()).hexdigest()
        cited = sorted(set(SHA1_RE.findall(sh["raw"])))
        for h in cited:
            ok = h == digest
            lines.append(f"    {'ok ' if ok else 'BAD'} {'cited sha1':<20} ships {h[:16]}… image "
                         f"{digest[:16]}…")
            if not ok:
                fails.append(f"the file cites sha1 {h} but {os.path.relpath(exe_path, ROOT)} hashes to "
                             f"{digest} — these constants were measured from a DIFFERENT image than "
                             f"the one this run read")
        if not cited:
            lines.append(f"    ok  {'cited sha1':<20} the file cites NO sha1 (0 of 40-hex tokens "
                         f"found) — nothing to compare against {digest[:16]}…")

    # ── THE STRUCT, as a GROUP — over the REQUIRED fields only, and that scope is the fix ───────────
    # The "consumed as a group" concern is real and stays: crt0_plan walks its `req[]` list and refuses
    # the boot if ANY entry is 0, so a half-filled required group is the faked-step failure that looks
    # like progress. What was WRONG was the DENOMINATOR — heapSizePtr/heapBasePtr were counted in it, so
    # a config that correctly says "this crt0 has no such global" read as 9-filled/2-zero and went red
    # while the group it actually describes was complete. Those two are gated above, directionally,
    # against the measurement instead.
    missing = [f for f in CFG_FIELD_CONST if f not in cfg]
    if missing:
        fails.append(f"the g_x4_cfg initialiser does not set {', '.join(sorted(missing))} — a boot-group "
                     f"field left to implicit 0 by omission is invisible to review")
    zero, filled, wrong = [], [], []
    for field, cname in CFG_REQUIRED_CONST.items():
        tok = cfg.get(field)
        if tok is None:
            continue                        # already reported as omitted, above
        if tok == "0":
            zero.append(field)
        elif tok == cname:
            filled.append(field)
        else:
            wrong.append(f".{field} = {tok}")
    # `stackBias.declared` is the 10th entry of crt0_plan's required list, so it belongs in this
    # partition too: a group of filled addresses with an UNDECLARED bias still refuses to boot.
    n_req = len(CFG_REQUIRED_CONST) + 1
    if sh.get("stackbias") and len(sh["stackbias"]) == 2:
        (filled if sh["stackbias"][0] not in ("0", "false") else zero).append("stackBias.declared")
    if wrong:
        fails.append(f"g_x4_cfg's REQUIRED crt0 group holds value(s) that are neither 0 nor the measured "
                     f"constant: {', '.join(wrong)}")
    if zero and filled:
        fails.append(f"g_x4_cfg's REQUIRED crt0 group is PARTIALLY filled — {len(filled)} field(s) "
                     f"({', '.join(sorted(filled))}) carry measured values while {len(zero)} "
                     f"({', '.join(sorted(zero))}) are still 0. crt0_plan (crt0_boot.h) consumes these "
                     f"AS A GROUP and REFUSES the boot on any zero among them, so a half-written group "
                     f"is an un-RE'd crt0 wearing a citation. (heapSizePtr/heapBasePtr are NOT in this "
                     f"count — for those two, 0 is the measured meaning ABSENT.)")
    lines.append(f"    ok  {'g_x4_cfg req group':<20} {len(zero)} zero / {len(filled)} filled of "
                 f"{n_req} REQUIRED (+{len(CFG_OPTIONAL_CONST)} optional, gated against the "
                 f"measurement) — "
                 + ("NOT REVERSE-ENGINEERED, all zero" if not filled else
                    "fully filled from the measured constants" if not zero else "MIXED"))
    return fails, lines


# ── instruction decode (only the forms a PSY-Q crt0 uses; anything else is 'other') ────────────────
def decode(w: int) -> dict:
    op = w >> 26
    rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    sa = (w >> 6) & 31
    fn = w & 63
    imm = w & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    d = dict(op=op, rs=rs, rt=rt, rd=rd, sa=sa, fn=fn, imm=imm, simm=simm, kind="other", raw=w)
    if op == 0x00:
        d["kind"] = {0x00: "sll", 0x02: "srl", 0x21: "addu", 0x23: "subu", 0x25: "or",
                     0x2B: "sltu", 0x08: "jr", 0x0D: "break"}.get(fn, "other")
    else:
        d["kind"] = {0x02: "j", 0x03: "jal", 0x04: "beq", 0x05: "bne", 0x08: "addi", 0x09: "addiu",
                     0x0C: "andi", 0x0D: "ori", 0x0F: "lui", 0x23: "lw", 0x2B: "sw"}.get(op, "other")
    return d


def text_of(a: int, d: dict) -> str:
    k = d["kind"]
    r = REG
    if k == "lui":
        return f"lui {r[d['rt']]}, 0x{d['imm']:04x}"
    if k in ("addiu", "addi", "ori", "andi"):
        return f"{k} {r[d['rt']]}, {r[d['rs']]}, {d['simm']}"
    if k in ("lw", "sw"):
        return f"{k} {r[d['rt']]}, {d['simm']}({r[d['rs']]})"
    if k in ("sll", "srl"):
        return f"{k} {r[d['rd']]}, {r[d['rt']]}, {d['sa']}"
    if k in ("addu", "subu", "or", "sltu"):
        return f"{k} {r[d['rd']]}, {r[d['rs']]}, {r[d['rt']]}"
    if k in ("jal", "j"):
        return f"{k} 0x{((a + 4) & 0xF0000000) | ((d['raw'] & 0x03FFFFFF) << 2):08x}"
    if k in ("beq", "bne"):
        return f"{k} {r[d['rs']]}, {r[d['rt']]}, 0x{a + 4 + d['simm'] * 4:08x}"
    return f".word 0x{d['raw']:08x}" if k == "other" else k


def target(a: int, d: dict) -> int:
    return ((a + 4) & 0xF0000000) | ((d["raw"] & 0x03FFFFFF) << 2)


# ── the extractor ─────────────────────────────────────────────────────────────────────────────────
def extract(exe, entry: int, limit: int = 256) -> dict:
    """Symbolically execute from `entry` until `break`, returning the boot group + the evidence."""
    reg: dict[int, int | None] = {i: None for i in range(32)}
    reg[0] = 0
    # PROVENANCE, so `stackTopBase2` is identified by DATAFLOW rather than by elimination: for each
    # register, the absolute address of the `lw` that currently defines it (None once it is
    # redefined by anything else). The heap-size `subu` then names its own operands' load sites.
    prov: dict[int, int | None] = {i: None for i in range(32)}
    out: dict = {"entry": entry, "why": {}, "abs_stores": [], "abs_loads": [], "jals": [],
                 "walked": 0, "events": []}
    a = entry
    n = 0
    pending_loop_counter = None

    def apply(addr: int, d: dict):
        """Register-effect of one instruction, immediate-only."""
        k, rs, rt, rd = d["kind"], d["rs"], d["rt"], d["rd"]
        # provenance: any write kills it; a `lw` from a resolved absolute address sets it (below).
        # `addi/addiu` PRESERVES it, because a biased stack top is still the stack-top load's value.
        if k in ("lui", "ori", "andi", "sll", "srl", "lw"):
            prov[rt if k in ("lui", "ori", "andi", "lw") else rd] = None
        elif k in ("addiu", "addi"):
            prov[rt] = prov[rs]
        elif k in ("addu", "subu", "or", "sltu"):
            prov[rd] = None
        if k == "lui":
            reg[rt] = (d["imm"] << 16) & 0xFFFFFFFF
        elif k in ("addiu", "addi"):
            reg[rt] = None if reg[rs] is None else (reg[rs] + d["simm"]) & 0xFFFFFFFF
        elif k == "ori":
            reg[rt] = None if reg[rs] is None else (reg[rs] | d["imm"]) & 0xFFFFFFFF
        elif k == "andi":
            reg[rt] = None if reg[rs] is None else (reg[rs] & d["imm"]) & 0xFFFFFFFF
        elif k == "sll":
            reg[rd] = None if reg[rt] is None else (reg[rt] << d["sa"]) & 0xFFFFFFFF
        elif k == "srl":
            reg[rd] = None if reg[rt] is None else (reg[rt] >> d["sa"]) & 0xFFFFFFFF
        elif k in ("addu", "subu", "or"):
            x, y = reg[rs], reg[rt]
            if x is None or y is None:
                reg[rd] = None
            else:
                reg[rd] = ((x + y) if k == "addu" else (x - y) if k == "subu" else (x | y)) & 0xFFFFFFFF
        elif k == "sltu":
            reg[rd] = None
        elif k == "lw":
            reg[rt] = None            # value unknown until resolved below by the caller
        reg[0] = 0

    while n < limit:
        try:
            w = exe.word(a)
        except IndexError as e:
            raise Refused(f"walked {n} instructions from 0x{entry:08X} and ran off the text image: {e}")
        d = decode(w)
        out["walked"] = n + 1

        if d["kind"] == "break":
            out["events"].append((a, "break", text_of(a, d)))
            break

        # ── .bss clear loop: sw zero,0(rX) … addiu rX,rX,4 … sltu at,rX,rY … bne at,zero,<back>
        if d["kind"] == "sw" and d["rt"] == 0 and reg[d["rs"]] is not None:
            lo = (reg[d["rs"]] + d["simm"]) & 0xFFFFFFFF
            ctr, hi, hi_reg = d["rs"], None, None
            for k2 in range(1, 6):
                d2 = decode(exe.word(a + 4 * k2))
                if d2["kind"] == "sltu" and d2["rs"] == ctr and reg[d2["rt"]] is not None:
                    hi, hi_reg = reg[d2["rt"]], d2["rt"]
                if d2["kind"] == "bne" and d2["simm"] < 0 and hi is not None:
                    out["bssZeroLo"], out["bssZeroHi"] = lo, hi
                    out["why"]["bssZeroLo"] = (a, text_of(a, d))
                    out["why"]["bssZeroHi"] = (a + 4 * k2 - 4,
                                               f"sltu at, {REG[ctr]}, {REG[hi_reg]}  ; {REG[hi_reg]}=0x{hi:08X}")
                    out["events"].append((a, "bss_loop", f"[0x{lo:08X},0x{hi:08X}) size 0x{hi - lo:X}"))
                    pending_loop_counter = ctr
                    break

        # ── absolute loads / stores ────────────────────────────────────────────────────────────────
        if d["kind"] in ("lw", "sw") and reg[d["rs"]] is not None:
            tgt = (reg[d["rs"]] + d["simm"]) & 0xFFFFFFFF
            rec = (a, tgt, REG[d["rt"]], text_of(a, d))
            if d["kind"] == "lw":
                out["abs_loads"].append(rec)
            elif d["rt"] != 0:
                out["abs_stores"].append(rec + (reg[d["rt"]],))

        # ── the heap-size subtraction: `subu rD, <stack-top>, <reserve>`. Identified by DATAFLOW —
        # both operands must trace to an absolute `lw` — which is what tells the stack-top word and
        # the reserve word apart from any OTHER absolute load in the function (e.g. this crt0's
        # `lw ra` reload of its own saved return address). Elimination could not do that.
        if (d["kind"] == "subu" and prov[d["rs"]] is not None and prov[d["rt"]] is not None
                and "_heapSubu" not in out):
            out["_heapSubu"] = (a, prov[d["rs"]], prov[d["rt"]])
            out["events"].append((a, "heap_size_subu",
                                  f"stackTop<-0x{prov[d['rs']]:08X}  reserve<-0x{prov[d['rt']]:08X}"))

        # ── the jals, with the arg regs live at the call (delay slot applied first) ────────────────
        if d["kind"] == "jal":
            ds = decode(exe.word(a + 4))
            apply(a + 4, ds)
            live = tuple(REG[r] for r in (4, 5, 6, 7) if reg[r] is not None)
            out["jals"].append((a, target(a, d), live, text_of(a, d), text_of(a + 4, ds)))
            out["events"].append((a, "jal", f"0x{target(a, d):08X} args={','.join(live) or '(none)'}"))
            a += 8
            n += 2
            continue

        apply(a, d)

        # lw of an absolute address inside .text: resolve it from the static image, and say so.
        if d["kind"] == "lw" and out["abs_loads"] and out["abs_loads"][-1][0] == a:
            tgt = out["abs_loads"][-1][1]
            try:
                reg[d["rt"]] = exe.word(tgt)
                prov[d["rt"]] = tgt
            except IndexError:
                reg[d["rt"]] = None
                prov[d["rt"]] = None

        if pending_loop_counter is not None and d["kind"] == "bne" and d["simm"] < 0:
            reg[pending_loop_counter] = None      # do not follow the loop; the counter is now unknown
            pending_loop_counter = None

        a += 4
        n += 1

    if "bssZeroLo" not in out:
        ev = "; ".join(f"{k}@0x{x:08X}" for x, k, _ in out["events"]) or "(no structural event at all)"
        raise Refused(f"0x{entry:08X} is not a crt0 by shape: walked {out['walked']} instructions, "
                      f"found NO .bss clear loop. Events seen: {ev}")

    # ── stack top: lw <abs>  [+ optional bias]  or sp,rD,0x80000000 ────────────────────────────────
    a2, n2 = entry, 0
    while n2 < limit:
        d = decode(exe.word(a2))
        if d["kind"] == "or" and d["rd"] == 29:                       # or sp, rD, rT
            src = d["rs"]
            bias, bias_at = 0, None
            base = None
            b, m = a2 - 4, 0
            while m < 8 and b >= entry:                               # walk back for the bias + the lw
                db = decode(exe.word(b))
                if db["kind"] in ("addi", "addiu") and db["rt"] == src and db["rs"] == src:
                    bias, bias_at = db["simm"], (b, text_of(b, db))
                if db["kind"] == "lw" and db["rt"] == src:
                    for (la, lt, _lr, ltxt) in out["abs_loads"]:
                        if la == b:
                            base, base_ev = lt, (b, ltxt)
                    break
                b -= 4
                m += 1
            if base is not None:
                out["stackTopBase"], out["stackTopBias"] = base, bias
                out["why"]["stackTopBase"] = base_ev
                out["why"]["stackTopBias"] = bias_at or (a2, "no bias instruction between the lw and "
                                                             "`or sp` — the bias is 0")
            break
        a2 += 4
        n2 += 1

    # ── heap base: the `sll 3` / `srl 3` KSEG0 mask of a constant ──────────────────────────────────
    a3, n3 = entry, 0
    while n3 < limit:
        d = decode(exe.word(a3))
        d2 = decode(exe.word(a3 + 4))
        if d["kind"] == "sll" and d["sa"] == 3 and d2["kind"] == "srl" and d2["sa"] == 3:
            b, m = a3 - 4, 0
            while m < 4 and b >= entry:
                db = decode(exe.word(b))
                if db["kind"] in ("addiu", "addi") and db["rt"] == d["rt"]:
                    dl = decode(exe.word(b - 4))
                    if dl["kind"] == "lui" and dl["rt"] == db["rs"]:
                        out["heapBase"] = ((dl["imm"] << 16) + db["simm"]) & 0xFFFFFFFF
                        out["why"]["heapBase"] = (b, f"{text_of(b - 4, dl)} ; {text_of(b, db)} "
                                                    f"-> 0x{out['heapBase']:08X}, then sll/srl 3 "
                                                    f"(mask to 0x1FFFFFFF)")
                    break
                b -= 4
                m += 1
            break
        a3 += 4
        n3 += 1

    # ── stackTopBase2: the RESERVE operand of the heap-size subtraction, by dataflow ───────────────
    out["stackTopBase2"] = None
    if "_heapSubu" in out:
        sa, st_from, res_from = out["_heapSubu"]
        out["stackTopBase2"] = res_from
        out["why"]["stackTopBase2"] = (sa, f"subu at 0x{sa:08X}: minuend traces to the lw of "
                                           f"0x{st_from:08X} (the stack top), subtrahend to the lw "
                                           f"of 0x{res_from:08X} (the reserve) — dataflow, not "
                                           f"elimination among the {len(out['abs_loads'])} abs loads")
        if out.get("stackTopBase") not in (None, st_from):
            out["why"]["stackTopBase2"] = (sa, f"DISAGREEMENT: the `or sp` chain names "
                                               f"0x{out['stackTopBase']:08X} as the stack-top load "
                                               f"but the heap subu's minuend traces to "
                                               f"0x{st_from:08X}. Not reconciled — inspect by hand.")
            out["stackTopBase2"] = None
    else:
        out["why"]["stackTopBase2"] = (0, f"absent — no `subu` in the {out['walked']} instructions "
                                          f"walked has BOTH operands traceable to an absolute load, "
                                          f"so this crt0 does not compute a heap size the framework's "
                                          f"way ({len(out['abs_loads'])} abs loads seen)")

    # ── gp ─────────────────────────────────────────────────────────────────────────────────────────
    a4, n4 = entry, 0
    while n4 < limit:
        d = decode(exe.word(a4))
        if d["kind"] in ("addiu", "addi") and d["rt"] == 28:
            dl = decode(exe.word(a4 - 4))
            if dl["kind"] == "lui" and dl["rt"] == d["rs"]:
                out["gp"] = ((dl["imm"] << 16) + d["simm"]) & 0xFFFFFFFF
                out["why"]["gp"] = (a4, f"{text_of(a4 - 4, dl)} ; {text_of(a4, d)}")
            break
        a4 += 4
        n4 += 1

    # ── heap globals: is the computed heap size / base STORED anywhere absolute? ────────────────────
    out["heapSizePtr"] = out["heapBasePtr"] = None
    for (sa, tgt, rname, txt, val) in out["abs_stores"]:
        if rname == "a1":
            out["heapSizePtr"] = tgt
            out["why"]["heapSizePtr"] = (sa, txt)
        elif rname == "a0":
            out["heapBasePtr"] = tgt
            out["why"]["heapBasePtr"] = (sa, txt)
    if out["heapSizePtr"] is None:
        out["why"]["heapSizePtr"] = (0, f"absent — none of the {len(out['abs_stores'])} recorded "
                                        f"absolute stores writes the computed heap SIZE register")
    if out["heapBasePtr"] is None:
        out["why"]["heapBasePtr"] = (0, f"absent — none of the {len(out['abs_stores'])} recorded "
                                        f"absolute stores writes the computed heap BASE register")

    # ── the two calls ──────────────────────────────────────────────────────────────────────────────
    if len(out["jals"]) >= 1:
        out["libcInit"], out["libcArgs"] = out["jals"][0][1], out["jals"][0][2]
        out["why"]["libcInit"] = (out["jals"][0][0], out["jals"][0][3] + "  ; delay: " + out["jals"][0][4])
    if len(out["jals"]) >= 2:
        out["gameMain"] = out["jals"][1][1]
        out["why"]["gameMain"] = (out["jals"][1][0], out["jals"][1][3])

    # ── derived boot state, so the group can be checked as a GROUP ────────────────────────────────
    try:
        st = exe.word(out["stackTopBase"])
        st2 = exe.word(out["stackTopBase2"]) if out.get("stackTopBase2") else None
        out["stackTopWord"], out["stackTopWord2"] = st, st2
        v0 = (st + out["stackTopBias"]) & 0xFFFFFFFF
        out["sp"] = v0 | 0x80000000
        if st2 is not None and "heapBase" in out:
            out["heapSize"] = (v0 - st2 - (out["heapBase"] & 0x1FFFFFFF)) & 0xFFFFFFFF
    except (IndexError, KeyError, TypeError):
        pass
    return out


# ── framework-compatibility verdict, DERIVED FROM THE PINNED FRAMEWORK'S OWN SOURCE ────────────────
# This used to be a hardcoded narrative: ten sentences, six always MATCHES and four always CONTRADICTS,
# quoting `native_boot.cpp:221/226/228` by line number. It never opened a framework file. So when the
# four defects were fixed upstream (psxport 726d10c9: the derivation moved into crt0_boot.h, the bias
# became a declared GameConfig field, the two heap stores became conditional, and `w.reg(5, p.a1)`
# landed), the verdict went on printing "INCOMPATIBLE (4 contradictions)" — a false negative that no
# amount of framework work could clear, and the selftest asserted it as a POSITIVE (">=3
# contradictions"), i.e. the gate required the framework to stay broken.
#
# It is now a scan of the framework source at $PSXPORT_DIR. Each mechanism the verdict depends on is
# located by its own pattern in a named file; a missing framework file is a REFUSAL, never "compatible".
# BLIND SPOT, and it is why the boot-time `crt0_audit` exists alongside this: locating a mechanism in
# the SOURCE TEXT is not running it. This says "the pinned framework has a declared-bias field and
# guards both heap stores", not "the boot produced sp = 0x80200000".
FW_FILES = {
    "crt0_boot.h":     os.path.join("runtime", "recomp", "crt0_boot.h"),
    "game_iface.h":    os.path.join("runtime", "recomp", "game_iface.h"),
    "native_boot.cpp": os.path.join("runtime", "recomp", "native_boot.cpp"),
}

# key -> (file, pattern, what having it licenses). Patterns run over COMMENT-STRIPPED text, because
# every one of these strings also appears in crt0_boot.h's prose describing the bug it fixed — matching
# a comment would let a framework that only DOCUMENTS the mechanism pass as having it.
FW_MECH = {
    "bss_loop":      ("crt0_boot.h", r"for\s*\(uint32_t\s+a\s*=\s*p\.bssLo;\s*a\s*<\s*p\.bssHi;\s*a\s*\+=\s*4\)"),
    "stacktop_read": ("native_boot.cpp", r"c->mem_r32\(cfg->stackTopBase\)"),
    "reserve_read":  ("native_boot.cpp", r"c->mem_r32\(cfg->stackTopBase2\)"),
    "heap_mask":     ("crt0_boot.h", r"cfg->heapBase\s*&\s*0x1FFFFFFFu"),
    "heap_arith":    ("crt0_boot.h", r"\(v0\s*-\s*stackReserveWord\)\s*-\s*a0m"),
    "gp_sp_fp":      ("crt0_boot.h", r"w\.reg\(29,\s*p\.sp\);\s*w\.reg\(30,\s*p\.sp\)"),
    "a0_plus4":      ("crt0_boot.h", r"\(a0m\s*\|\s*0x80000000u\)\s*\+\s*4u"),
    "bias_field":    ("game_iface.h", r"struct\s+Crt0StackBias\s*\{[^}]*\bdeclared\b[^}]*\}\s*stackBias"),
    "bias_required": ("crt0_boot.h", r'\{"stackBias\.declared",\s*cfg->stackBias\.declared\}'),
    "bias_used":     ("crt0_boot.h", r"bias\s*=\s*cfg->stackBias\.value"),
    "size_absent":   ("crt0_boot.h", r"p\.storeHeapSize\s*=\s*cfg->heapSizePtr\s*!=\s*0u"),
    "base_absent":   ("crt0_boot.h", r"p\.storeHeapBase\s*=\s*cfg->heapBasePtr\s*!=\s*0u"),
    "size_guarded":  ("crt0_boot.h", r"if\s*\(\s*p\.storeHeapSize\s*\)\s*(?:\{\s*)?w\.w32\(\s*p\.heapSizeAddr"),
    "base_guarded":  ("crt0_boot.h", r"if\s*\(\s*p\.storeHeapBase\s*\)\s*(?:\{\s*)?w\.w32\(\s*p\.heapBaseAddr"),
    "a1_set":        ("crt0_boot.h", r"w\.reg\(5,\s*p\.a1\)"),
}

BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def _strip_comments(s: str) -> str:
    return "\n".join(ln.split("//")[0] for ln in BLOCK_COMMENT_RE.sub("", s).splitlines())


def framework_source(psxport: str = PSXPORT) -> dict:
    """{filekey: comment-stripped text}. REFUSES on a missing file: a verdict computed over a framework
    it could not read would print MATCHES for mechanisms nobody located."""
    out = {}
    for key, rel in FW_FILES.items():
        p = os.path.join(psxport, rel)
        if not os.path.isfile(p):
            raise Refused(f"the framework source {p} does not exist — the crt0_setup compatibility "
                          f"verdict SCANNED NOTHING and is not reported. $PSXPORT_DIR = {psxport}; "
                          f"either the submodule is uninitialised (`git submodule update --init "
                          f"external/psxport`) or PSXPORT_DIR points somewhere that is not psxport.")
        out[key] = _strip_comments(open(p, encoding="utf-8").read())
    return out


def framework_mechanisms(src: dict) -> dict:
    """{key: (found, filekey, first matching line number or 0)} over ALL of FW_MECH — never a filtered
    list, so the denominator in the verdict is the full set every run."""
    mech = {}
    for key, (fk, pat) in FW_MECH.items():
        m = re.search(pat, src[fk])
        mech[key] = (m is not None, fk, src[fk][:m.start()].count("\n") + 1 if m else 0)
    return mech


def _cite(mech: dict, key: str) -> str:
    found, fk, ln = mech[key]
    return f"{fk}:{ln}" if found else f"{fk}: PATTERN NOT FOUND ({FW_MECH[key][1]})"


def framework_verdict(g: dict, mech: dict) -> tuple[list[str], list[str]]:
    """Which parts of psxport's generic crt0 derivation this crt0 matches, and which it contradicts.
    Every line cites the framework file and line the mechanism was located at (or says it was NOT)."""
    ok, bad = [], []

    def need(key: str, matched: str, contradicted: str):
        (ok if mech[key][0] else bad).append(
            f"[{_cite(mech, key)}] " + (matched if mech[key][0] else contradicted))

    need("bss_loop",
         f"bss clear: `for (a=p.bssLo; a<p.bssHi; a+=4) w.w32(a,0)` is EXACTLY this loop's semantics "
         f"([0x{g['bssZeroLo']:08X},0x{g['bssZeroHi']:08X}), store-then-increment, sltu unsigned bound)",
         "no word-stepped .bss clear loop over [bssLo,bssHi) — this crt0's clear loop has no counterpart")
    need("stacktop_read", "stack top comes from a MEMORY WORD, matching `c->mem_r32(cfg->stackTopBase)`",
         "the framework does not read the stack-top word from cfg->stackTopBase")
    need("reserve_read", "the stack reserve is read from cfg->stackTopBase2, as this crt0's second "
                        "absolute lw does",
         "the framework does not read a reserve word from cfg->stackTopBase2")
    need("heap_mask", "heap base is KSEG0-masked with 0x1FFFFFFF, matching `cfg->heapBase & 0x1FFFFFFFu`",
         "the framework does not KSEG0-mask heapBase, so a0 would keep its 0x8 nibble")
    need("heap_arith", "heap size is `(stackTop - mem[stackTopBase2]) - maskedHeapBase`, matching this "
                       f"crt0's two subu at 0x800DAEF8 exactly (0x{g.get('heapSize', 0):X})",
         "the framework's heap-size arithmetic is not (stackTop - reserve) - maskedBase")
    need("gp_sp_fp", "gp / sp / fp assignment (fp = sp) matches `w.reg(28,gp); w.reg(29/30, sp)`",
         "the framework does not set sp and fp to the same value")
    need("a0_plus4", "the libc-init callee is reached with a0 = maskedHeapBase|0x80000000 + 4, matching "
                     "this crt0's `addi a0,a0,4` in the jal's delay slot",
         "the framework does not pass maskedHeapBase|KSEG0 + 4 as a0")

    # ── the four that USED to be contradictions. Each is now a located mechanism or a real one again ──
    bias = g["stackTopBias"]
    if mech["bias_field"][0] and mech["bias_used"][0] and mech["bias_required"][0]:
        ok.append(f"[{_cite(mech, 'bias_used')}] the stack-top bias is a DECLARED GameConfig field "
                  f"(`stackBias.{{declared,value}}`, required by crt0_plan at "
                  f"{_cite(mech, 'bias_required')}), not a hardcoded -8 — so this crt0's measured bias "
                  f"of {bias} is expressible, and 0 does not read as 'unset'")
    elif bias == -8:
        ok.append(f"[{_cite(mech, 'bias_used')}] no declared-bias field, but this crt0's measured bias "
                  f"is -8, which is the stock PSY-Q value the framework assumes — compatible BY LUCK, "
                  f"not by design")
    else:
        bad.append(f"[{_cite(mech, 'bias_used')}] the framework has no declared stack-top bias "
                   f"(bias_field={mech['bias_field'][0]}, bias_used={mech['bias_used'][0]}, "
                   f"bias_required={mech['bias_required'][0]}), and this crt0's measured bias is {bias}: "
                   f"sp would come out 0x{(g['sp'] - 8) & 0xFFFFFFFF:08X} instead of 0x{g['sp']:08X} "
                   f"({8 - bias} bytes low), and the same 8 bytes shift the heap size")

    for what, absent_key, guard_key, field in (("SIZE", "size_absent", "size_guarded", "heapSizePtr"),
                                              ("BASE", "base_absent", "base_guarded", "heapBasePtr")):
        expressible = mech[absent_key][0] and mech[guard_key][0]
        if g[field] is None and not expressible:
            bad.append(f"[{_cite(mech, guard_key)}] the framework stores the heap {what} through "
                       f"cfg->{field} UNCONDITIONALLY ({absent_key}={mech[absent_key][0]}, "
                       f"{guard_key}={mech[guard_key][0]}), but this crt0 stores it NOWHERE — it passes "
                       f"it in a register. With the field left 0 the framework writes to guest "
                       f"address 0x00000000.")
        elif g[field] is None:
            ok.append(f"[{_cite(mech, guard_key)}] `{field} == 0` means ABSENT and the heap-{what.lower()} "
                      f"store is GUARDED on it, which is what this crt0 needs: its only absolute store "
                      f"is `sw ra`, so no heap global exists to write")
        else:
            ok.append(f"[{_cite(mech, guard_key)}] this crt0 DOES store the heap {what.lower()} at "
                      f"0x{g[field]:08X}, and the framework performs that store")

    if "a1" in g["libcArgs"]:
        need("a1_set",
             f"the libc-init callee 0x{g['libcInit']:08X} is called with a1 LIVE (= heap size "
             f"0x{g.get('heapSize', 0):X}), and the framework sets `w.reg(5, p.a1)` before dispatching "
             f"it — the BIOS A(39h) InitHeap(ptr,size) arena capacity",
             f"the libc-init callee 0x{g['libcInit']:08X} is called with a1 LIVE (= heap size "
             f"0x{g.get('heapSize', 0):X}), but the framework never assigns r[5] before dispatching it "
             f"— a1 would be whatever was left in the register file, so the heap would be initialised "
             f"with a garbage size")
    return ok, bad


def check(g: dict, expect: dict) -> list[str]:
    fails = []
    for k, v in expect.items():
        got = g.get(k, "MISSING")
        if got != v:
            sv = v if not isinstance(v, int) else f"0x{v:08X}"
            sg = got if not isinstance(got, int) else f"0x{got:08X}"
            fails.append(f"{k}: expected {sv}, derived {sg}")
    return fails


def fmt(v):
    return "absent" if v is None else (f"0x{v:08X}" if isinstance(v, int) else str(v))


def report(g: dict, exe_path: str, mech: dict) -> None:
    print(f";; {exe_path}")
    print(f";; entry (PS-EXE pc0) = 0x{g['entry']:08X}; walked {g['walked']} instructions to `break`")
    print()
    print("  MEASURED crt0 boot group — each field with the instruction that produced it:")
    for k in ("bssZeroLo", "bssZeroHi", "stackTopBase", "stackTopBias", "stackTopBase2", "heapBase",
              "heapSizePtr", "heapBasePtr", "gp", "libcInit", "gameMain"):
        v = g.get(k, "MISSING")
        wa, wt = g["why"].get(k, (0, "(no evidence recorded)"))
        loc = f"@0x{wa:08X}" if wa else "        "
        val = fmt(v) if k != "stackTopBias" else str(v)
        print(f"    {k:<14} {val:<12} {loc}  {wt}")
    print(f"    {'libcArgs':<14} {','.join(g.get('libcArgs', ())) or '(none)':<12}"
          f"            arg regs holding a resolved value at the first jal")
    print()
    print(f"  .bss size          = 0x{g['bssZeroHi'] - g['bssZeroLo']:X} "
          f"({g['bssZeroHi'] - g['bssZeroLo']:,} bytes)")
    if "sp" in g:
        print(f"  stack-top word     = mem[0x{g['stackTopBase']:08X}] = 0x{g['stackTopWord']:08X}"
              f"  -> sp = fp = 0x{g['sp']:08X}")
    if g.get("stackTopWord2") is not None:
        print(f"  reserve word       = mem[0x{g['stackTopBase2']:08X}] = 0x{g['stackTopWord2']:08X}")
    if "heapSize" in g:
        print(f"  heap               = [0x{g['heapBase']:08X}+4, size 0x{g['heapSize']:X} "
              f"= {g['heapSize']:,} bytes)")
    print()
    print(f"  ALL {len(g['abs_stores'])} absolute stores in this function "
          f"(this is the denominator behind 'stores no heap globals'):")
    for (sa, tgt, rname, txt, val) in g["abs_stores"] or []:
        print(f"    0x{sa:08X}  {txt:<28} -> 0x{tgt:08X}  (source reg {rname})")
    if not g["abs_stores"]:
        print("    (none — and the loop's `sw zero` is excluded by construction, it is the bss clear)")
    print(f"  ALL {len(g['abs_loads'])} absolute loads:")
    for (la, tgt, rname, txt) in g["abs_loads"]:
        print(f"    0x{la:08X}  {txt:<28} -> 0x{tgt:08X}  (into {rname})")
    print()
    ok, bad = framework_verdict(g, mech)
    nfound = sum(1 for f, _, _ in mech.values() if f)
    print(f"  psxport crt0 COMPATIBILITY — derived from the framework source at {PSXPORT}")
    print(f"    mechanisms located: {nfound} of {len(mech)} across {len(FW_FILES)} framework file(s)"
          + ("" if nfound == len(mech) else
             "; NOT FOUND: " + ", ".join(k for k, (f, _, _) in mech.items() if not f)))
    for s in ok:
        print(f"    MATCHES     {s}")
    for s in bad:
        print(f"    CONTRADICTS {s}")
    print(f"  verdict: {'COMPATIBLE' if not bad else f'INCOMPATIBLE ({len(bad)} contradictions)'} — "
          f"{len(ok)} of {len(ok) + len(bad)} checks match")
    print("  BLIND SPOT: this verdict is a scan of the framework's SOURCE TEXT, not a boot. It says the "
          "mechanisms exist, not that a run produced the right sp/heap — psxport's own crt0_audit "
          "(crt0_verify.h) is what checks that, at every boot.")


def load_exe(path: str):
    """Every way the corpus can fail to be a PS-X EXE routes through Refused — the ONE non-zero exit
    with a message that says what was scanned. Only the missing-PATH case used to; a 0-byte or garbage
    file died with an uncaught ValueError out of psexe.load, and a traceback is not a refusal: it has
    no denominator and no exit-code contract, so a caller cannot tell it from a crash in the analysis.
    Widening this is not an exception swallow — nothing is caught and continued, the failure is
    re-raised as the tool's own refusal with the file's size in it."""
    import psexe
    if not os.path.isfile(path):
        raise Refused(f"{path} does not exist — SCANNED NOTHING. Extract it first: "
                      f"`python3 tools/extract_exe.py` (see .env.example for the disc key).")
    try:
        return psexe.load(path)
    except (ValueError, struct.error) as e:
        raise Refused(f"{path} ({os.path.getsize(path)} bytes) is not a loadable PS-X EXE — SCANNED "
                      f"NOTHING of its code. psexe.load: {e}") from e
    except OSError as e:
        raise Refused(f"{path} could not be read — SCANNED NOTHING. {e}") from e


def selftest(cross: str | None) -> int:
    """Gate BOTH classes. Prints PASS/FAIL per case and the denominator of what it could not run."""
    results: list[tuple[str, bool, str]] = []

    # POSITIVE — the SHIPPING path: what game_config.cpp ships must equal what these bytes measure.
    # This is the same call `--check` makes, deliberately: a selftest over a helper beside the shipping
    # comparison is how the two-copies defect stayed invisible in the first place.
    try:
        exe = load_exe(DEFAULT_EXE)
        g = extract(exe, exe.entry)
        sh = parse_shipped()
        fwsrc = framework_source()
        mech = framework_mechanisms(fwsrc)
        sfails, slines = check_shipped(g, exe, sh, DEFAULT_EXE)
        results.append((f"positive: game_config.cpp's shipped constants == this run's measurement "
                        f"({len(slines)} comparisons)", not sfails,
                        f"{len(slines)} compared, 0 disagreements" if not sfails
                        else "; ".join(sfails)))
        fails = check(g, X4_SHAPE)
        results.append(("positive: the crt0 SHAPE facts with no shipping counterpart still hold "
                        f"({', '.join(X4_SHAPE)})", not fails,
                        f"all {len(X4_SHAPE)} hold" if not fails else "; ".join(fails)))
        # The pinned framework must be able to RUN this crt0. This assertion replaces ">=3
        # contradictions", which required the framework to stay broken and would have gone RED on the
        # upstream fix — the gate pointed the wrong way. It is claim C006's own stated falsifier.
        ok, bad = framework_verdict(g, mech)
        nfound = sum(1 for f, _, _ in mech.values() if f)
        results.append(("positive: the PINNED framework can run this crt0 — verdict COMPATIBLE, 0 "
                        "contradictions", not bad,
                        f"{nfound}/{len(mech)} mechanisms located, {len(ok)} matches, {len(bad)} "
                        f"contradictions" + ("" if not bad else ": " + " | ".join(bad))))
    except Refused as e:
        print(f"REFUSED: {e}")
        return 2

    # NEGATIVE 1 — mutation: flip the .bss-hi immediate. The extractor MUST report the mutated value
    # and the SHIPPED-vs-MEASURED comparison MUST fail, which is what proves the tool reads bytes.
    mut = bytearray(exe.text)
    off = 0x800DAE98 - exe.load                       # addiu v1, v1, 24376  (the bss upper bound)
    orig = struct.unpack_from("<I", mut, off)[0]
    struct.pack_into("<I", mut, off, (orig & 0xFFFF0000) | ((orig & 0xFFFF) ^ 0x0040))
    mexe = copy.copy(exe)
    mexe.text = bytes(mut)
    gm = extract(mexe, mexe.entry)
    shipped_hi = sh["consts"].get("kCrt0BssZeroHi")
    moved = gm.get("bssZeroHi") != shipped_hi
    mfails, _ = check_shipped(gm, mexe, sh)
    results.append(("negative: a flipped bss-bound immediate changes the derived bssZeroHi",
                    moved, f"derived 0x{gm.get('bssZeroHi', 0):08X} "
                           f"(game_config.cpp ships {fmt(shipped_hi)})"))
    results.append(("negative: the mutated image DISAGREES with the shipped constants",
                    bool(mfails), f"{len(mfails)} disagreement(s): {'; '.join(mfails) or 'NONE'}"))

    # NEGATIVE 2 — SABOTAGE THE SHIPPING FILE, the other half of the same comparison. A hand-edited
    # constant is the exact defect this tool was rebuilt to catch (kCrt0GameMain -> 0x80999999 once
    # passed every gate), so the sabotage is run here on a copy of the REAL file text, through the
    # REAL parser and the REAL comparison.
    for cname, poison, why in (("kCrt0GameMain", "0x80999999u", "a plausible-looking wrong address"),
                               ("kCrt0LibcInit", "0xDEADBEEFu", "an obvious sentinel"),
                               ("kPsExeTextAddr", "0x80020000u", "a header fact, not a crt0 field")):
        # (the cited-sha1 case is separate, below — it is not a `static constexpr`)
        real = open(sh["path"], encoding="utf-8").read()
        pat = re.compile(rf"(static\s+constexpr\s+uint32_t\s+{cname}\s*=\s*)([^;]+)(;)")
        if not pat.search(real):
            results.append((f"negative: a hand-edited {cname} is caught", False,
                            f"{cname} is not defined in {os.path.relpath(sh['path'], ROOT)} — the "
                            f"sabotage could not even be applied, so this case proves NOTHING"))
            continue
        bad_src = pat.sub(rf"\g<1>{poison}\g<3>", real, count=1)
        bfails, _ = check_shipped(g, exe, parse_shipped_src(bad_src, sh["path"]), DEFAULT_EXE)
        hit = any(cname in f for f in bfails)
        results.append((f"negative: a hand-edited {cname} = {poison} is caught ({why})", hit,
                        f"{len(bfails)} disagreement(s); "
                        + (next(f for f in bfails if cname in f) if hit
                           else "NONE names " + cname + " — the comparison does not cover it")))

    # NEGATIVE 2a — the actual first-substrate failure: a zero resident range makes every generated
    # main function unreachable even though rec_func_index contains it.
    real = open(sh["path"], encoding="utf-8").read()
    bad_range = re.sub(
        r"(\.recMainLo\s*=\s*)kPsExeTextAddr\s*&\s*0x1FFFFFFFu",
        r"\g<1>0",
        real,
        count=1,
    )
    rfails, _ = check_shipped(
        g, exe, parse_shipped_src(bad_range, sh["path"]), DEFAULT_EXE
    )
    hit = any("recMainLo" in failure for failure in rfails)
    results.append(
        (
            "negative: a zero resident recomp range is caught",
            hit,
            next(
                (failure for failure in rfails if "recMainLo" in failure),
                f"{len(rfails)} disagreement(s), none names recMainLo",
            ),
        )
    )

    # NEGATIVE 2b — a hand-edited CITED SHA1: the file's claim about WHICH image these constants were
    # measured from is itself a shipped measurement, so it is gated the same way.
    real = open(sh["path"], encoding="utf-8").read()
    m_sha = SHA1_RE.search(real)
    if not m_sha:
        results.append(("negative: a hand-edited cited sha1 is caught", False,
                        "the shipping file cites NO sha1, so this case proves NOTHING"))
    else:
        poisoned = real.replace(m_sha.group(0), "0" * 39 + "1")
        pfails, _ = check_shipped(g, exe, parse_shipped_src(poisoned, sh["path"]), DEFAULT_EXE)
        hit = any("cites sha1" in f for f in pfails)
        results.append(("negative: a hand-edited cited sha1 is caught", hit,
                        (next(f for f in pfails if "cites sha1" in f)[:190] if hit
                         else f"{len(pfails)} disagreement(s), none about the sha1")))

    # NEGATIVE 3 — a sabotaged STRUCT. Every one of these edits a copy of the REAL initialiser text and
    # runs the REAL comparison. `expect` is the substring the failure must contain, so a case cannot
    # pass by going red for an unrelated reason — which is exactly how the partial-group bug hid: the
    # correct config went red, and "it failed" read as "the gate works".
    #
    #   * the HALF-filled required group is still red (the state that looks like progress);
    #   * BUT the two OPTIONAL fields at 0 must NOT count toward that, which is the positive direction
    #     of the same check and is asserted by the top-level positive case above;
    #   * an INVENTED address for an absent global is red;
    #   * a store the guest DOES make, shipped as 0, is red (the opposite direction);
    #   * an undeclared or wrong stack bias is red — that field had NO gate before.
    real = open(sh["path"], encoding="utf-8").read()
    struct_cases = [
        ("a HALF-filled required crt0 group",
         r"\.bssZeroLo\s*=\s*kCrt0BssZeroLo\s*,\s*\.bssZeroHi\s*=\s*kCrt0BssZeroHi\s*,",
         ".bssZeroLo = 0, .bssZeroHi = 0,", "PARTIALLY filled"),
        ("an INVENTED heapSizePtr for a global this crt0 does not have",
         r"\.heapSizePtr\s*=\s*0\s*,\s*\.heapBasePtr\s*=\s*0\s*,",
         ".heapSizePtr = kCrt0HeapBase, .heapBasePtr = 0,", "stores heapSizePtr NOWHERE"),
        ("an UNDECLARED stack bias (crt0_plan would refuse the boot)",
         r"\.stackBias\s*=\s*\{\s*1\s*,\s*kCrt0StackBias\s*\}\s*,",
         ".stackBias = {0, kCrt0StackBias},", "declared = 0"),
        ("a stack bias of -8, the value four other ports measure",
         r"(kCrt0StackBias\s*=\s*)0(\s*;)", r"\g<1>-8\g<2>", "measured a stack-top bias of 0"),
        # A bare literal in the struct is NOT itself a hole — the token is evaluated and diffed against
        # the measurement either way, which this case proves by shipping a bare WRONG one. What IS a
        # hole is deleting the constant: the value then has no citation anchoring it to the
        # disassembly, and that is the case below it.
        ("a bare-literal stack bias with the WRONG value",
         r"\.stackBias\s*=\s*\{\s*1\s*,\s*kCrt0StackBias\s*\}\s*,",
         ".stackBias = {1, -8},",
         "but this run measured a bias of 0"),
        ("kCrt0StackBias deleted, leaving the bias uncitable",
         r"static\s+constexpr\s+int32_t\s+kCrt0StackBias\s*=\s*0\s*;\s*", "",
         "shipped as a bare literal"),
    ]
    for label, pattern, replacement, expect in struct_cases:
        if not re.search(pattern, real):
            results.append((f"negative: {label} is caught", False,
                            f"the text this case edits ({pattern!r}) was NOT FOUND in "
                            f"{os.path.relpath(sh['path'], ROOT)} — case proves NOTHING"))
            continue
        sabotaged = re.sub(pattern, replacement, real, count=1)
        sfx, _ = check_shipped(g, exe, parse_shipped_src(sabotaged, sh["path"]))
        hit = any(expect in f for f in sfx)
        results.append((f"negative: {label} is caught", hit,
                        (next(f for f in sfx if expect in f)[:200] if hit else
                         f"{len(sfx)} disagreement(s), NONE containing {expect!r}: "
                         + ("; ".join(sfx)[:200] or "NONE AT ALL"))))

    # NEGATIVE 3b — the OTHER direction of the optional pair: a crt0 that DOES store the heap size,
    # against a config that says ABSENT. The framework would then skip a store the guest makes. Driven
    # by a measurement dict with that one field set, because X4's own bytes cannot produce this case —
    # the genuine cross-game form of it runs below when --cross is supplied.
    g_present = dict(g)
    g_present["heapSizePtr"] = 0x800ABEF8
    pfails, _ = check_shipped(g_present, exe, sh, DEFAULT_EXE)
    hit = any("DOES store heapSizePtr" in f for f in pfails)
    results.append(("negative: a crt0 that DOES store the heap size, against .heapSizePtr = 0", hit,
                    (next(f for f in pfails if "DOES store heapSizePtr" in f)[:200] if hit
                     else f"{len(pfails)} disagreement(s), none about a skipped store")))

    # NEGATIVE 3c — SABOTAGE THE FRAMEWORK SOURCE. The verdict is a scan of psxport's own text now, so
    # the way to prove it is not a hardcoded "COMPATIBLE" is to remove the mechanisms from a copy of
    # that text and require the contradictions to come back. Each of the four upstream fixes is deleted
    # in turn, and the case names the mechanism it deleted.
    for key, frm, to, expect in (
            ("size_guarded", r"if\s*\(\s*p\.storeHeapSize\s*\)", "if (true)",
             "heap SIZE through cfg->heapSizePtr UNCONDITIONALLY"),
            ("base_guarded", r"if\s*\(\s*p\.storeHeapBase\s*\)", "if (true)",
             "heap BASE through cfg->heapBasePtr UNCONDITIONALLY"),
            ("a1_set", r"w\.reg\(5,\s*p\.a1\)", "w.reg(6, p.a1)", "never assigns r[5]"),
            ("bias_used", r"bias\s*=\s*cfg->stackBias\.value", "bias = -8",
             "no declared stack-top bias")):
        doctored = dict(fwsrc)
        if not re.search(frm, doctored["crt0_boot.h"]):
            results.append((f"negative: deleting the framework's {key} brings the contradiction back",
                            False, f"{frm!r} not found in the pinned crt0_boot.h — case proves NOTHING"))
            continue
        doctored["crt0_boot.h"] = re.sub(frm, to, doctored["crt0_boot.h"], count=1)
        _, dbad = framework_verdict(g, framework_mechanisms(doctored))
        hit = any(expect in s for s in dbad)
        results.append((f"negative: deleting the framework's {key} brings the contradiction back", hit,
                        (next(s for s in dbad if expect in s)[:200] if hit
                         else f"{len(dbad)} contradiction(s), none containing {expect!r}")))

    # NEGATIVE 3d — a framework we cannot READ must REFUSE, not report COMPATIBLE over zero files.
    try:
        framework_source(os.path.join(ROOT, "scratch", "raw", "__NO_SUCH_PSXPORT__"))
        results.append(("negative: an unreadable framework tree refuses the verdict", False,
                        "it returned a source dict for a directory that does not exist"))
    except Refused as e:
        results.append(("negative: an unreadable framework tree refuses the verdict", True, str(e)[:150]))

    # NEGATIVE 4 — wrong entry: main() must be REFUSED, not partially parsed into a plausible group.
    try:
        extract(exe, g["gameMain"])
        results.append(("negative: main() is refused as 'not a crt0'", False,
                        "it returned a group instead of refusing — the shape assert is too weak"))
    except Refused as e:
        results.append(("negative: main() is refused as 'not a crt0'", True, str(e)[:150]))

    # NEGATIVE 5 — a MALFORMED corpus must refuse, not raise. Three shapes, because only the first
    # used to be handled: a missing path, a 0-byte file, and a file full of the wrong bytes. The last
    # two died with an uncaught ValueError from psexe.load, which has no exit-code contract.
    sd = os.path.join(ROOT, "scratch", "raw")
    os.makedirs(sd, exist_ok=True)
    zero_p, junk_p = os.path.join(sd, "selftest_zero.bin"), os.path.join(sd, "selftest_junk.bin")
    open(zero_p, "wb").close()
    with open(junk_p, "wb") as f:
        f.write(b"NOT-AN-EXE" + bytes(range(256)) * 8)
    for label, p in (("a MISSING path", os.path.join(sd, "__NO_SUCH_EXE__")),
                     ("a 0-BYTE file", zero_p),
                     ("a GARBAGE file", junk_p)):
        try:
            load_exe(p)
            results.append((f"negative: {label} refuses", False,
                            "it returned an exe object instead of refusing"))
        except Refused as e:
            results.append((f"negative: {label} refuses", True, str(e)[:130]))
        except Exception as e:            # noqa: BLE001 — the POINT of the case
            results.append((f"negative: {label} refuses", False,
                            f"it raised {type(e).__name__} instead of Refused: {e}"))
    for p in (zero_p, junk_p):
        os.remove(p)

    # NEGATIVE 4 (cross-game) — a DIFFERENT crt0 must yield a DIFFERENT shape. Skipped loudly.
    if cross and os.path.isfile(cross):
        try:
            cexe = load_exe(cross)
            gc = extract(cexe, cexe.entry)
            differs = (gc.get("stackTopBias") != g["stackTopBias"]
                       or (gc.get("heapSizePtr") is None) != (g["heapSizePtr"] is None)
                       or gc.get("bssZeroLo") != g["bssZeroLo"])
            ok2, bad2 = framework_verdict(gc, mech)
            results.append((f"negative: {os.path.basename(cross)} yields a DIFFERENT crt0 shape",
                            differs,
                            f"bias {gc.get('stackTopBias')} vs {g['stackTopBias']}; "
                            f"heapSizePtr {fmt(gc.get('heapSizePtr'))} vs {fmt(g['heapSizePtr'])}; "
                            f"bss 0x{gc.get('bssZeroLo', 0):08X} vs 0x{g['bssZeroLo']:08X}; "
                            f"verdict {'COMPATIBLE' if not bad2 else f'INCOMPATIBLE({len(bad2)})'}"))
            # POSITIVE CONTROL: does it reproduce the eleven values Tomba2Engine recorded by hand?
            if gc.get("entry") == TOMBA2_CONTROL["entry"]:
                cf = check(gc, TOMBA2_CONTROL)
                results.append(("positive control: the extractor reproduces all "
                                f"{len(TOMBA2_CONTROL)} of Tomba!2's independently hand-recorded "
                                "boot-group values", not cf,
                                f"{len(TOMBA2_CONTROL) - len(cf)}/{len(TOMBA2_CONTROL)} match"
                                + ("" if not cf else "; MISMATCH: " + "; ".join(cf))))
            else:
                results.append(("positive control: Tomba!2 hand-recorded values", False,
                                f"--cross exe entry is 0x{gc.get('entry', 0):08X}, not Tomba!2's "
                                f"0x{TOMBA2_CONTROL['entry']:08X} — the control could not run, so "
                                "pass a different --cross or drop it"))
            # The GENUINE present-vs-absent mismatch, from a real second binary rather than a
            # synthesized measurement: Tomba!2's crt0 DOES store both heap globals, so measuring IT
            # against X4's shipping file (which correctly says ABSENT) must go red in that direction.
            xfails, _ = check_shipped(gc, cexe, sh)
            hit = any("DOES store heapSizePtr" in f for f in xfails)
            results.append(("negative: a REAL crt0 with heap globals, against this port's ABSENT "
                            "config", hit,
                            (next(f for f in xfails if "DOES store heapSizePtr" in f)[:200] if hit
                             else f"{len(xfails)} disagreement(s), none about a skipped store — "
                                  f"{os.path.basename(cross)} measured heapSizePtr "
                                  f"{fmt(gc.get('heapSizePtr'))}")))
        except Refused as e:
            results.append((f"negative: cross-game {cross}", False, f"refused: {e}"))
    else:
        print(f"NOTE: the cross-game negative did NOT RUN — --cross "
              f"{cross or '<not supplied>'} is not a readable file. 4 of 5 case groups below; the "
              f"extractor is still gated by the mutation negative, which is self-contained.")

    print()
    npass = sum(1 for _, p, _ in results if p)
    for name, p, detail in results:
        print(f"  [{'PASS' if p else 'FAIL'}] {name}\n         {detail}")
    print(f"\n  {npass}/{len(results)} cases passed "
          f"({sum(1 for n, _, _ in results if n.startswith('positive'))} positive, "
          f"{sum(1 for n, _, _ in results if n.startswith('negative'))} negative)")
    return 0 if npass == len(results) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=DEFAULT_EXE, help="PS-X EXE to read (default: the extracted X4)")
    ap.add_argument("--entry", default=None, help="override the entry PC (hex); default = header pc0")
    ap.add_argument("--check", action="store_true",
                    help="diff game/core/game_config.cpp's SHIPPED constants against what this run "
                         "measured from the bytes (the only comparison that gates the shipped value)")
    ap.add_argument("--shipped", default=SHIPPED_FILE,
                    help="the shipping file to diff against (default: game/core/game_config.cpp)")
    ap.add_argument("--cross", default=None, help="a SECOND game's PS-X EXE, for the cross-game negative")
    ap.add_argument("--selftest", action="store_true", help="gate both classes; exit 1 on regression")
    a = ap.parse_args()

    if a.selftest:
        try:
            return selftest(a.cross)
        except Refused as e:
            print(f"REFUSED (exit 2): {e}")
            return 2

    try:
        exe = load_exe(a.exe)
        entry = int(a.entry, 16) if a.entry else exe.entry
        g = extract(exe, entry)
        mech = framework_mechanisms(framework_source())
    except Refused as e:
        print(f"REFUSED (exit 2): {e}")
        return 2
    report(g, a.exe, mech)
    if a.check:
        try:
            sh = parse_shipped(a.shipped)
        except Refused as e:
            print(f"\nREFUSED (exit 2): {e}")
            return 2
        fails, lines = check_shipped(g, exe, sh, a.exe)
        shape = check(g, X4_SHAPE)
        print()
        print(f"  SHIPPED vs MEASURED — {os.path.relpath(sh['path'], ROOT)} against these bytes:")
        for ln in lines:
            print(ln)
        for s in shape:
            print(f"    BAD shape fact (no shipping counterpart): {s}")
        if not shape:
            print(f"    ok  {'shape facts':<20} " +
                  ", ".join(f"{k}={X4_SHAPE[k]}" for k in X4_SHAPE) + " (no GameConfig field exists "
                  "for these — see X4_SHAPE)")
        print()
        if fails or shape:
            print(f"  CHECK FAILED: {len(fails) + len(shape)} disagreement(s) between the SHIPPED "
                  f"values and this run's measurement:")
            for f in fails + shape:
                print(f"    {f}")
            print("    One of the two is wrong. The measurement wins over a hand-edit; if the bytes "
                  "changed, this is not the same executable.")
            return 1
        print(f"  CHECK PASSED: {len(lines)} shipped-vs-measured comparisons agree, and "
              f"{len(X4_SHAPE)} shape fact(s) hold. There is no second copy of these values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
