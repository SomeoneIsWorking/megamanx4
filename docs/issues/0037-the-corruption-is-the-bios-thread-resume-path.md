---
id: 37
title: The corruption is the BIOS-thread budget RESUME path, and the bad address is never at rest anywhere
status: open
symptom: The build stops with guest address 0x0113D7D0 "resolves to zero or multiple active code images"
state_items: S002
tags: megamanx4,bios,threads,resume,executor
created: 2026-09-29
updated: 2026-09-29
---

## CORRECTED BY THE PRODUCT RUN — the boundary defect was REAL and is FIXED, but it is NOT the cause of `0x0113D7D0`

**The claim in the heading above is falsified.** The boundary defect was genuine, the repair works,
and the decompress call now returns correctly — but the corruption survives the repair, so the
boundary was a second defect, not this one.

**What the repair verifiably achieved.** The decompress call now runs with the boundary the image
implies and COMPLETES:

    before:  guest call 0x80016FF4 to return address 0x80022060   <- inherited, unrelated `jal`
    after:   guest call 0x80016FF4 to return address 0x80015F5C   <- `jal 0x80016FF4` at 0x80015F54, +8

Both before and after it reports `2 turn(s), 757804 cycles total` and is counted as completed
(`2 of 46715 completed guest call(s) have needed a resume`). The call genuinely is that long, and it
now returns at the right place instead of running past its own end.

**And the corruption is still there, through a different call.** Naming the entry (a diagnostic added
for exactly this, because the owner-only message could not say which entry had faulted) gives:

    [x4-guest:error] guest call 0x80012600 exited fault at 0x0113D7D0 after 0 cycles, and this
                     owner has no return point for it: ambiguous code-image identity

**`0x80012600` is `kUpdateTasks`** — the retail task scheduler, dispatched by the frame driver. It
faults **within its first host turn**, so this is not a boundary consulted across a resume; it is the
guest jumping to a non-address from inside the scheduler. That is the BIOS-thread `ChangeTh` /
fiber-switch path the original frontier pointed at, and it is where the frontier now belongs.

**So the honest position is two findings, not one.** A real, measured, fixed defect in how a native
owner obtained a return boundary; and an unexplained corruption that predates it, still live, and now
localised to the task scheduler. The second was never caused by the first.

## The next step, named

1. **The scheduler, not the boundary.** `0x80012600` chooses a task and calls `ChangeTh`
   (`0x800EDDBC`); the fault is 0 cycles after entering it. Instrument the `ChangeTh` fiber switch to
   report the register file it resumes a task with, specifically the task's `r[31]` and `pc` — the
   same census that refuted the stale-`$ra` hypothesis here should be pointed at the switch itself,
   because `Service::open` sets `r[29]`, `r[28]` and `pc` and never `r[31]`.
2. **Supply boundaries for the remaining native-owner calls**, so the refusals become working calls.
   `tools/census_guest_call_sites.py` has the candidates: `kAppendBandsGuest` (0x80015ECD) has **no**
   `jal` site at all, so it needs a pointer/`jalr` reachability answer before a boundary can be
   derived for it; the `display_init` and `music_stream` entries have 2-24 sites each and the owner
   must name which one it stands in for.
3. **Widen `GuestDispatch` to carry the return address.** Five headers each declare their own
   `using GuestDispatch = void (*)(Core *, std::uint32_t);`, so a boundary cannot travel with a
   dispatch today, which is why `callWithRegisterReturn` exists as a verified-register compromise.
   One typedef, one owner, and the return address becomes impossible to drop.
4. Keep the boundary gate. `tools/census_guest_call_sites.py --verify-boundaries` re-derives the two
   hard-coded constants from the image and was confirmed red on a mutated constant; it is what stops
   a future edit from silently restoring the defect this repair removed.

## CORRECTION THE PRODUCT RUN FORCED — the boundary was NOT the cause of `0x0113D7D0`

**The section below claims the boundary was the root cause of the corruption. That claim is wrong,
and the disc-backed product run falsified it.** The boundary defect was real and the repair works — the
decompress call now returns at `0x80015F5C` instead of inheriting `0x80022060` — but `0x0113D7D0`
survives the repair, arriving through `guest call 0x80012600`, which is `kUpdateTasks`, the retail
task scheduler the frame driver dispatches. It faults **0 cycles** into its first host turn, so it is
not a boundary consulted across a resume at all: it is the guest jumping to a non-address from inside
the scheduler, which is the `ChangeTh` fiber-switch path the original frontier named.

