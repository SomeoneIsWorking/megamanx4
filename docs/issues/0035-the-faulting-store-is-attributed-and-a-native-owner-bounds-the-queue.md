---
id: 0035
title: The faulting store is attributed — nine appends for g_Player from ONE call site in ONE guest field — and a native owner of the rectangle queue now bounds the write that overflows it
status: open
symptom: |
  Issues 0032, 0033 and 0034 established the mechanism of the stage-load fault — the guest's VRAM
  rectangle queue at 0x801659D0 is appended to with no capacity test, the ninth 12-byte record
  lands on `item_objects[0]` at 0x80165A30, and `update_item_objects` then dispatches on a
  rectangle as if it were a state index and calls a data word. All three ended with the same open
  measurement: WHICH instruction wrote 0x80165A30 could not be attributed, because
  `PSXPORT_WWATCH` reports the executor SEGMENT boundary rather than the store's site. This issue
  closes that measurement, settles defect-or-not, and lands the native owner that removes the
  out-of-bounds write at its cause.
state_items: S004, S009
tags: fault,stage-load,mmx4,decomp,bytes,native-owner,array-bound,attribution
created: 2026-09-28
updated: 2026-09-28
---

## 0. Summary

**The attribution is measured, not argued.** In one run the guest appender was entered **184**
times; **9** of those calls wrote a record, all **9** from a single one of the 17 call sites
(`0x80022058`, return address `0x80022060`), all **9** for the same object — `g_Player`,
`0x801418C8` — and all **9** inside **one** guest field (the guest's own field counter,
`0x80141BD8`, read `175501` on every one of them). The ninth store is the one that changes
`item_objects[0].active` from `0x00` to `0x40`, and `item_objects[0].x_pos` from `0` to
`0x8016DEA8`. The other 175 calls returned early without storing, and **16 of the 17 call sites
never executed at all**.

**The verdict on the fault is (a): a guest defect this port reproduced.** The queue's writer has no
capacity test anywhere, and its post-loop terminator store is placed at `&entry[emitted]` — the
slot AFTER the last one written — so it writes past the array at the array's own designed
occupancy. Retail has no defence the port lacks.

**The verdict on the COUNT is explicitly NOT established**, and the mitigation does not depend on
it: an entry at index 8 was never uploadable by retail either, because the guest's own uploader
reads exactly 8. A write with no possible benefit and a corruption cost is a defect whoever
authored the count.

**The fix is a native owner, not a clamp** — `game/core/vram_rect_queue.{h,cpp}` replaces all three
guest functions, in readable C++ with named structures, and supplies the array's real capacity at
the one store that can cross it. `tools/verify_vram_rect_queue.py` re-derives all 64 of its
constants from the authenticated `SLUS_005.61`, and `--selftest` shows **10/10** mutations caught.

**The fault is gone and the run goes further**: `0x26010006` never appears again, and the guest
reaches display field **31,166** against the fault's **29,514** — **+1,652 fields** — before a
DIFFERENT, already-guarded, non-faulting condition stops it.

## 1. The instrument, and why `PSXPORT_WWATCH` was the wrong shape

`PSXPORT_WWATCH` cannot do this, for two independent reasons 0032 measured: its `pc`/`ra` are the
last executor SEGMENT boundary, and it matches only a store's START address. A watch on
`0x80165A30` therefore reports the enclosing segment, not the store.

**What was used instead: a native override on the appender that WRAPS the original.** It is the
same seam the product already uses for eleven other functions, and it changes nothing about the
code that runs:

```cpp
void probeAppend(Core *core) {
  const std::uint32_t ra = core->r[31];          // the guest's OWN link register for THIS call
  const std::uint32_t obj = core->r[4];
  const std::int32_t  x = static_cast<std::int16_t>(core->r[5]);
  const std::int32_t  y = static_cast<std::int16_t>(core->r[6]);
  const std::uint32_t before = core->mem_r32(0x80141F68);
  original(0x80015ECC, "vramrect-probe original", core);   // the REAL guest body runs
  const std::uint32_t after = core->mem_r32(0x80141F68);  // stored ⇔ the cursor advanced
  /* log field, ra, obj, x, y, cur/prev anim, gfx slot, band count, before, after,
     the 12 bytes at after-12, and item_objects[0].active/.x_pos */
}
```

