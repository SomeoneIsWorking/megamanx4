---
id: 33
title: The instruction that writes 0x80141F68 is 0x80015FE0 in decompress_player_gfx, and the
  nine appends that overrun the array are nine single-band calls inside one field — the per-field
  reset is NOT being skipped, so this is a guest bound the image states and never enforces
status: open
symptom: |
  Issue 0032 left exactly one measurement open: which instruction writes the cursor word
  0x80141F68, because PSXPORT_WWATCH hit it once in 6,184 stores and the cursor demonstrably
  read 0x801659D0..0x80165A3C mid-run. This issue closes it from bytes, and answers the
  "does retail overrun too" question that decides whether the fault is the port's business.
tags: RE-07,stage-load,diagnostics,correction,frontier
created: 2026-09-28
updated: 2026-09-28
---

## 0. Summary, and the correction that is part of it

**The writer is `0x80015FE0` — `sw $a1, 0x1F68($at)`, word `0xAC251F68` — in
`decompress_player_gfx` (`0x80015ECC`).** It is one of exactly three instructions in the whole
1,177,600-byte guest `.text` that write `0x80141F68`, and the only one that ever writes an
*advanced* value.

**The correction: my leading hypothesis was wrong, and the measurement said so before I built on
it.** Reading `X4FrameDriver::stepFrame`, the prefix holding `clear_vram_rect_ptrs` is skipped
whenever `movieOwnsPicture()` is true, and the resets run 60/59 times in ~14,757 presented fields
rather than once per field — so "the port is skipping the guest's per-field reset and the cursor
accumulates" looked established before any run. It is **falsified for this fault**: in the fatal
field the clear executed *immediately before* all nine appends, with no reset missing between
them. The resets are a real and separately-reportable divergence from retail's main loop; they
are not this fault.

## 1. The writer, established EXHAUSTIVELY from bytes

A MIPS store is exactly one 32-bit word — `op(6) base(5) rt(5) imm(16)` — so a store that can
reach a given word is found by matching two fields of one word. That makes this scan independent
of control flow, of register allocation, and of any constant tracking, which is why it can be
exhaustive where a dataflow walk could not (a dataflow walk left 35,026 of 38,175 stores with an
unresolved base and was worthless as evidence).

| # | site | word | instruction | what it publishes |
|---|---|---|---|---|
| 1 | `0x80015E18` | `0xAC241F68` | `sw $a0, 0x1F68($at)` | the **base**, `0x801659D0` — `clear_vram_rect_ptrs` |
| 2 | `0x80015EB0` | `0xAC221F68` | `sw $v0, 0x1F68($at)` | the **base**, `0x801659D0` — `load_vram_rect_ptrs` |
| 3 | `0x80015FE0` | `0xAC251F68` | `sw $a1, 0x1F68($at)` | an **advanced** cursor — `decompress_player_gfx` |

Denominators, all measured over the whole `.text`:

* **12** store instructions have a displacement in `[0x1F60, 0x1F70]`. Exactly **3** of them have
  `0x1F68`; the other **9** all have `0x1F6C` and target `0x80141F6C`, the word *after* the cursor.
* `addiu $r, $r, 0x1F68` — the "build a pointer, then store at 0(reg)" formation — occurs **0**
  times.
* The value `0x80141F68` appears **0** times as word-aligned data anywhere in the image, in either
  byte order. **So no statically formed pointer to the cursor can exist**, which is what bounds the
  one case the displacement scan cannot cover (a store through a pointer computed at runtime).
* All three writers use base register `$1`, and each is reached with `$1` holding page `0x8014` —
  checked by reading the preceding `lui` and stopping at the enclosing `jr $ra`. Without that, the
  scan proves only a *displacement* of `0x1F68`; `0x00141F68` has the same displacement. The
  selftest's 8th case is what caught that hole, and closing it added the check.

Call-site census, also from bytes: `clear_vram_rect_ptrs` has **exactly one** caller
(`0x800120D0`), `load_vram_rect_ptrs` **exactly one** (`0x800120FC`), both in the main loop
`0x80012024`; `decompress_player_gfx` has **17**.

The appender's loop, `0x80015F74`–`0x80015FD4`, exits on `bnez` of `size << 16` at `0x80015FD0`
and nowhere else — no comparison against 8, against `base+0x60`, or against the record array.
`size` is `$16 = unk38[cur_anim] >> 20` (`srl` at `0x80015F20`).

## 2. The runtime measurement, and why it is the right instrument

`PSXPORT_STORE_OBSERVE` armed on those three **store PCs** — the correct use of it, and the
opposite of the mistake 0032 records, which armed data addresses. `game/core/main.cpp:103` already
calls `store_observe_attach`, so the observer is armed on this title's own spine.

Run: headless, silent, unpaced, no debug server, `PSXPORT_NATIVE_FRAMES=40000`,
`PSXPORT_DEBUG=store-observe`. `tools/live_play.py` cannot produce this measurement: it ends its
runs by signalling the product (`exited 130` measured), and a live endpoint's presence *lifts* the
headless frame cap, so the product ran past the budget and died at the fault instead of exiting
normally. `scratch/vramrect_probe/run_observer.py` exists only to drop the endpoint and let the
product exit at its cap.

