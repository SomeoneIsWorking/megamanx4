---
id: 32
title: 0x26010006 is a data word in an 8-entry function-pointer table the guest indexed with a
  record byte it had itself overwritten, and the array doing the overwriting is bounded by the image
  at eight entries
status: open
symptom: |
  Every product run ends with
      [native-dispatch:error] guest address 0x26010006 resolves to zero or multiple active code images
      [x4-thread:error] guest task stopped at 0x26010006 with unexpected fault boundary: ambiguous code-image identity
  at presented field 1,178 / 2,383 / 2,830 (issue 0030/0031) or ~14,758 in this issue's runs. Issue
  0030 called it "a garbage-pointer fault in the post-park stage-load sequence" and correctly refused
  to attribute it without RE. This issue does the RE and names the word, the writer's shape, the
  table, and the bound that was crossed. It does NOT name the instruction that writes the cursor,
  and says so.
tags: RE-07,RE-08,cd,stage-load,diagnostics,frontier
created: 2026-09-28
updated: 2026-09-28
---

## 1. The fault, read from the guest's own words at the fault

The product's own fatal line names an address and nothing else. The register file at that moment,
which the title now reports (`game/core/bios_threads.cpp`, added by this issue), settles the shape:

    r1=0x80110100  r2=0x26010006  r3=0x8016DEA8  r4=0x80165A30  r17=0x800F2910  r18=0x800F21B0
    r31=0x800BEBEC

**`r2` is the pointer that was followed, `r31` is the guest's own link register at the branch, and
`r1` is the index the guest computed.** Three independent routes then agree on one number:

| route | what it reads | value |
|---|---|---|
| `r2` | the word actually loaded and called | `0x26010006` |
| `r1` | `0x80110000 + (byte << 2)`, so `r1 - 0x80110000 = 0x100` | index **64** |
| `PSXPORT_WWATCH` on the record | a guest CPU store of `0x00000040` to `0x80165A34` in the fatal field | state byte **0x40** |

## 2. The words that settle each claim

All disassembly is `llvm-objdump -d` over `tools/probe_elfwrap.py`'s wrap — **no `--triple`**, which
is what this port's byte order requires (see §6).

**The branch.** `0x800BEBB4` is `item_object_update_funcs[1]`: `D_800F2910` at `0x800F2910` holds 115
consecutive guest code pointers and `word[1] = 0x800BEBB4`. It is reached from `update_item_objects`
at `0x8002174C`, which publishes the record array itself — `lui $2,0x8016` / `addiu $2,$2,0x5A30` =
`0x80165A30`, and `addiu $3,$2,0x1180` = 32 records of `0x8C` — and dispatches on `base.id` at
`0x80021800` (`lb $2,0x1($4)` → `sll 2` → `addu $2,$2,$17` with `$17 = 0x800F2910`).

    800bebbc: lw    $3, 0x8($4)          ; +0x18 = +8
    800bebc0: lb    $2, 0x4($4)          ; <-- the index: a SIGNED BYTE at +4
    800bebc4: lw    $5, 0xc($4)          ; +0x1C = +0xC
    800bebc8: sll   $2, $2, 2
    800bebcc: sw    $3, 0x18($4)
    800bebd0: sw    $5, 0x1c($4)
    800bebd4: lui   $1, 0x8011
    800bebd8: addu  $1, $1, $2           ; $1 = 0x80110000 + (byte << 2)
    800bebdc: lw    $2, -0x3d10($1)      ; <-- the table read
    800bebe4: jalr  $2                   ; <-- THE FAULT

**The table.** Base `0x80110000 - 0x3D10` = **`0x8010C2F0`**. It holds **exactly 8** consecutive guest
code pointers (indices 0..7: `0x800BEBFC 0x800BED6C 0x800BF530 0x800BF5EC 0x800BEED4 0x800BEFCC
0x800BF1FC 0x800BF508`), `word[8] = 0x00000000`, and then the image's general data. `word[64]` is at
`0x8010C3F0` and is **`0x26010006`**.

**So `0x26010006` is a data word in the image, not a code address**, and the guest called it because
the index was 64 and the table has 8 entries. `0x26010006 & 0x1FFFFFFF = 0x02010006` is main RAM but
outside the one published image range `[0x80010000,0x80130000)`, so the framework's "zero or multiple
active code images" refusal is **correct** and is not a contributor.

**Only four words in the whole 2 MB of RAM equal `0x26010006`** (measured over four full RAM dumps),
all at immutable image addresses: `0x800FC57C`, `0x800FC5A8`, `0x80101754`, `0x8010C3F0`. Only
`0x8010C3F0` is reachable as `0x8010C2F0 + 64*4`. So the value was never written by the port: it is
read straight out of the executable the guest was loaded from.

**The record.** The title's fatal report now prints the guest's own `$a0` argument, in bytes:

    a0=0x80165A30  w0=0x00000140 w1=0x00200040 w2=0x8016DEA8 w3=0x00000000
    bytes: 40 01 00 00  40 00 20 00  A8 DE 16 80  00 00 00 00

