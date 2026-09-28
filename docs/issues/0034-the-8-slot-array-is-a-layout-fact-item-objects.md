---
id: 0034
title: The 8-slot array is a LAYOUT fact — item_objects[0] sits at base+96 — and the appender advances the cursor by 12 per CALL, so the count is 10 calls in one field
status: open
symptom: issue 0033 established that the guest enforces no capacity on the VRAM-rect array and that
  the "8" is the observer's inference. It named the next step: one disassembly of `update_item_objects`
  to establish whether the consumer bounds itself by the cursor or reads a fixed count. **This is that
  disassembly, and it does not say what 0033 expected.**
tags: fault,stage-load,mmx4,decomp,bytes,array-bound
created: 2026-09-28
updated: 2026-09-28
---

## The 8 IS REAL — but it is a layout, not a check

`item_objects[0]` is at **`0x80165A30`**, and it is referenced in **five** real code sites
(`0x8002176c`, `0x80024074`, `0x8002a938`, `0x8002adc0`, `0x80052228`, each an
`addiu $r, $r, 0x5a30` after `lui $r, 0x8016`).

And `0x80165A30` is **exactly** `0x801659D0 + 0x60` = `base + 8 * 12`.

**So the array has precisely eight 12-byte records of storage, and that is a fact about the DATA
LAYOUT — the next structure begins there — not an instruction that enforces it.** Combined with issue
0033: the guest uses `item_objects[0]` in five places and **never compares the append cursor against
it**. There is no bound because the bound is expressed by adjacency, not by a test.

**This is a stronger form of the same finding.** "The writer has no check" understates it: the array's
capacity is not recorded anywhere, and the only thing making it eight is that something else starts
there.

## The appender advances the cursor by 12 per CALL, not per loop iteration

`0x80015ECC` is one function, `0x80015ECC`–`0x80015FFC`. Its shape:

```
80015ee8: lbu   $3, 0x47($4)
80015eec: lbu   $2, 0x48($4)
80015ef4: beq   $2, $3, 0x80015fe4      <- equal -> straight to the epilogue, no append
...
80015f74: <loop head>
80015fc0: subu  $16, $16, $2
80015fc8: addiu $4,  $4,  0xc            <- the record pointer advances 12 per ITERATION
80015fcc: sll   $2,  $16, 0x10
80015fd0: bnez  $2, 0x80015f74           <- loop back
80015fd4: addiu $5,  $5,  0xc            <- the CURSOR advances 12, ONCE, after the loop
80015fe0: sw    $5,  0x1f68($1)
```

**So one call = one decompress pass, and it claims exactly ONE array slot no matter how many 12-byte
records the inner loop wrote.** The inner loop's `$4` walk is the decompressor's own output pointer,
not the array index.

**Therefore the array index is the CALL COUNT, and 0032's observation is exactly that: a cursor final
value of `0x80165A3C` is `base + 10*12`, i.e. ten calls in one presented field.** Calls 9 and 10 land
on `0x80165A30` (`item_objects[0]`) and `0x80165A3C`.

## What this settles, and what it makes newly urgent

**Settles:** the mechanism. The fault is **two calls more than the layout allows, in one field**, and
the guest's own adjacent structure is what gets hit. It is not a mis-decode, not a bad pointer, and not
a count that is off by one — it is a count that is off by **two**, and the guest has no defence.

**Makes newly urgent, and this is the honest part:** 0032 could not show that `0x80165A30` is *written*
rather than merely *read*, because `PSXPORT_WWATCH` cannot answer it — its `pc`/`ra` are the executor
SEGMENT boundary, not the store's site, and it matches only a store's **start** address. So the chain
"call 9 and 10 land on `item_objects[0]`" is a **layout and control-flow argument, not a measured
store.** The store would close it, and the instrument that would record it does not exist.

**And the question that decides defect-or-not has sharpened, not gone:** retail running the same disc,
the same level and the same authored object data would make **the same call count**, because the count
is a function of which of the 17 `jal 0x15ecc` sites execute. **So on the port's own evidence this
looks like faithfully reproduced retail behaviour rather than a port defect** — but "looks like" is not
"established", and establishing it needs the store, not the layout.

**Falsifier:** a store to `0x80165A30` or `0x80165A3C` attributable to `0x80015FE0` would close the
chain; the absence of such a store, with the cursor still at `base + 10*12`, would refute it and send
the search to whoever else writes that structure. Either answer is decisive, and **both need an
instrument that does not exist yet** — the cheapest is a RAM-dump bracket across the fatal field
comparing `0x80165A30` before and after, which 0032 §5.3 already shows is only sound at
`PSXPORT_RAMDUMP_FRAME=14756`.
