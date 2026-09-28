---
id: 0033
title: The guest has no 8-entry bound on the VRAM-rect array at all — "8 entries" is the observer's inference, not a fact from the image
status: open
symptom: issue 0032 recorded the fatal `0x26010006` read as "a data word at `0x8010C3F0`" whose
  writer is `0x80015FE0 sw $a1,0x1F68($at)`, described the array as "**eight**-entry", and left open
  whether retail's own per-field count is also 9. The eight is load-bearing for calling this a port
  defect, and it is not in the image.
state_items: S004
tags: fault,stage-load,mmx4,decomp,bytes,array-bound
created: 2026-09-28
updated: 2026-09-28
---

## The question, and why it is decidable statically

Issue 0032 could not say "which instruction advances `0x80141F68` past the array end" because
`PSXPORT_WWATCH` cannot answer it — and that same work established **why**, which is a real result:
`PSXPORT_WWATCH`'s `pc` and `ra` are the last executor *segment* boundary, not the store's site, and
it matches only on a store's **start** address. So the runtime route is structurally blocked.

**But the bound is a static question, and the answer is that there is no bound.**

## What is actually in the image

`SLUS_005.61` text, disassembled with plain `llvm-objdump -d` (the `--triple=mips` form decodes this
image **wrong and silently** — issue 0032 §5.1 — so the plain form is the one that agrees with the
CPU's own little-endian reads).

**The array base `0x801659D0` appears exactly THREE times in code:**

```
80015e10: addiu  $4,  $4,  0x59d0      ; base
80015e60: addiu  $16, $16, 0x59d0      ; base
80015ea8: addiu  $2,  $2,  0x59d0      ; base, then published to the cursor
```

**The array END — `base + 8 * 12` = `0x80165A20` — appears ZERO times in code.** The only textual hit
is `80109c08 lb $10, -0x5a20($zero)`, which is a data word being decoded as an instruction, not a
comparison. (`8011b0a0`, the fourth `0x59d0` hit, is the same kind of artefact.)

**The cursor `0x80141F68` is touched exactly FOUR times:**

| address | instruction | what it is |
|---|---|---|
| `0x80015E18` | `sw $4, 0x1f68($1)` | clear — publish the base |
| `0x80015EB0` | `sw $2, 0x1f68($1)` | clear's tail — publish `0x801659D0` |
| `0x80015F60` | `lw $5, 0x1f68($5)` | **arithmetic, not a test** — followed by `addiu $4,$5,0x6` |
| `0x80015FE0` | `sw $5, 0x1f68($1)` | the appender — no comparison in its 75 instructions |

**None of the four is a bound check.** The one read is consumed by `addiu $4, $5, 0x6` and never
compared. The appender stores and returns — `0x80015FE4` onwards is the epilogue (`lw $ra, 0x20($sp)`
… `jr $ra`), so **one call appends exactly one record and does not loop**.

## Who calls the appender, and what shape they have

**17 call sites** (`jal 0x15ecc`). The shape at the clearest one is per-object dispatch, not a loop:

```
80093c64: lb    $2, 0x2($16)
80093c6c: bnez  $2, 0x80093c7c
80093c70: addiu $5, $zero, 0x140
80093c74: jal   0x15ecc          ; append  ($4=obj, $5=0x140, $6=0x30)
80093c7c: lb    $3, 0x2($16)
80093c84: bne   $3, $2(=1), 0x80093c9c
80093c90: jal   0x15ecc          ; append  ($4=obj, $5=0x140, $6=0x40)
```

A byte selector at `obj+2` picks 0, 1 or 2 appends, and the function at `0x80093c54` returns at
`0x80093ca0`-ish without a loop. **So the per-field count is a sum over whichever of the 17 sites
execute — and no single site, nor the appender, can overflow the array on its own.**

## What this establishes, and what it does NOT

**Establishes:**

- **The guest enforces no capacity on this array.** The base is published; the appender is unbounded;
  no instruction in the image compares the cursor against an end.
- **Therefore "an 8-entry array" is the observer's inference, not a fact from the image.** It comes from
  what the *consumer* reads, and the writer has no opinion.
- **The port cannot be faulted for overflowing an 8-entry array, because no such array bound exists.**
  A bound enforced only by the consumer is a bound retail's own code would violate identically on the
  same input.

**Does NOT establish — and this is where the fault question now sits:**

- **Whether retail's per-field append count is 9/10 or smaller.** That is a runtime question about how
  many of the 17 sites execute in the fatal field, and it is the remaining thing that decides whether
  this is a port defect at all.
- **Whether the consumer reads a fixed count.** If `update_item_objects` reads N entries unconditionally,
  then the 10th append corrupting `item_objects[0]` is a **retail** behaviour reproduced faithfully, and
  the fault is downstream of a faithful append. If the consumer is itself bounded by the same cursor,
  the overflow is contained and the fault has another cause.

**So the frontier has moved, and it is narrower and cheaper to answer than issue 0032 left it:** the
next step is **one disassembly of `update_item_objects`**, to establish whether the consumer bounds
itself by the cursor or reads a fixed count. That is a single function, reachable statically, and it
decides the shape of the fault without any run.

**Falsifier:** an instruction in the image that compares `0x80141F68` (or any materialised form of the
base) against an end value, which would restore the bound this issue says is absent. A consumer that
proves itself bounded by the cursor would also refute "the overflow is a retail behaviour", because
the append past the end would then never be read.