`active = 0x40`, `id = 0x01`, **`state` (+4) = `0x40`**, `+6 = 0x20`, `+8 = 0x8016DEA8`.

## 3. The mechanism: the record is a foreign 12-byte record, not an item object

`0x801659D0` is the decomp's `vram_rect_ptrs`, and **the image states its own bound**:

    clear_vram_rect_ptrs (0x80015E0C)      load_vram_rect_ptrs (0x80015E54)
      lui   $4, 0x8016 / addiu $4,$4,0x59D0   lui   $16, 0x8016 / addiu $16,$16,0x59d0
      ...                                     addiu $3, $16, 0x60      <-- the END
      addiu $3, $3, 0xc        ; stride 12     sltu  $2, $16, $3
      sltiu $2, $5, 0x8        ; <-- 8 entries bnez $2, loop

**`0x801659D0 + 8 * 12 = 0x80165A30`, which is `item_objects[0]` exactly.** The array's last legal
slot ends one byte before the record array begins.

A RAM dump taken **inside the run** (`PSXPORT_RAMDUMP_FRAME=14756`, the last frame that dumps before
the fault) shows the array holding one record more than its bound, and the record array's first
record being byte-identical to it:

| dump frame | `vram_rect_ptrs` slots holding `40 01 00 00 40 00 20 00 A8 DE 16 80` | `0x80141F68` (the published cursor) | `item_objects[0].active` |
|---|---|---|---|
| 14700 | none | `0x801659D0` | 0 |
| 14730 | none | `0x801659D0` | 0 |
| 14745 | 4 (…`0x801659F4`) | `0x80165A00` | 0 |
| 14752 | 7 (…`0x80165A18`) | `0x80165A24` | 0 |
| **14756** | **9 (…`0x80165A30` = `item_objects[0]`)** | `0x80165A3C` | **`0x40`** |

The cursor at `0x80141F68` is the array's own append cursor: `clear_vram_rect_ptrs` publishes the base
there (`sw $4,0x1f68($1)` at `0x80015E18`) and so does an appender at `0x80015FE0`, which advances it
by 12 and writes it back. **That appender never forms the array base or the array end in its 75
instructions**, so it cannot be comparing its cursor against the bound the other two functions state.
The cursor's final value `0x80165A3C` is `base + 10*12` — ten appends into an eight-entry array, the
tenth landing on `item_objects[0]`.

The record's own fields corroborate that it is not an item object: `+8 = 0x8016DEA8` is
`player_gfx_buf_0`, a **compile-time constant** in the guest's own code, and `+0x18` receives the same
value — which is what `0x800BEBCC`'s `sw $3, 0x18($4)` does after `lw $3, 0x8($4)`. The 12-byte record is
a decompressor's run/rectangle descriptor, and its `+4` halfword is a run field. `update_item_objects`
then reads that run field as a state index.

## 4. Is this a port defect? NOT ESTABLISHED, and the honest split is this

**Cleared, each from bytes or a measurement:**