**Why this is structurally sound, stated as the property it needs.** Inside a native override the
frame's `$31` IS the return address of the specific `jal` that reached the function, because the
guest's link register is committed before the dispatcher transfers control and is not touched
before the override reads it. `PSXPORT_WWATCH` cannot have that, because it reads `Core::pc`,
which is only written at segment boundaries. So the instrument's `ra` answers exactly the question
the watch cannot, and it answers it per CALL rather than per segment.

**It is also falsifiable, and that is the part that matters more than the mechanism.** The same
wrapper, in the same run, reported the *other* answer for 175 of 184 calls (`stored=0`), and
reported 16 of the 17 call sites as never reached. A probe that cannot say "no" is not an
attribution. Raw log: `scratch/appenderoverride/attribution.log`, 184 `CALL` lines.

## 2. What the measurement says, with its denominators

| quantity | value | denominator |
|---|---|---|
| appender invocations in the run | **184** | — |
| of those, calls that STORED a record | **9** | 9 of 184 |
| of those, calls that returned early (`cur == prev`) | **175** | 175 of 184 |
| distinct call sites reached | **1** (`0x80022058`, ra `0x80022060`) | 1 of 17 |
| distinct objects | **1** (`0x801418C8` = `g_Player`) | 1 |
| guest fields in which any call happened | **1** (field counter `175501`) | 1 of the run's fields |
| records written, and where they landed | indices 1..9, `0x801659D0`..`0x80165A30` | 9 |
| cursor at the end of the fatal field | `0x80165A3C` = `kQueueBase + 9*12` | — |

**The 9th store is the faulting store, and the measurement shows it directly.** On stores 1..8
`item_objects[0].active` reads `0x00`; on store 9 it reads `0x40` and `item_objects[0].x_pos` reads
`0x8016DEA8`. `0x40` is the low byte of the rectangle's `x = 0x140`; `0x8016DEA8` is the
rectangle's source pointer, which the gate pins as `kSharedGfxBuffer`. The record that made the
item object dispatchable is byte-for-byte the record the appender wrote.

**And the count is not 9 objects.** It is **one** object, nine times. The appender latches
`prev_anim = cur_anim` at `0x80015F04` and returns immediately when they are equal
(`beq $2,$3,0x80015FE4` at `0x80015EF4`), so a stored record requires the animation index to have
MOVED since the last call. The measured sequence is:

```
calls   1..167  cur=0  prev=0   stored=0   <- 167 passes with the animation index unmoved
call      168   cur=53 prev=255 stored=1   index 1     bands=32  slot=3  x=320 y=0
call      169   cur=53 prev=53  stored=0
call      170   cur=54 prev=53  stored=1   index 2
call      171   cur=54 prev=54  stored=0
call      172   cur=53 prev=54  stored=1   index 3
   ... alternating 53 / 54, storing on every second call, until ...
call      184   cur=53 prev=54  stored=1   index 9     -> 0x80165A30 = item_objects[0]
```

**So the player's animation index alternated between 53 and 54 on nine consecutive passes.** Each
pass emitted exactly ONE entry (`bands = 32`, so the full-band path runs once with
`height = 32 & ~15 = 32` and `remaining` reaches zero), which is why the cursor advanced 9 entries
over 9 calls — and that is a coincidence of this data, not the general rule. §3 corrects the
reading issues 0033 and 0034 recorded.

## 3. Two readings from 0033 and 0034 that this measurement corrects

**Both read `0x80015FD4 addiu $5,$5,0xc` as a post-loop instruction.** It is the DELAY SLOT of the
loop branch `bne $2,$zero,0x80015F74` at `0x80015FD0`, so it executes once per ENTRY, not once per
call, and one call can emit several entries. 0033 concluded "one call appends exactly one record
and does not loop" and 0034 concluded "the array index is the CALL COUNT"; both are wrong in
general and happen to agree with this run because `bands == 32` made every call emit one entry.
`verify_vram_rect_queue.py` pins the branch target so the reading cannot come back.

**Both derived the count as 10, from a mis-addition.** `0x80165A3C - 0x801659D0 = 0x6C = 9 * 12`,
not `10 * 12`; 0033's own measured nine store executions were right and 0034's title line
("ten calls in one field") was not.