| store PC | executions | return address seen |
|---|---|---|
| `0x80015E18` clear | **60** | `0x800120D8` ×60 — the port's own retail return address |
| `0x80015EB0` load | **59** | `0x80012104` ×59 — likewise |
| `0x80015FE0` **the writer** | **9** | `0x80015F5C` ×9 — inside the appender itself |

The counts are real observations, not a guaranteed answer: the same arming, in the same run, saw
the other two PCs 60 and 59 times. A shorter 1,200-field run saw 15/14/**0**, so the writer's nine
executions are all in the fatal field.

**The nine appends, in order, with `$4` read from the observer** (`$4 = gfx + 6` inside the
appender, so `N = (a0 - base - 6) / 12` is the cursor position after the call):

| # | `$a0` | cursor after | # | `$a0` | cursor after |
|---|---|---|---|---|---|
| 1 | `0x801659E2` | base+1 | 6 | `0x80165A1E` | base+6 |
| 2 | `0x801659EE` | base+2 | 7 | `0x80165A2A` | base+7 |
| 3 | `0x801659FA` | base+3 | 8 | `0x80165A36` | base+8 |
| 4 | `0x80165A06` | base+4 | 9 | `0x80165A42` | base+9 |
| 5 | `0x80165A12` | base+5 | | | |

So: **nine calls, each advancing the cursor by exactly one 12-byte entry, consecutively, with no
clear between them, ending at `base + 9*12 = 0x80165A3C`** — which is byte-for-byte the cursor
value 0032's RAM dump recorded, and the 9th record at `base + 8*12 = 0x80165A30` is
`item_objects[0]`, exactly as recorded there. Two independent instruments, same number.

Nine calls advancing the cursor nine times means each call emitted **exactly one** band, i.e.
each call's `size` was `< 16` and took the `size < 16` arm. The overrun is therefore **nine
objects each decompressing one 16-pixel band in a single field**, into an eight-entry array.

The fault reproduced identically: `vblank=0x0000734A`, `r2=0x26010006`, `r4=0x80165A30`,
`r31=0x800BEBEC`, `r17=0x800F2910`, and the same `a0` argument record
`40 01 00 00 40 00 20 00 A8 DE 16 80`. `0x734A` = 29,514 vblanks ≈ 14,757 presented frames at the
repo's already-measured 2× display-clock rate, which is 0032's 14,756.

## 3. Does retail overrun too? What decides it — and what is still not answered

**What the image settles.** The array is bounded at eight in two places and the appender is
bounded nowhere. The bound is a *convention the guest states and relies on*, not one it enforces.
The only thing keeping the array intact is that the guest's own per-field band count stays ≤ 8.
Nothing in the image checks.

**What the measurement settles.** That count is **9**, made of 9 calls × 1 band. It is
data-driven twice over: which objects call is `unk47 != unk48` on the object, and the band count
is `unk38[cur_anim] >> 20`. Both are guest state.

**What decides retail parity, precisely.** Whether retail's per-field count is also 9. That is a
property of retail's object and stage state in that one field, and **one image cannot answer it**,
because the answer is a runtime count, not a byte in the file. So the honest statement is:

* If retail's count in that field is ≤ 8, this is a port divergence and the next step is to find
  which object's animation is changing that it should not.
* If retail's count is 9, retail overruns identically — the 9th record lands on `item_objects[0]`,
  `0x800BEBB4` reads its `rect.w` as a state index and calls table entry 9×8=72 — and this is
  **not the port's defect at all**.

**What is therefore still open, named rather than guessed:** the *ordering* question. The fault
needs `update_item_objects` to dispatch on the corrupted record in the same field the appends
wrote it. In the port the sequence inside the fatal field is: clear → nine appends → dispatch →
fault, with the load never reached. Whether retail's `func_80012600` chain reaches
`update_item_objects` before or after the 17 appender call sites — and whether retail spreads the
nine over two fields — is not established here, and it is the next measurement, not a conclusion.

A live suspect exists and is **not** being claimed: the repo already records that the guest's
display-field clock runs at **2× the presented cadence** (issue 0028), which this run corroborates
(29,514 vblanks ≈ 14,757 presented frames). An animation clock advancing at 2× would make
`unk47 != unk48` fire more often than retail. That is a lead, and it is recorded as one.

## 4. The fix: none in this repository, and why that is the correct outcome

**No product code was changed, and none should be until §3's ordering question is answered.**
Writing a guest byte to stop the fault, widening the array, or clamping the cursor would each hide
the symptom while leaving the cause — whatever produces a ninth band — untouched. That is the tap
this workspace treats as its worst outcome, and the discipline is not to reach for it while the
cause is still open.

## 5. The framework finding, reported rather than patched

`psxport` is not mine to edit. Two things belong there, with evidence.

### 5.1 `PSXPORT_WWATCH` structurally cannot see a translated guest store to main RAM

This is the gap that made 0032's writer unlocatable, and it is not a window or a range mistake.

* `Core::writeGuestMemory` (`runtime/psx/guest_memory.cpp:75`) calls `wwatch_check`, and
  `mem_w32` is its only guest-store entry point.
* `runtime/cpu/lightrec_executor.cpp:121` registers `storeWord` → `Core::mem_w32` as
  `lightrec_mem_map_ops::sw`.
* But `rec_store` in the built Lightrec (`shared/lightrec`, `3fddb23`) routes
  `LIGHTREC_IO_RAM` and `LIGHTREC_IO_DIRECT` to `rec_store_ram` / `rec_store_direct*`, which end
  in `jit_new_node_ww(code, imm, addr_reg2, src_reg)` — a **direct host store into the RAM array**.
  The `mem_map` callbacks are reached only for `LIGHTREC_IO_DIRECT_HW` (I/O registers), for
  addresses the optimiser could not classify, and on interpreter-fallback paths.

So `PSXPORT_WWATCH` observes I/O-register stores, unclassified stores, interpreter-fallback
stores, and host-side stores from native code, DMA and loaders. It does **not** observe translated
stores to main RAM. 0032's run is exactly what that predicts: 6,184 stores logged, the single hit
on `0x80141F68` from crt0's BSS clear, which runs before the guest is translated.

**Proposed:** state this in `PSXPORT_WWATCH`'s help text, in the same sentence as the existing
`pc`/`ra` and start-address warnings, that a zero from it does **not** mean "no guest CPU store
touched this word" — only "no store on a path that reaches `Core::mem_w32` did". Better still,
have the log line print that limitation whenever it reports zero hits, so the negative cannot be
read as the other question.

### 5.2 The store observer's report is unreachable on this title, even on a clean `exit 0`

`store_observe_report` is called from `~LightrecExecutor`
(`runtime/cpu/lightrec_executor.cpp:523`), and the comment there says this placement was chosen
precisely because "the report is emitted from the teardown that every exit path reaches". Measured
on this title, **it does not**: a run that exited **0** with the frame cap reached printed its
`store-observe` arming lines and no report at all, and no `Lightrec fallback telemetry [shutdown]`
either — so the executor's destructor is not reached on this title's exit path. That is the same
class of defect the comment describes having been fixed once already, in a different direction: the
report moved to a teardown, and this title does not have that teardown.

**Proposed:** emit the report from a path this title actually reaches — the same place the run-end
line and the `env audit AT EXIT` are printed — or make `~Core` reach the executor's teardown.
Until then the observer's only usable output is the live `store-observe` channel, which is how §2's
counts were obtained and is the workaround worth documenting.

**No covering-store or DMA/host-side observer is proposed.** It is not needed: the writer was
reachable by reading the image, and §1 shows that the *static* route is the cheap one. A new
instrument would have been the wrong call.

## 6. What the gate holds

`tools/verify_stage_fault.py` grows from **38 comparisons to 47**, and its `--selftest` from
**5 mutations to 9**:

* the exhaustive writer scan (12 in the displacement window, exactly 3 on the cursor word, the
  three sites named, all on base register `$1` reached with page `0x8014`);
* the pointer case bounded (0 occurrences of the cursor address as data, 0 `addiu` formations);
* four new negative cases — retarget the appender's publish, **plant a fourth writer**, move the
  base page, plant a static pointer.

The "plant a fourth writer" case is the one that matters: it proves the scan counts writers rather
than recognising a known list of three.

**`--selftest: 9/9`, `--check: 47/47`, `ctest -R stage_fault_evidence`: 1/1.**

`ctest --test-dir build` → **33/34**. The one failure is `megamanx4_psxport_pin_live`, reporting
"framework is dirty or changed since configure (configured `0aef9d60`, current `0aef9d60`)". The
commits match; the tree is dirty because of an **untracked `psxport/tools/pin_round.py`**
(mtime 05:30, before this session began). That is not a regression from this work — this
repository's only modified file is `tools/verify_stage_fault.py`, and no framework file was
touched. It is reported, not fixed: the fix belongs to whoever owns the pin, and the brief forbids
touching it.

## 7. What remains

1. **The ordering question in §3** — does retail reach `update_item_objects` before or after the
   appender call sites in that field? This decides whether there is a port defect to fix at all.
2. **The per-field count** — whether retail's is also 9. One image cannot answer it; a second
   observation of the same field would.
3. **The 2× display clock** (already recorded in issue 0028, corroborated here) is a live suspect
   for an inflated animation-change count, and is uninvestigated.
4. **The 60/59 resets in ~14,757 fields.** A real divergence from retail's main loop — retail calls
   both once per field, unconditionally — and *not* the cause of this fault. It is its own
   measurement, and it matters because the same skip would let the cursor accumulate on any field
   where appends do occur.
5. **S009** unchanged and `missing`. See §8.

## 8. How far the game gets, and the scene question

Unchanged, because no product code changed. The fault still ends every run, now measured at
`vblank=0x0000734A` ≈ presented field **14,757**. Boot, CAPCOM intro and both authored STR movies
complete; the title front end and the post-park transition are reached. **No scene with more than
2 submitted prims is reached**, and no capture of one exists — the same `NOT SCENE` result 0028
recorded, with the blocker now named rather than open-ended.