* **Image identity / overlay publication (the briefing's candidate (a)).** X4 has one code image and
  no overlays (RE-03, measured over 138 ARCs plus the STR/XA set). One identity is published over
  `[0x80010000,0x80130000)`. The fault address is outside it, so this is not a missing-identity case,
  and the framework's refusal is right.
* **A loader boundary that resumes mid-sequence (candidate (b)).** The guest ran 1,557 consecutive
  task turns through `init_objects` (`0x80023DB8`) and the `update_*_objects` set, and the record was
  created and dispatched inside ONE presented field. Nothing shows a mid-sequence resume.
* **A stage-load DMA that is not awaited (candidate (c)).** `fast_wait::cd_get_sector` copies the raw
  sector into the guest's destination for every request, and the guest's own bytes confirm the
  framing: the archive ready callback `0x80013E68` issues `CdGetSector(scratch, 3)` for a 3-word probe
  and then `CdGetSector(cursor, 0x200)` = 2048 bytes of payload, advancing its read cursor 16 bytes
  per record — i.e. 2052 bytes per sector, exactly 4 header bytes at `raw[12]` plus 2048 of payload.
  The delivered archive stream at `0x80169498` opens `01 00 00 00 00 18 00 00 05 00 00 00 00 10 00 00`,
  whose size word `0x1800` = 6144 is **exactly** request 12's byte count, so the stream is framed and
  self-consistent.
* **The bad value being port-written.** `0x26010006` exists in RAM only at four immutable image
  addresses. No port code writes it.

**Not established, and this is the remaining frontier:** *which instruction advances
`0x80141F68` past the array end.* `PSXPORT_WWATCH` over `[0x80141F00,0x80142000)` logged **6,184
stores** across the run and hit `0x80141F68` **once**, at frame 1, from crt0's BSS clear with value 0
— while the word demonstrably reads `0x801659D0` … `0x80165A3C` in mid-run dumps. That contradiction
is unexplained, and because of it **this issue does not claim the appender at `0x80015ECC` is the
writer**; it claims only that the appender exists, is unbounded, and is the shape the record matches.

## 5. Three instrument defects found while doing this, all now fixed or bounded

Each of these produced a confident wrong answer first, which is why they are recorded rather than
tidied away.

1. **`llvm-objdump --triple=mips` decodes this image WRONG for this port, and silently.**
   `scratch/raw/x4_text.elf` is a big-endian-`EI_DATA` file, so `--triple=mips` makes llvm-objdump
   read it big-endian, and every `lui`/`addiu` comes out as a `beq`/`b`. The correct invocation is
   plain `llvm-objdump -d` (or `--triple=mipsel`). **Why:** this port's `Core` reads words
   little-endian (`mem_r32` is a `memcpy` on a little-endian host) and the provisioned executable is
   stored word-byte-swapped, so the little-endian reading is the one the CPU sees. Three
   measurements agree and are now gate cases in `tools/verify_stage_fault.py`: 5,380 `jr $ra` and
   79.4% of `jal` targets inside `.text` (LE) against 0 and 30.0% (BE); crt0's own `gp = 0x8012F418`
   and `heapBase = 0x80175F38`; `InitPAD2`'s `jr 0xB0` with function `0x12`. The same property holds
   for Tomba! 2's and Vagrant's provisioned images, so it is a workspace convention, not an X4 quirk.
2. **`PSXPORT_WWATCH`'s `pc` and `ra` are NOT the store's site.** They are the last executor *segment*
   boundary: `Core::pc` is only written by `copyLightrecToCore` and the native scopes, so it holds
   wherever the segment started, and `r[31]` is whatever was committed at that point. Measured: a
   store into a record reported `pc=0x8002B288 ra=0x800CB5A4`, and `0x8002B288`'s entire 40-instruction
   body contains no store to that record at all. `PSXPORT_WWATCH` also matches only on a store's
   **start** address, so a 4-byte store to `0x80173C80` never fires a watch on `0x80173C84` — which is
   why a byte watch on `0x801721D7` and `0x80173C84` produced nothing and that absence means
   "no narrow store", not "no store".
3. **My own first read of a RAM dump over-claimed.** I noted the 12-byte record pattern appears
   nowhere in RAM, from dumps taken ~25 fields before the fault. The record is created and consumed
   inside one field, so those dumps predate it: the measurement does **not** rule out that the record
   came from guest-visible data. It is only sound at `PSXPORT_RAMDUMP_FRAME=14756`, which is inside
   the fatal field.

## 6. What the gate now holds

`tools/verify_stage_fault.py` pins all of §2 and §3 from the authenticated `SLUS_005.61`:
**38 comparisons, 0 failures**, and a `--selftest` that mutates a copy of the image five ways —
byte-swapping crt0 to break the word order, `nop`-ing the `jalr`, changing the clear's trip count,
moving the array base off `item_objects`, and forming the array end inside the appender — and requires
**5/5** to be caught. Registered as ctest `stage_fault_evidence`.

The check found four of my own errors while it was being written (a `LUI` immediate read as 0x8014
where the image says 0x8016, a `+4` where the `lb` is at `+0xC`, and two over-broad absence claims
replaced with narrower falsifiable ones). That is the reason to want it.

`game/core/bios_threads.cpp` gains the register file, `r[31]`, and the `$a0` argument record on the
fatal path. The old one line named a branch **target** and nothing about the branch; this is the
change that made the whole diagnosis possible, and it is a named-failure report, not a fix.

## 7. Gate

`ctest --test-dir build` → **34/34 passed** (33 before, plus `stage_fault_evidence`). Baseline before
this issue was 33/33. `clang-format --dry-run --Werror game/core/bios_threads.cpp` clean. Full Clang
build clean. `tools/verify_stage_fault.py --check --selftest` → 38/38 and 5/5.

## 8. What remains

1. **The writer of `0x80141F68`.** The `PSXPORT_WWATCH` contradiction in §4 is the single open
   measurement. The next step is a store observation that can see what `PSXPORT_WWATCH` cannot — a
   DMA/host-side write, or a store whose start address is outside a byte range. `PSXPORT_STORE_OBSERVE`
   was armed on four candidate store PCs derived from a scan for `sb <0x40>, 4(base)` and observed
   **0 of 4**, so the candidate derivation was too narrow and the store observer's own teardown report
   never printed because the product `abort()`s. Neither is a reason to stop; both are a reason to
   build the instrument that answers it.
2. **Whether the guest is re-entering the appender instead of clearing the array.** The cursor is at
   `base` at f14730 and has advanced by 3 appends by f14745, so either one call emits several records
   or it is called several times between clears. `clear_vram_rect_ptrs` (`0x80015E0C`) is the reset and
   its callers are the next thing to census.
3. **Whether this is guest behaviour retail also hits.** If the appender's run count is data-driven
   and the data is right, retail would overrun too and this is not the port's business. That cannot
   be answered from one image, and it is the question item 1 has to reach before any fix is proposed.
4. **S009.** Unchanged and `missing`. No scene was reached: **0 of 2 captures with more than 2
   submitted prims**, the park's own measured 2 distinct colours and 2 prims. Boot, the two authored
   STR movies, the title front end and the post-park transition are all still not gameplay.
5. **Item 1 is the whole blocker.** Nothing downstream of a first stage scene can be measured until
   the guest gets past this.