**What survives, and it is the load-bearing part:** the array's eight entries are a LAYOUT fact
(`kQueueEnd == 0x80165A30 == item_objects[0]`, a `static_assert` in the owner), the guest's own
clearer states eight (`sltiu $2,$5,8` at `0x80015E40`) and its uploader states the end
(`addiu $3,$s0,0x60` at `0x80015E64`), and the appender tests for neither. That is now
`tools/verify_vram_rect_queue.py`'s claim 1–§1, and the "no capacity-shaped compare in the
appender" claim was written to be sensitive in BOTH directions: planting one in the appender fails
the selftest.

## 4. (a) or (b): the verdict, and the part that is not established

**(a) for the fault, from bytes and from the measurement.**

* The queue's capacity is never tested by its writer. Scanned: the appender's 77 instructions
  contain **zero** capacity-shaped compares, and its only immediate compare is the band threshold
  `slti $2,$3,0x10` at `0x80015F78`. Both directions of that claim are in the selftest.
* **The terminator store is the sharper defect and 0032/0033/0034 all missed it.** `sw $zero,8($5)`
  at `0x80015FD8` writes the source pointer of `&entry[emitted]` — one slot PAST the last one
  written. At fewer than 8 entries it re-zeroes a slot `clear` already zeroed this field, so it is
  redundant; **at exactly 8 entries — the array's designed capacity — it zeroes
  `item_objects[0].x_pos` at `+8`.** That fires on a full queue, not on an overflowing one, and it
  needs no ninth append at all.
* The overflow is consumed by the guest's own pass order, measured from the image: the update pass
  opens its frame at `0x80021F34`, dispatches item objects at `0x80021FE8` (`jal 0x8002174C`) and
  only then appends the player's rectangles at `0x80022058`. So the ninth entry cannot fault on the
  pass that wrote it — it is read by the NEXT pass's dispatch, which is what the register file at
  the fault shows (`r31 = 0x800BEBEC`, `r4 = 0x80165A30`).
* The per-pass count is the guest's own. The guest's scheduler `func_80012600` is a ring walk
  (`lw $v0,0($s0)` / `addiu $v0,$v0,0x80` / `beq $3,$zero,<top>` at `0x80012710`–`0x80012724`) that
  returns to the retail main loop only when the ring is exhausted, and the appender call sits at
  the end of a pass. All 184 invocations carry the same field counter, so all 184 are inside ONE
  `func_80012600` call and therefore inside ONE retail main-loop iteration, with no `VSync(0)`
  between them. The queue is reset once per main-loop iteration, by `clear_vram_rect_ptrs` and
  again by `load_vram_rect_ptrs`.

**NOT ESTABLISHED, and it is named rather than assumed: whether retail's ring walk dispatches this
mode 184 times on this disc.** The ring's live-task set is guest state the port has not traced. If
retail dispatched fewer, retail would not have overflowed and the divergence would be in the ring's
contents — a DIFFERENT defect with a DIFFERENT fix. That does not change §4's first four bullets,
and it is the next step in §7.

**The mitigation is justified without that answer, which is the point of stating it this way.** An
entry at index 8 was never uploadable: the guest's uploader loops `while (entry < base + 0x60)` and
`LoadImage`s only non-null entries, so it reads indices 0..7. The write therefore has **no possible
benefit** under any count, and its only effect is to corrupt the next guest structure. A store with
no benefit and a corruption cost is a defect regardless of who authored the count.

## 5. The owner, and the bound

`game/core/vram_rect_queue.{h,cpp}` is a native override of all three guest functions, registered
through the per-Core seam in `native_overrides.cpp`. It is this repository's own C++; the AGPL-3.0
reference decompilation supplied the structure NAMES (`vram_rect_ptrs`, `RectPtrPair`) and the loop
shape, and no decompiled text is shipped. See §8 for the licence split.

What it owns, in order:

* `clear` — zero the eight entries, republish the base. `0x80015E0C`–`0x80015E4C`.
* `upload` — `LoadImage` every entry whose source pointer is non-null, in array order, republish the
  base. `0x80015E54`–`0x80015EB0`. The BIOS `LoadImage` entry stays a guest call; only the loop is
  native.
* `append` — read the object's animation index, return if it has not moved, latch it, read the
  band's count and the decompressed buffer, call the guest's RLE decompressor, then walk the bands.
  `0x80015ECC`–`0x80015FE0`. **The decompressor stays a guest call** (`0x80016FF4`): it is a leaf
  that owns a compression format, and reimplementing it here would duplicate a format rather than
  own behaviour.

