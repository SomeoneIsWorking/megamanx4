---
id: 7
title: A PS-X EXE is sector-padded, and a J-type target is not PC-relative
status: open
symptom: Disassembly of a PS-X EXE yields plausible guest addresses that are all wrong
state_items: S002
tags: megamanx4,re,tooling,disassembly
created: 2026-09-29
updated: 2026-09-29
---

## Two traps, both of which produce confident nonsense

### 1. The text is loaded from file offset 0x800, not from the start of the file

A PS-X EXE has its 2048-byte header at offset 0 and its text at **`t_addr`**, read from **file offset
`0x800`**. For `SLUS_005.61` the header says:

    magic   PS-X EXE
    pc0     0x800DAE8C
    t_addr  0x80010000
    t_size  0x0011F800

So file offset `0x800` holds the first text word and file offset `0x10000` is **address
`0x80021800`**, not `0x80010000`. Mapping the file as though it began at `t_addr` puts everything
`0xF800` bytes too high, and the result is not an obvious failure: the region that should hold the
faulting call instead holds an **ASCII attribution string**, which a disassembler reports as a mixture
of `UNKNOWN` and nonsense `jalx`, and which reads convincingly like "this image is not code here".

That is exactly what happened here, and it nearly produced a correction to a correct record. The
reason it was caught is that the framework's disassembler **refuses** a run with undecoded words
(`scanned 16/16; decoded 10/16; unknown 6; REFUSED incomplete decode`) instead of printing text
anyway. A tool that reports incomplete coverage as a failure is what turns a silent misalignment into
a loud one.

**The rule:** build the dump as `dump[t_addr - 0x80000000 ...] = file[0x800 ...]`, and print the first
word at `file[0x800]` before trusting anything. At `file[0x800]` a real image shows `lui`/`ori` pairs
building its own addresses; a misaligned one shows text.

### 2. A J-type target is NOT PC-relative, and the error is a plausible address

The MIPS rule is

    target = (PC + 4) & 0xF0000000 | (imm26 << 2)

Reading the 26-bit field as an offset **from the current PC** adds a PC offset the encoding has
already accounted for. In `SLUS_005.61` that produced five wrong call targets out of seven, and
**all five followed one rule exactly**:

    wrong == right + (delay_slot_address & 0x0FFFFFFF)

so the damage was a constant per site, not noise. Verified for every wrong entry, no exceptions.

**Why this is worth an issue rather than a footnote:** every wrong number is a plausible guest
address in the right neighbourhood — `0x8002xxxx` for a function that is really at `0x8001xxxx`. A
listing of seven consistent-looking addresses invites a reader to check the shape rather than the
arithmetic, and the two entries that *were* right are the two whose true target crosses a 256 MB
page, where the error would have been obvious. **A wrong value that looks like the right kind of
thing outlives a wrong value that does not.**

## The tool that already answers this

`psxport/tools/disasm.py` — Capstone MIPS32, a locked dependency, gated by
`psxport/tests/test_disasm.py`:

    uv run --frozen python tools/disasm.py RAM_DUMP 800120D8 80012118

It takes an **exact 2 MiB RAM dump** (not the EXE) and a half-open address range, prints a
scanned/decoded denominator, reports each undecodable word with its raw bits as `UNKNOWN`, and exits
nonzero on incomplete coverage.

**It is a diagnostic, not a validity oracle**, and its own documentation says so: some legitimate
PSX COP2/GTE encodings are unsupported, and an `UNKNOWN` is not proof that code is absent. That
distinction matters in both directions — it is why this issue's correction was confirmed by hand for
one entry (`0x800120EC` = `0x0C0051E0` → `op 3`, `imm26 0x000051E0`, `<<2 = 0x00014780`, page
`0x80000000` → **`0x80014780`**) rather than resting on the tool alone.

## What this corrects elsewhere

The workspace map stated that `llvm-objdump --triple=mips` "misdecodes `SLUS_005.61`". **It does not
misdecode it; it refuses it** — *"The file was not recognized as a valid object file"* — because it
wants an object file or a recognised container, not a PS-X EXE. Under the framework's tool the same
range decodes 16 of 16 with zero unknown. The map's claim has been corrected, and so has the listing
in `megamanx4/docs/issues/0036` that the claim had been used to justify hand-decoding.