**Two findings, not one: a measured and fixed defect in how a native owner obtained a return
boundary, and an unexplained corruption that predates it, still live, and now localised to
`0x80012600`.** What follows is kept because the boundary defect was real and the evidence for it
stands; what it does not establish is that it explained the corruption.

## MEASURED 2026-09-29 — ROOT CAUSE (SUPERSEDED BY THE RUN ABOVE): a NATIVE owner calls `x4::guest::call`, which takes its return boundary from `core->r[31]`

**The prediction that failed first, because the record should show the refutation.** The hypothesis
above was a stale `$ra`. `guest_execution.cpp`'s census now classifies the link register at the
instant of every resume, using `Core::currentImageIdentity` — the framework's own rule, and the same
criterion the fault message quotes. A 20,000-field run reported:

    guest call 0x800ED574 to return 0x80018AA0 ... 1 of 278 completed guest call(s) resumed
      Link register at the resume point: 1 in a code image, 0 in RAM outside one, 0 outside RAM
    guest call 0x80016FF4 to return 0x80022060 ... 2 of 46715 completed guest call(s) resumed
      Link register at the resume point: 2 in a code image, 0 in RAM outside one, 0 outside RAM

**Both resume points carried a valid code address, so the stale-`$ra` mechanism is REFUTED** — exactly
as this file's own falsifier said it would be. Two useful denominators fell out: only **2 of 46,715**
guest calls ever need a resume, and the first is `0x800ED574` at 610,746 cycles, which matches the
`DecDCTvlc` figure already recorded in `bios_threads.cpp`.

**The boundary, not the link register, is the defect.** `x4::guest::call` derives its return boundary
from `core->r[31]`:

    const std::uint32_t returnPc = core->r[31];

Its comment states the assumption — "the caller's `r[31]` as the FIRST segment saw it ... keeps a
resume from adopting the nested `r[31]`" — and the assumption holds **only when guest code executed
the `jal`**. A **native owner** invoking the same helper inherits whatever link register the guest
happened to leave, and that stale address becomes the boundary the call must reach to return.

**And the faulting call is exactly that case.** `0x80016FF4` is `kDecompressGfxGuest`, the RLE
decompressor, and `vram_rect_queue.cpp` calls it from host C++:

    runGuest(core, kDecompressGfxGuest, stream, buffer, caller);

with the comment "`jal 0x80016FF4` at `0x80015F54`" — so the owner's own real return point is
**`0x80015F58`**. Decoding the boundary it actually got:

    80022058  jal   0x80015ecc      <- an UNRELATED guest call
    8002205C  move  $a2, $zero
    80022060  lw    $ra, 0x14($sp)  <- the boundary the call was given

**`0x80022060` is the return address of a different function's `jal 0x80015ecc`.** It is not a return
point for a call to `0x80016FF4`, and the decompressor cannot reach it by returning. So the call does
not return: it runs on past its own end through code it was never meant to execute, consumes 757,804
cycles over 2 host turns, and faults at `0x0113D7D0` — a value produced by code running past its
intended boundary, which is also **why that value is never at rest anywhere**.

**This accounts for every earlier observation at once**: the fault after a long call rather than at a
branch, the valid link register at the resume, the value absent from the image, from the class-0
table, from four RAM regions and from the task stack, and the 0-cycle fault (a fetch, not a
computation).

**The fix direction is now well-posed and the owner already holds the answer**: a native-owner
initiated guest call must supply the return point its own call site implies (`0x80015F58` here), not
`core->r[31]`. That is a real behavioural repair, so it is recorded rather than applied in the same
breath as the measurement, and it needs a regression test that fails today.

## What this does that the earlier frontier did not

Issues 0036 and 0037 established that `0x0113D7D0` is **nowhere at rest**: not in the image, not in the
class-0 table, not in three live RAM windows. That left the question "what computes it" with no
mechanism attached. `PSXPORT_DEBUG=x4-thread` turns on `Service::open`'s own `lucent::debug` line, which
logs every BIOS thread activation with its entry, SP and GP — **the instrument was already in the
shipping code and nobody had switched the channel on.**

The run narrows the fault to a specific port-owned path.