**The bound, in two places, because the defect has two stores, and it is a MEMBERSHIP test over the
array rather than the upper bound the fault teaches you to write:**

```cpp
if (cursor < kQueueBase || cursor >= kQueueEnd) { record.refused += 1; break; }   // the record store
...
if (cursor >= kQueueBase && cursor + kEntryStride <= kQueueEnd) {                   // the terminator
  core.mem_w32(cursor + 8, 0u);
}
```

**The first version of this was `cursor >= kQueueEnd` alone, and that is wrong** — recorded here
because the upper bound is what the fault pushes you toward. `kCursorGlobal` is a published global the
guest itself writes, so a cursor **below** `kQueueBase` is exactly as possible as one past
`kQueueEnd`, and an upper bound would write rectangles over whatever is there. The terminator store
is at `cursor + 8`, so its test has to cover a whole RECORD, not a whole word: a cursor one entry
from the end still reaches past the array. Both corrections were found by reasoning about the fix's
own edge case, not by a run, and neither is observable in the runs below — which is precisely why a
bound nobody reasons about is a bound nobody gets right.

Nothing else changed. The band's arithmetic, the record layout, the latching and the early return
are the guest's, and the gate pins all of them.

**The owner's own census is the permanent instrument, and it discriminates.** Before the fix: *9
entries written, 8 fit*. After: *8 written, 8 fit, 1 refused*, and one `queue is FULL` line per
field carrying the call site, the object, the coordinates and the denominator. A run that never
fills the queue says so with a denominator rather than by silence.

## 6. What the gate holds, and what it caught in my own code

`tools/verify_vram_rect_queue.py`, registered as ctest `vram_rect_queue_evidence`:

* **64 comparisons** covering the queue's layout and the structural claim, the clearer's and the
  uploader's own stated bound, the exhaustive three-writer census of the cursor word, the appender's
  early return / latch / band count / stream mask / both buffers / band geometry, the per-iteration
  cursor advance and its delay slot, the pass ordering the fault argument rests on, and the
  seventeen-site census. **64/64 pass.**
* **`--selftest`: 10/10 mutations caught**, including planting a fourth cursor writer, planting a
  capacity compare INSIDE the appender (the same claim in the other direction), swapping the loop
  branch's target (the 0033/0034 misreading), moving the array base off `item_objects[0]`, and
  planting a fourth call site.
* **CORRECTED 2026-10-09.** This entry claimed the image's stream-offset mask is sixteen bits. It is
  twenty: `lui $4,0xf` at `0x80015F44` precedes the `ori $4,$4,0xffff` at `0x80015F48`, so the `and` at
  `0x80015F4C` uses `0xFFFFF`, as the reference decompilation says. The sixteen-bit mask made the guest
  decompressor read the wrong stream, which is the cause of issue 0036 and the `0x0113D7D0` dispatch.
  `kStreamOffsetMask` is `0xFFFFF` and `x4_vram_rect_queue` pins it.
* Two of the gate's own helpers were wrong before the gate was right, and both produced a confident
  wrong answer rather than an error: a MIPS shift puts its SOURCE in the `rt` slot and a
  non-shift puts its source in `rs`; and a mutation helper that read the load address one word too
  far offset every mutation by 8, so `--selftest` reported **0 of 9** mutations caught against an
  image passing 64 of 64. Both are now comments in the file, because both are re-tempting.

## 7. How far it gets, and the exact next step

**Two "after" runs exist, and the difference between them is a bug this issue found, so both are
reported.** The first two runs of the owner still carried the twenty-bit stream mask taken from the
decompilation (§6 says the gate caught it). With that mask the guest reads the wrong compressed
stream and follows a different path.

| | before the owner | owner, 20-bit mask (SUPERSEDED) | owner, 16-bit mask (WRONG, superseded) |
|---|---|---|---|
| fatal `0x26010006` dispatch | present | **absent** | **absent** (0 occurrences) |
| display field reached | **29,514** | **31,166** | past the refusal at field counter 175,501, and further |
| entries written / fit | 9 / 8 | 8 / 8, 1 refused | 8 / 8, 1 refused |
| what stopped the run | the fault | `kMaxTurnFields = 512` budget turns without a field boundary, at `0x800312B4` | `guest::call` refused a **non-guest** entry word, `0x0113D7D0` |

