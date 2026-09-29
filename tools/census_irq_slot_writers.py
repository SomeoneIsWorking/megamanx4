#!/usr/bin/env python3
"""census_irq_slot_writers.py — who can write the libetc SetInterrupt class-0 slot, from bytes.

    python3 tools/census_irq_slot_writers.py --check
    python3 tools/census_irq_slot_writers.py --selftest

WHY THIS EXISTS. docs/issues/0035 and docs/re-frontier.md (RE-10 gap) recorded the run's stop as
"the class-0 interrupt table entry at 0x8011CB98 holds the non-guest word 0x0113D7D0". That claim is
a MISREAD, and this tool exists so the next session does not re-derive it or build a fix on it:
0x0113D7D0 is not the slot's CONTENTS. It is the guest PC of a control transfer to an address no
code image claims, read out of the dispatcher's own fault line. A store observer armed on
[0x8011CB98,0x8011CB9C) for a whole real-disc run saw SIX stores, and the word held at the moment
of the fault was 0x800DD7FC — libsnd's SS-tick handler, the value libsnd's SsStart installs
(docs/issues/0015). A counter that reads a plausible corruption is worth less than a census of the
writers, which is what this is.

WHAT IT CLOSES, with the class each class belongs to:

  A. DIRECT stores — one backward walk per `sb`/`sh`/`sw` (12 instructions, straight-line only)
     tracking the base register through `lui`/`ori`/`addiu`/`addu` and through a load of an image
     word. $gp/$sp/$fp are seeded with what the port's NATIVE crt0 sets (psxport
     runtime/psx/native_boot.cpp, transcribed in game/core/game_config.cpp): gp=0x8012F418,
     sp=fp=0x80200000. A base the walk cannot resolve is COUNTED, never assumed harmless.
  B. POINTER-TABLE class — image words that are themselves a pointer into the window, which is the
     only way a store through a loaded pointer could aim at it.
  C. DMA — guest stores into a MADR cell (0x1F801080 + 4*channel), the only way a channel is aimed
     at a RAM destination at all.

BLIND SPOTS, STATED BECAUSE THEY ARE THE POINT. A base register whose value was produced more than
12 instructions earlier, by a computation this walk does not model, or by a host-side write, is
outside A — and the real writers of this slot ARE outside it, because they are parameter-driven:
FUN_800E53F0 (SetInterrupt) stores its callback argument at 0x8011CB98 + 4*class, and the BIOS IRQ
init stores the boot handler. That is why the AUTHORITY for "what actually wrote this word" is the
runtime store observation, and this tool is the corroborating static class list, not a replacement.

`--selftest` plants a direct store into the window in a copy of the image, plants an image word
that is a pointer into the window, and plants a third MADR store, and requires every one to be
caught — so a zero here is a measurement and not a census that never looked.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXE = ROOT / "scratch" / "bin" / "megamanx4" / "SLUS_005.61"
PSX_EXE_HEADER = 0x800

WINDOW_LO, WINDOW_HI = 0x8011CB98, 0x8011CB9C
WINDOW_BACK = 12                                   # backward walk length, in instructions
MADR_BASE, MADR_END = 0x1F801080, 0x1F8010A0
# game/core/game_config.cpp: the native crt0 transcription. sp/fp are 0x80200000 with NO bias.
HOST_SEED = {28: {0x8012F418}, 29: {0x80200000}, 30: {0x80200000}}

STORE_SIZE = {0x28: 1, 0x29: 2, 0x2B: 4}           # sb, sh, sw
BRANCH = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07}


class Image:
    """The authenticated executable's loaded segment, read the way the GUEST reads it (little-endian)."""

    def __init__(self, data: bytes) -> None:
        _, _, text_address, text_bytes = struct.unpack_from("<11I", data, 0x10)[:4]
        self.address = text_address
        self.text = bytearray(data[PSX_EXE_HEADER:PSX_EXE_HEADER + text_bytes])
        self.words = list(struct.unpack_from(f"<{text_bytes // 4}I", self.text, 0))

    def word(self, address: int) -> int:
        return self.words[(address - self.address) // 4]

    def poke(self, address: int, value: int) -> None:
        """Plant a word. A --selftest that mutates a COPY is the only thing that makes a zero from
        this census a measurement, so the copy must be genuinely writable."""
        self.words[(address - self.address) // 4] = value & 0xFFFFFFFF


def op(w): return w >> 26
def rs(w): return (w >> 21) & 0x1F
def rt(w): return (w >> 16) & 0x1F
def rd(w): return (w >> 11) & 0x1F
def imm(w): return w & 0xFFFF
def funct(w): return w & 0x3F


def simm(w: int) -> int:
    i = w & 0xFFFF
    return i - 0x10000 if i & 0x8000 else i


def defines(w: int) -> set[int]:
    o = op(w)
    if o in (0x09, 0x0D, 0x0F, 0x20, 0x21, 0x23, 0x24, 0x25, 0x2E, 0x30, 0x31, 0x33, 0x35):
        return {rt(w)}
    if o == 0x00:
        return {rd(w), rt(w)}
    if o == 0x01 or o in (0x2F, 0x3F):
        return {rt(w)} if o == 0x01 else {rd(w)}
    return set()


class Census:
    def __init__(self, image: Image) -> None:
        self.image = image
        self.direct: list[tuple[int, int, int, int, int]] = []
        self.unresolved = 0
        self.stores = 0

    def backward(self, index: int, reg: int) -> set[int]:
        if reg in HOST_SEED:
            return set(HOST_SEED[reg])
        for back in range(1, WINDOW_BACK + 1):
            j = index - back
            if j < 0:
                break
            w = self.image.words[j]
            if op(w) in BRANCH:
                break
            if reg not in defines(w):
                continue
            o = op(w)
            if o == 0x0F and rt(w) == reg:
                return {imm(w) << 16}
            if o in (0x0D, 0x09) and rt(w) == reg and rs(w) == reg:
                src = self.backward(j, rs(w))
                if o == 0x0D:
                    return {(v | imm(w)) & 0xFFFFFFFF for v in src}
                return {(v + simm(w)) & 0xFFFFFFFF for v in src}
            if o == 0x09 and rt(w) == reg:
                return {(v + simm(w)) & 0xFFFFFFFF for v in self.backward(j, rs(w))}
            if o == 0x00 and funct(w) == 0x21 and rd(w) == reg:
                return self.backward(j, rs(w)) | self.backward(j, rt(w))
            if o == 0x23 and rt(w) == reg:            # lw: the value is the IMAGE WORD it reads
                out = set()
                for v in self.backward(j, rs(w)):
                    if self.image.address <= v < self.image.address + 4 * len(self.image.words) \
                            and (v - self.image.address) % 4 == 0:
                        out.add(self.image.word(v))
                return out
            return set()                              # a def this walk does not model
        return set()

    def run(self) -> None:
        for i, w in enumerate(self.image.words):
            if op(w) not in STORE_SIZE:
                continue
            self.stores += 1
            values = self.backward(i, rs(w))
            if not values:
                self.unresolved += 1
                continue
            for v in values:
                a = (v + simm(w)) & 0xFFFFFFFF
                if a < WINDOW_HI and a + STORE_SIZE[op(w)] > WINDOW_LO:
                    self.direct.append((self.image.address + 4 * i, w, STORE_SIZE[op(w)], rs(w), a))
        self.direct = sorted(set(self.direct))

    def pointer_words(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for i, v in enumerate(self.image.words):
            if WINDOW_LO <= v < WINDOW_HI:
                out.setdefault(v, []).append(self.image.address + 4 * i)
        return out

    def madr_stores(self) -> list[tuple[int, int, int]]:
        out = set()
        for i, w in enumerate(self.image.words):
            if op(w) not in STORE_SIZE:
                continue
            for v in self.backward(i, rs(w)):
                a = v + simm(w)
                if MADR_BASE <= a < MADR_END:
                    out.add((self.image.address + 4 * i, w, (a - MADR_BASE) // 4))
        return sorted(out)


def check(exe: Path) -> list[str]:
    census = Census(Image(exe.read_bytes()))
    census.run()
    pointers = census.pointer_words()
    madr = census.madr_stores()
    notes = [
        "scanned %d words in [0x%08X,0x%08X); %d sb/sh/sw sites; backward window %d instructions"
        % (len(census.image.words), census.image.address,
           census.image.address + 4 * len(census.image.words), census.stores, WINDOW_BACK),
        "class A direct stores that can land in [0x%08X,0x%08X): %d"
        % (WINDOW_LO, WINDOW_HI, len(census.direct)),
        "class A stores whose base this walk could not resolve (reported, not assumed safe): "
        "%d of %d" % (census.unresolved, census.stores),
        "class B image words that ARE a pointer into the window: %d value(s) at %d site(s)"
        % (len(pointers), sum(len(v) for v in pointers.values())),
        "class C guest stores into a DMA MADR cell: %d" % len(madr),
    ]
    for address, w, size, base, a in census.direct:
        notes.append("  A %08X word=%08X size=%d base=$%d -> %08X" % (address, w, size, base, a))
    for v, sites in sorted(pointers.items()):
        notes.append("  B %08X at %s" % (v, " ".join("%08X" % s for s in sites[:8])))
    for address, w, channel in madr:
        notes.append("  C %08X word=%08X -> MADR channel %d" % (address, w, channel))
    notes.append(
        "The real writers of this slot are PARAMETER-driven and therefore outside class A: "
        "FUN_800E53F0 (SetInterrupt) stores its callback argument at 0x8011CB98 + 4*class, and the "
        "BIOS IRQ init stores the boot handler 0x800E56FC. A runtime store observation is the "
        "authority for what actually wrote the word; this is the corroborating static class list.")
    return notes


def selftest(exe: Path) -> list[str]:
    """Every mutation must be caught; a zero from a census that never looked is not a result."""
    # $6 is $a2: the plant is `lui $a2,H / ori $a2,$a2,L / sw $a2,0($a2)`, i.e. 0xACC60000 at the store.
    # Each mutation is a PLANTED INSTRUCTION SEQUENCE, not a bare data word: a store only reaches
    # the window if its base register's chain is modelled, so a single poked word would be caught
    # by class B alone and would prove nothing about class A.
    cases = [
        ("plant lui/ori/sw whose base lands in the window", "A",
         [(0x80123400, 0x3C068011), (0x80123404, 0x34C6CB98), (0x80123408, 0xACC60000)]),
        ("plant an image word that is a pointer into the window", "B",
         [(0x80123410, WINDOW_LO)]),
        ("plant a third MADR store (lui/ori/sw -> 0x1F801088)", "C",
         [(0x80123420, 0x3C061F80), (0x80123424, 0x34C61088), (0x80123428, 0xACC60000)]),
    ]
    notes = []
    for name, expect, plants in cases:
        image = Image(exe.read_bytes())
        census = Census(image)
        census.run()
        base = {"A": len(census.direct), "B": len(census.pointer_words()),
                "C": len(census.madr_stores())}[expect]
        for site, value in plants:
            image.poke(site, value)
        mutated = Census(image)
        mutated.run()
        caught = {"A": len(mutated.direct) > base,
                  "B": len(mutated.pointer_words()) > base,
                  "C": len(mutated.madr_stores()) > base}[expect]
        notes.append("%s: %s" % (name, "CAUGHT" if caught else "MISSED"))
        if not caught:
            raise SystemExit("selftest FAILED: %s was not caught" % name)
    notes.append("%d of %d mutations caught" % (len(cases), len(cases)))
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if not args.exe.is_file():
        print("REFUSED: %s does not exist. Provision the authenticated image first "
              "(tools/extract_exe.py). This gate refuses to report a clean zero without one."
              % args.exe)
        return 2
    if args.selftest:
        for line in selftest(args.exe):
            print(line)
    if args.check or not args.selftest:
        for line in check(args.exe):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