## MEASURED — the last four events before the fault

    OpenTh handle=0xFF000001 entry=0x8001DAF8 sp=0x801FEC00 gp=0x00000000
    ChangeTh main -> 0xFF000001 entry=0x8001DAF8 sp=0x801FEBC8
    ChangeTh main -> 0xFF000001 entry=0x8001DAF8 sp=0x801FEB58
    retail task entry 0x8001DAF8 ... was RESUMED at 0x800EA0F4 after 564486 cycle(s) in that turn.
      Denominator: 1561 of 13420 task turn(s) have needed a budget resume, 881179244 guest cycle(s)
      over them; the other 11859 reached a guest field boundary
    [native-dispatch:error] guest address 0x0113D7D0 resolves to zero or multiple active code images
    [executor:error] ... execution exited as fault at 0x0113D7D0 after 0 cycles

**The chain is task -> budget resume -> BIOS-range address `0x800EA0F4` -> fault at `0x0113D7D0`.**
`0x800EA0F4` is in the BIOS range and is **not** an entry the port's BIOS table names (it knows
`PutDispEnv` 0x800EAAD8, `DrawSync` 0x800EA20C, `LoadImage` 0x800EA4D0, and others). The turn after
that resume consumed **0 guest cycles**, which is the signature of a jump to a non-code address
rather than of code that ran and went wrong.

## The seam, which is the actual finding

`game/core/bios_threads.cpp` takes the resume address from the executor's own exit report:

    resumeAddress = result.guestPc;
    suspended = true;

and its only guard on that value is `result.cycles == 0u || result.guestPc == 0u` — a **non-zero**
check. There is no check that the resume address is a guest **code** address. A value like
`0x0113D7D0` passes that guard and is handed straight to `psx::cpu::resumeGuestToReturnFrom` on the
next turn, which is where the framework's `ambiguous code-image identity` comes from.

**So the port-owned seam through which a non-address becomes an execution target is identified, and it
is a missing predicate rather than a wrong computation.** The code already knows the difference
matters — it aborts on a zero PC for exactly this reason — and stops one predicate short.

**This is NOT yet a fix, and the reason matters.** Adding "is this a code address" as a check would
turn a diagnosable fault into a refusal, and would not say where the value came from. The correct
fix is upstream of the seam: find why the executor reported `0x0113D7D0` as `guestPc` after a resume
into `0x800EA0F4`. Recorded as the next step, not applied.

## Two more measured facts about the activations

* **Every activation passes `gp=0x00000000`.** All five `OpenTh` calls in the run log
  `gp=0x00000000`, from a0=entry, a1=sp, a2=gp. The BIOS contract's third argument is documented in
  the owner as the global pointer. Either this guest never uses `$gp`, or it is passing zero where
  retail passes a real value, and any `$gp`-relative access in a task would then read from address 0.
  **Not established which**, and it is a separate question from the fault.
* **Task `0x8001DAF8` never retires, and its SP descends monotonically**: 0x801FEC00 -> 0x801FEBC8 ->
  0x801FEB58 across three `ChangeTh main ->` transfers, with no `RETIRED` line for that entry
  anywhere in the run. The task is being re-entered without ever reaching its activation's return
  address.

## The value is still nowhere at rest — now over four regions

`tools/probe_class0_table.py` was re-pointed at the **task stack**, which the earlier scans never
covered: the activations log `sp=0x801FEC00` and descending, and the earlier ranges were
0x8011C000, 0x801F8000 and 0x80139000.

    34 ticks x 1,280 word-reads = 43,520 word-reads, presented frames to 13,163
    regions: 0x8011C000..0x8011C200, 0x801FE000..0x801FE200, 0x801F8000..0x801F8200,
             0x80139000..0x80139100
    0x0113D7D0 present at 0 of 43,520

The product still exited at the fault (the probe's `RC=1` is its BrokenPipe on the dying child, not a
scan failure). **So a stale return address read off the task's own stack is refuted** — that was the
most likely mechanism for a fiber-resumed guest task, and it is not it.

## CORRECTED THE SAME DAY — `0x800EA0F4` is NOT shown to be the culprit, and my own falsifier fired

**AND THE CLASSIFICATION UNDERNEATH THIS IS ALSO WRONG — see `psxport/docs/issues/0038`, which
records the refutation.** `0x800E0000..0x80100000` was called "the BIOS range". It is not: the EXE
loads text at `0x80010000` size `0x11F800`, so the image spans `0x80010000..0x8012F800` and
**contains that range entirely**. `0x800EA0F4` decodes as a guest byte-getter ending in `jr $ra`, and
`0x800ED744` as mid-function decoder code. So the table below has **overlapping buckets** and its
300/1,261 split is an artifact; the only honest reading is that **1,561 of 1,561 resumes land inside
the loaded guest image**.