**The fault is gone in both, and the shipping run's refusal line is the denominator that says so:**
*"8 of 9 entries this run fit; the rest were refused rather than written over the next guest
structure"* — against the previous run's nine records with the ninth landing on `item_objects[0]`.

**The shipping run's new stop is NOT characterised, and it is not a regression.** It is
`vsync_sync.cpp`'s own `guest::call(c, vblankHandler)`, where `vblankHandler` is read from the
guest's class-0 interrupt table at `0x8011CB98` and is now **`0x0113D7D0`** — a word with no
`0x8`/`0xA` top nibble, so not a KSEG address. `0x8013D7D0` is the same word with its top byte
replaced by `0x01`, which is the shape of a single byte store. **This owner cannot have written it:
its only stores are four s16 rectangle fields, one u32 source pointer, one u32 zero and one u32
cursor, and every address it touches is inside `[kQueueBase, kQueueEnd)` because the bound is a
membership test** (§5). So it is a second, later corruption in the same family as the first.

**Two next steps, both bounded to one measurement each.** The first is the immediate blocker.

1. **The writer of the byte at `0x8011CB9B`** — the class-0 interrupt table entry now holds
   `0x0113D7D0` and stops the run (§7). One byte, one store site, and it is the immediate blocker.
2. **The writer of `g_Player+0x47`** — the measurement brackets it to the code **between two
   consecutive executions of the pass function `0x80021F34`**, i.e. inside the ring walk
   `0x80012600` or inside another task it dispatches, because the pass's own appender call is the
   last call before its epilogue. There are **66** `sb rt,0x47(reg)` sites in `.text`; the
   measurement is a native override on `0x80021F34` that snapshots `+0x47` on entry, which brackets
   the alternation to one dispatch and turns 66 candidates into one function. **If that writer turns
   out to be paced by something the port drives, the count is (b) after all and the bound in §5 is a
   mitigation with a real fix behind it — which is why the risk is stated here rather than buried.**
   If it is the guest's own animation sequencer, (a) is complete.

**The guard that already exists is deliberately not widened.** `deliverField` refuses
`vblankHandler == 0` and nothing else, which is why step 1's corruption reaches the dispatcher as
"ambiguous code-image identity" rather than being named at the point it happened. Adding a
"and it must look like a KSEG address" clause would name it and cost one line — and would hide the
writer, which is the finding. It is left as the next step, not folded in as a fix.

## 8. Licence, and what was taken as knowledge versus verified

`external/mmx4` is AGPL-3.0 and **nothing from it is copied into this repository or into
`psxport`**. This repository already carries `LICENSE` (AGPL-3.0-or-later) and
`tools/check_license_containment.py`; the two new files carry the file-level SPDX marker and the
`derived from external/mmx4` line, and `LICENSING.md` already describes that arrangement.

Taken from the decompilation as KNOWLEDGE, and then re-derived from the image by the gate: the
structure names `vram_rect_ptrs` / `vram_rect_ptr` / `RectPtrPair`; the call ordering of
`func_80021158` (which put me on `update_item_objects` before the appender); the *shape* of the band
loop; and `func_8001D460`'s countdown, which is what identified the pass function's caller.

Verified here, against the authenticated bytes, and NOT taken from the decompilation: every address,
every immediate, the record layout, the twelve-bit band field, the per-iteration cursor advance and
its delay slot, the three-writer census, the pass ordering, and the stream mask (originally recorded as sixteen bits,
wrongly; it is twenty, see the correction in section 6).

## 9. The measurement trap this issue walked into, recorded because it nearly cost the finding

For one probe iteration the log printed `x=0 y=0` for every call while the record bytes said
`x = 0x140, y = 0`. The cause: `Core::mem_r16s(a)` takes a guest ADDRESS, and the probe had written
`core->mem_r16s(5u)` to read register `$5` — i.e. guest address 5, which reads zero. **A
convenient-looking zero from a wrong accessor is exactly the shape of a correct measurement**, and
it would have made the call arguments look like a second, contradictory fact. The fix is in the
owner's `install()` with a comment naming the trap. The record bytes were always the authority; the
register line only became trustworthy after the accessor was corrected.