What survives from this section: the leaf at `0x800EA0F4` ends in `jr $ra`, so **the continuation after
a resume that lands there is the task's `$ra`** — and `Service::open` never initializes `r[31]`.

## The paragraph below assumed a range boundary; it is kept because the wrong premise is the attractive one

The paragraph above reads as though the resume into `0x800EA0F4` is the causal link. **The log does
not support that, and the falsifier written into this file fired.** All 1,561 budget-resume lines
from the run, classified by where the resume address lands:

| resume address lands in | count | share |
|---|---|---|
| BIOS range `0x800E0000..0x80100000` | **1,261** | **80.8%** |
| game text `0x80010000..0x8012F800` | 300 | 19.2% |
| anywhere else | 0 | 0% |

Distinct BIOS-range resume addresses, with counts:

    0x800ED744 x583   <- a KNOWN framework BIOS constant
    0x800ED7A0 x349
    0x800ED628 x115
    0x800ED7C8 x80    0x800ED7A4 x42    0x800ED784 x26
    0x800ED730 x24    0x800ED828 x23    0x800ED700 x13
    0x800EA0F4 x6     <- NOT a known entry

**So "the fault followed a BIOS-range resume" carries almost no information** — four in five resumes
land there. And `0x800EA0F4` is **6 of 1,561, 0.38%**, not a unique event: the same address was
resumed five earlier times in this run without faulting. The chain in the previous section is
therefore **temporal, not causal**, and this file's earlier phrasing overstated it.

**What survives is structural, and it is a different and better claim.** Four in five budget resumes
land at a BIOS address, and this title's BIOS is **HLE'd with no ROM** — there are no BIOS bytes to
execute, so a BIOS address is an *HLE entry point*, not a place execution continues from. Yet
`resumeGuestToReturnFrom` is handed that address as `resumeAddress`, the **continuation point**. The
question worth asking is not "why 0x800EA0F4 this time" but **"what happens when a resume
continuation is an HLE entry rather than a mid-function guest address"** — and 1,261 of 1,561
measured resumes are exactly that case. `0x800ED744` at 583 occurrences is a known entry, which
suggests the common path re-enters HLE and recovers; the 6 occurrences of an *unnamed* address are
the interesting minority.

**The port-owned seam reading is unaffected and still stands**, because it is a statement about code
rather than about this run: `resumeAddress = result.guestPc` is guarded only by
`result.guestPc == 0u`. What changed is the confidence in `0x800EA0F4` specifically, which is now
recorded as incidental.

## The next step, named

1. **Ask the structural question, not the address question**: 1,261 of 1,561 resumes continue at an
   HLE entry rather than mid-function. Establish what a resume does when its continuation is an HLE
   entry — specifically whether it re-enters the HLE with `$ra` unchanged, and where the HLE then
   returns to. A guest `$ra` that is stale inside a `ChangeTh`/fiber task is the most likely source
   of a non-address, and it is consistent with the task's SP descending without ever retiring.
2. **The 6 unnamed resumes are the minority worth keeping.** Instrument the resume path to REPORT a
   continuation that is not a known BIOS entry and not in loaded text, with a count. That is a
   diagnostic with a denominator, and 0.38% is the number it would be watching.
3. **Only then decide the seam's predicate.** The `guestPc != 0` check is the place a non-address gets
   to become a target, and tightening it is a refusal, not a repair.
4. **Answer the `gp=0` question** independently. Five of five activations pass a zero global pointer.
5. Keep the `x4-thread` channel in the standing probe set. The fault's neighbourhood was in the
   shipping debug channel the whole time; the earlier frontier spent its effort on a static image scan
   of a value that is never in the image.

## Falsifier

* **FIRED, and the result is in the correction above.** The falsifier asked whether the
  `0x800EA0F4` link was incidental. It is: 6 occurrences in 1,561, five of which did not fault, and
  80.8% of all resumes are BIOS-range.
* The structural claim stands or falls on its own measurement: if a resume whose continuation is a
  known HLE entry (`0x800ED744`, 583 occurrences) provably re-enters and recovers, then the HLE
  entry path is sound and the 6 unnamed continuations need their own explanation. If it does NOT
  recover cleanly, the 1,261 are all latent instances and the fault is the common case, not the
  sixth occurrence.
