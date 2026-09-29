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

## MEASURED 2026-09-29 — the fiber SWITCH is refuted too: 14,000 resumes, 0 with an unusable register

The next step named above was to point the register census at the `ChangeTh` fiber switch itself,
because `Service::open` writes `r[29]`, `r[28]` and `pc` and **never `r[31]`**. That census now ships
in `bios_threads.cpp` and reports on a stride, so a run that never trips it still says how much it
scanned.

    fiber-switch census: 14000 task resume(s) scanned; 14000 resumed with a pc inside a code image,
    0 with one outside EVERY code image; of their link registers, 3 were zero (`Service::open` never
    initialises r[31]), 13997 were in a code image and 0 were not

**So the switch is sound on both registers that matter, and it is not the source.** Every one of
14,000 task resumes loaded a `pc` that resolves in a code image, and no link register was outside one.

**The "3 were zero" is a measured confirmation, not a fault.** Those are the first resumes of tasks
that have not yet executed a `jal`, so `r[31]` is still the zero `Service::open` left in it — which
is exactly why the census reports the zero case separately instead of folding it into "not a code
image". They are benign: the task sets the register before it returns through it.

**Where this leaves `0x0113D7D0`.** Not the boundary (fixed, and the fault survives that fix), not
the saved `pc`, not the saved `r[31]`. The task resumes valid and then, somewhere in its own guest
execution, jumps to a non-address. Catching that means watching the VALUE rather than the two
registers at a switch — a store observer or a register watchpoint on `0x0113D7D0` appearing in any
register — because every structural register the port owns is now measured sound at the point where
it hands control to the guest.

## MEASURED 2026-09-29 — not in a register either, and the RAM scan is measurably too slow to find it

The switch census left one place the port does not own: the value itself. The `x4-guest` refusal now
scans the whole register file at the fault and names any register that already holds the faulting
address.

    guest call 0x80012600 exited fault at 0x0113D7D0 after 0 cycles ... 0 of the 32 general
    registers already hold that address
    register file at the fault: r0=0x00000000 r1=0x80200000 r2=0x801F8300 r3=0x00000001
      r4=0x00000000 r5=0xFFFF0000 r6=0x80139554 r7=0x00000000 r8=0x80166D14 r9=0x0000002A
      r10=0x000000A0 r11=0x00000000 r28=0x8012F418 r29=0x801FFFE0 r30=0x80200000 r31=0x800120EC

**`r31 = 0x800120EC` independently confirms the call site.** That is `PC + 8` for the `jal 0x80012600`
at `0x800120E4` — the one static caller found in issue 0036 — so the guest is genuinely inside the
scheduler, reached the documented way, not by a route nobody accounted for.

**And the faulting address is in no GPR.** It is `core.pc`, not a register, so that negative is
expected rather than surprising — but it does mean the value is not sitting in a register at the
moment of the jump, which narrows the mechanism to a **branch target** computed by guest code inside
the scheduler. A `lui`/`ori` pair immediately followed by `jr` would still leave the value in a
register, so whatever produced `0x0113D7D0` did not leave it there.

**The RAM scan that would find it is NOT feasible with this instrument, and the arithmetic is worth
recording so nobody re-derives it.** Guest RAM is 512,000 words; the `rw` endpoint's measured cost is
**~18 presented frames per 64-word read**, so full coverage needs 8,000 reads ≈ **144,000 frames** —
against a run that faults at **~13,400**. A sliding-slab probe was built and MEASURED to confirm the
rate rather than assume it: 16,384 words per tick, ticks arriving every ~4,500 frames, reaching only
~3% of RAM before the product ends. **The earlier four-window scan covered 43,520 words — under 1% —
so its clean result never supported "it is not in memory", and this issue is not to be read as
having claimed that.**

## MEASURED 2026-09-29 — the scheduler DECODED: it is a polling loop over a cursor that points at ITSELF

Decoded from the authenticated image with `psxport/tools/disasm.py` (28/28, 32/32, 28/28 and 12/12
words across four windows, zero unknown). `0x80012600` is not a dispatcher in the sense the issue
assumed; it is a **bounded polling loop over a cursor at `0x801F8300`**.

    80012618  lui   $s0, 0x801f
    8001261C  ori   $s0, $s0, 0x8300      ; $s0 = 0x801F8300, the cursor
    8001262C  lui   $a0, 0x8020
    80012630  lw    $a0, -0x7d00($a0)     ; $a0 = *(0x801F8300)
    80012638  lhu   $v1, ($a0)             ; the STATE, a halfword read AT the cursor
    8001263C  addiu $v0, $zero, 2
    80012640  beq   $v1, $v0, 0x80012698   ; state == 2  -> ChangeTh
    80012648  beqz  $v0, 0x80012660        ; state < 3
    80012650  beq   $v1, $v0, 0x8001267C   ; state == 1
    80012664  beq   $v1, $v0, 0x80012698   ; state == 4  -> ChangeTh
    8001266C  beq   $v1, $s1, 0x80012698   ; state == 0x7f -> ChangeTh

and the loop tail:

    80012710  lw    $v0, ($s0)             ; re-read the cursor
    80012714  ori   $v1, $v1, 0x82ff       ; $v1 = 0x801F82FF
    80012718  addiu $v0, $v0, 0x80         ; cursor += 0x80
    8001271C  sltu  $v1, $v1, $v0
    80012720  beqz  $v1, 0x8001262c        ; cursor < 0x801F8380 -> re-read the state
    80012724  sw    $v0, ($s0)             ; else store it and return via `jr $ra`

**So `0x801F8300` is a CURSOR, not a state variable — and in this run it holds `0x801F8300`, itself.**
The probe measured that value at every tick, and `r2` at the fault is the same `0x801F8300`.

**Which means the "state" the state machine reads is the cursor's own low halfword: `lhu` at
`0x801F8300` yields `0x8300`.** None of the four branches handles `0x8300` — not 1, not 2, not 4,
not `0x7f` — so the fall-through runs, reaches `0x80012710`, advances the cursor by `0x80` to
`0x801F8380`, finds `sltu` false, and **returns without ever calling `ChangeTh`**.

Two consequences, both measured rather than inferred:

* **The scheduler does not dispatch tasks from this state.** The `ChangeTh` paths at `0x80012698`
  are unreachable while the cursor points at itself, which is consistent with the task's SP
  descending across repeated `ChangeTh main ->` transfers without ever retiring — something else is
  driving the fiber switches, not this state machine's `ChangeTh` branch.
* **A cursor that points at itself is a defect on its own terms**, whatever the fault: the record
  pointer the guest is iterating is its own storage, so the table it walks is not a table. This is
  the first thing found in this investigation that is wrong in the GUEST's data rather than in the
  port, and it is the thing to check first from here.

**This does not yet account for `0x0113D7D0`.** With state `0x8300` the scheduler's path returns
cleanly through `jr $ra` to `0x800120EC`, which is consistent with `r31 = 0x800120EC` at the fault and
means the fault is NOT on the state-`0x8300` path. It narrows the search to the paths that *do*
dispatch, and it gives a new, cheaper question: **why does the cursor at `0x801F8300` hold a
self-reference?**

## MEASURED 2026-09-29 — the self-pointer is REAL, it is heap, and the guest's only store to it NEVER RUNS

Four measurements, each with a control, because the first two could both have been artifacts.

**1. The reading is not the endpoint echoing the address it was asked for.** The first version of the
probe read `0x801F8300` alone. The control is its *neighbours*: an endpoint that answers an unmapped
address with that address would produce the identical line. Reading the neighbourhood settles it:

    spot 0x801F8300=801F8300  0x801F8304=00000000  0x801F8308=00000000  0x801F8380=00000000
          0x80139554=00000000

The neighbours read zero and do **not** echo themselves, so `0x801F8300` genuinely holds
`0x801F8300` — and the whole `0x80`-byte record the cursor steps through is otherwise zero.

**2. It is HEAP, and no port code writes it.** The loaded image ends at `0x8012F800` and the
crt0-zeroed `.bss` is `[0x8012F418, 0x80175F38)`, so `0x801F8300` is in neither — above the heap base
`0x80175F38`, below the stack top `0x801FFFF0`. Grepping the title for `0x801F83*` returns
**nothing**, and the port has **no allocator at all**, so a free-list explanation is refuted before it
was proposed.

**3. The guest's only store to that address never executes.** A register-tracking scan of all 294,400
text words — requiring the store's *base register* to hold the target with offset 0 — finds **1**
store, the scheduler's own `sw $v0, ($s0)` at `0x80012724`, and **0** of them store the
self-reference. (The first version of this scan was loose: it accepted any `sw` within five
instructions and matched `sw ..., ($sp)`, reporting three "writers" that were stack saves. The
corrected version has the OPPOSITE failure mode — it can miss writers reached through a loaded
pointer, which is exactly what is left.)

**4. And that store genuinely does not run — verified with an instrument proven to fire.**
`PSXPORT_STORE_OBSERVE=0x80012724` reports **no events** across a 20,000-field run. A zero from an
unproven instrument means nothing, so it was re-armed on the scheduler's own prologue store
`0x80012620`, which must run, and it fires immediately:

    [store-observe] guest_pc=0x80012620 phase=before cycle=16 a0=0x00000000 t0=0x80166C74
      t1=0x0000002A gpr[29]=0x801FFFC0 gpr[31]=0x800120EC seen=1

So the silence at `0x80012724` is real: **the cursor is never advanced by the guest.**

**Which leaves one sharp open question.** Nothing in the port writes `0x801F8300`, the guest's only
tracked store to it never runs, and it is not zero. So either a store reached through a **loaded
pointer** wrote it — invisible to a `lui`/`addiu`/`ori` chain scan — or the word predates the run. Note
too that the observer's dump shows the scheduler running early with `t0 = 0x80166C74` / `0x80166D14`,
which look like **record pointers**, so the cursor may be a valid pointer when the scheduler actually
runs and only self-referential later; the probe sampled it at frame 13,163 and **no measurement yet
covers the moment the scheduler executes**.

### A trap this section walked into, recorded because the map already warns about it

`PSXPORT_STORE_OBSERVE` takes **store-instruction PCs**, and says so on arming: *"These are the PCs OF
STORES, not the guest words they write."* It was first armed with `0x801F8300` — a **data** address.
That is the exact error `WORKSPACE.md` records as having happened before ("arming the store observer
on a data address and reading the guaranteed `MATCHED NONE` as absence"), and it would have produced a
clean, confident, meaningless zero. It is named so the next reader does not repeat it, and because the
instrument then had to be re-proven.

## MEASURED 2026-09-29 — the scheduler enters ONCE and never reaches either of its own stores, with its code provably intact

The observer makes the state machine's two exits into **watchable stores**, and watching all three
store PCs *in one run, with a control*, is what turns this from a guess into a localization.

The scheduler's dispatch exit and its fall-through exit both store, and they are the only two ways
out of the state block:

    800126A4  jal   0x800eddbc      ; ChangeTh
    800126A8  sh    $s1, ($v0)     ; delay slot: record state <- 0x7f   (DISPATCH exit)
    ...
    80012718  addiu $v0, $v0, 0x80 ; cursor += 0x80
    80012720  beqz  $v1, 0x8001262c
    80012724  sw    $v0, ($s0)     ; cursor store                (FALL-THROUGH exit)

One run, three store PCs armed, `0x80012620` being the function prologue and therefore a control
that must fire:

    armed: 0x80012620  0x800126A8  0x80012724
    events: 1 x guest_pc=0x80012620 phase=before
            1 x guest_pc=0x80012620 phase=after

**The prologue fires exactly once, and NEITHER exit store ever fires.** The scheduler is entered once
and never passes `0x80012624`. The state block at `0x8001262C..0x8001267C` is where it dies.

**The instructions in that block are provably UNMODIFIED at run time.** `0x0113D7D0` is below
`0x04000000`, so it is exactly the kind of value a corrupted 26-bit `j` field would produce, and the
block contains two `j` instructions — which made "a `j` field was overwritten" an obvious hypothesis.
The runtime words were read directly through the debug server:

    0x80012654=3C03801F  0x80012658=080049C4  0x80012670=3C03801F  0x80012674=080049C4

Both `j` instructions are `0x080049C4`, byte-identical to the authenticated image. **The
corrupted-`j` hypothesis is REFUTED**, not merely unproven.

**Which leaves a contradiction sharp enough to be useful.** With the cursor self-referential
(`0x801F8300`), the state read at `0x80012638` yields `0x8300`; no branch handles it; `0x80012674`
jumps to `0x80012710`; `sltu` makes `beqz` fall through; and `0x80012724` **must** execute. It does
not — while the instructions that would take it there are provably unmodified.

So this is no longer a question about a word someone wrote. The data and the code are both shown
intact, the path is shown to be taken, and the store at the end of it is shown not to happen. **That
points at the EXECUTION of that block rather than at its contents** — a translation or branch-
propagation fault on the state-read block in the executor, which is a different owner from anything
examined so far and a different kind of fix.

### What this does NOT establish

It does not establish that the executor is at fault. The `beqz $v1, 0x8001262c` back-edge at
`0x80012720` targets the state-read block itself, so a **re-entered** block would also produce no
exit store, and the observer's `seen=` counter shows one entry — but a loop that re-enters through the
prologue is a different thing from a loop inside the block, and nothing yet separates them. That
distinction is the next thing to settle, and it decides which owner is responsible.

## CORRECTION 2026-09-29 — "entered ONCE and reached neither exit" is WITHDRAWN; it was measured on a crashed run

The previous section's central claim is **refuted by my own later measurement**, and the reason it
was wrong is worth recording because it is a new instance of the same class this investigation keeps
meeting: a run that died early was read as a run that reached a conclusion.

**The scheduler is called 10,403 times, and the cursor store fires on every one of them.** Arming the
prologue and the cursor write — two targets, both of which execute — gives:

    10403  guest_pc=0x80012620 phase=before / after
    10403  guest_pc=0x80012628 phase=before / after

So `0x80012628` — `sw $v0, -0x7d00($at)`, which **writes the cursor at `0x801F8300`** — runs on every
call. That is also the store the earlier register-tracking scan missed, because it forms the address
from `lui $at, 0x8020` plus a `-0x7D00` displacement rather than from the `lui $s0, 0x801f` /
`ori 0x8300` chain the scan followed. **The scan's predicted false negative, observed.**

**What made the earlier reading wrong: the process was crashing, and the "1 event" was the crash.**
Signal **06** from `abort()`, and the stack is the port's own:

    native_boot_run -> FrameLoopShell::step -> X4FrameDriver::stepFrame
      -> x4::guest::callWithoutKnownReturn -> abort

That is **`callWithoutKnownReturn` hitting its budget and refusing, which is the function's designed
behaviour** — the scheduler spins on its `beqz` back-edge at `0x80012720` until the budget is gone.
It is not a segfault and not an observer fault.

**What is still NOT established, and is the reason the earlier section is withdrawn rather than
amended:** whether `0x800126A8` and `0x80012724` execute. Runs watching them abort almost immediately
(1 event, same stack), so their silence is a run that **died before it could observe anything** — which
is the same green-zero mistake in a new costume. A run that aborts is not a run that proves absence,
and the previous section treated it as one.

**RETRACTED 2026-09-29 — my "run-length variance" resolution of this was WRONG, and the effect is
real.** The resolution was generalised from two runs of the *same* arming and never compared the two
armings head to head. Doing that settles it, with identical flags, one target per run, repeated:

| armed store PC | events | outcome |
|---|---|---|
| `0x80012628` (cursor store, function entry) | 400 | **no abort**, 400 frames clean |
| `0x80012724` (cursor advance, inside the loop) | 0 | **aborts** before any event |

Reproducible two runs each way. **Arming a store PC does change this program's outcome**, so the
worry is reinstated and only the "run-length variance" explanation is withdrawn.

**The mechanism is now known and it is a property of the INSTRUMENT, not of MMX4.**
`lightrec_set_store_observer` calls `lightrec_invalidate_all` and `lightrec_free_all_blocks` —
arming discards the entire translation cache — and the emitter then instruments **every store in
every block**, filtering by PC only later in the callback. Each observed store additionally flushes
and resets the whole register cache. So a run with the observer armed **is not the program**, which
is the same class of failure this project treats as worst. Full derivation and the reproduction:
`psxport/docs/issues/0039`.

**What that does and does not settle here.** It explains why an instrumented run is not a clean run,
and it means the 0 / 10,403 / 400 event counts must not be read as clean-program behaviour. It does
**not** explain why the two armings differ, since by that mechanism both instrument every store
everywhere. That part is unexplained and is reported, not worked around.
The runs that produced 10,403 and the runs that produced 1 differed in how long they lived before
the budget refusal ended the process, and that is what set the count.

**Nothing suggests the store observer perturbs execution, and the earlier worry is withdrawn.** What
survives is the correction above: a run that aborts is not a run that proves absence, and the
"entered once, reached neither exit" reading was made on an aborted run.

## MEASURED 2026-09-29 — the cursor store at `0x80012724` provably does NOT execute, and the data is not why

This is settled **without** the store observer, because `psxport/docs/issues/0039` established that
arming it invalidates every block and instruments every store, so a run with it armed is not the
program. `tools/probe_cursor_poll.py` polls the word directly and reports the full histogram.

    scanned 9627 read(s) of 0x801F8300; 4813 read(s) returned nothing
    1 distinct value(s) observed:
      0x801F8300    4814 read(s)  100.0%

**`0x801F8380` is never observed once in 4,814 successful reads.** The decoded path says the store at
`0x80012724` must write it, so the two facts are incompatible and the code reading is the one that is
wrong.

**The sampling bias runs AGAINST this result, which is what makes it trustworthy.** Between two
scheduler calls the cursor would hold `0x801F8380` for essentially the entire frame; `0x801F8300` is
written only at the call's entry (`0x80012628`) and overwritten at the exit. A poller is therefore
biased toward seeing `0x801F8380`, not toward seeing `0x801F8300`. A uniform `0x801F8300` across
4,814 reads is not a phase artifact — it is what a word that only ever takes that value looks like,
and that is exactly what the histogram is for: a single reported value is otherwise indistinguishable
from sampling one window.

**So, with the `j` words at `0x80012658` and `0x80012674` proven byte-identical to the authenticated
image, and the data proven intact, execution diverges from the decoded path INSIDE the state block.**
This is a code/translation finding, not a data finding, and it is the first result on this frontier
that points at the executor rather than at MMX4's memory.

### The tool, and what it refuses

`tools/probe_cursor_poll.py` REFUSES rather than reporting a vacuous result in three cases: fewer than
200 samples ("a short run proves nothing about a polling phase"), every read failing, and any outcome
it cannot characterise (it says `NOT a conclusion` rather than guessing). It prints the read count and
the failure count separately, because 4,814 successes out of 9,627 attempts is a fact about the
endpoint dying mid-poll, not about the guest.

## CORRECTION 2026-09-29 — the self-pointer is the scheduler's NORMAL exit value, and the previous section's conclusion is WRONG

The previous section concluded that `0x80012724` does not execute and that execution "diverges
from the decoded path", pointing at the executor. **A positive control overturns that.** The debug
server's `call` command invokes a guest function directly and reports its register file:

    call 80012600(a0=00000000,...) -> v0=801F8300 v1=00000001

`v1` is the `sltu` result from `0x8001271C`. **`v1 = 1` means `beqz` was NOT taken, so execution DID
fall through to `0x80012724` and DID store the cursor.** The code path is correct.

**And the arithmetic shows the poll was measuring the wrong thing.** The loop at `0x80012710`
increments `$v0` by `0x80` and continues while `0x801F82FF < $v0`. The first multiple of `0x80`
strictly greater than `0x801F82FF` **is `0x801F8300`**. So the loop's terminal value is
`0x801F8300` **from any starting cursor** — the value the high-frequency poll saw 4,814 times out
of 4,814 is simply where this loop always stops.

**So `0x801F8300` holding `0x801F8300` is not a self-reference and not corruption. It is the
scheduler's designed end state**, and the poll's uniform result is a correct observation of a
correct program. My "data and code disagree" verdict was reading a designed terminal value as a
symptom.

**What the loop length actually tells us, and it is the useful part.** The iteration count is
`(0x801F8300 - entry_cursor) / 0x80`. Entered with `$v0 = 0` — which is what the direct call
supplies — that is **262,142 iterations in a single guest call**, which is why
`callWithoutKnownReturn` exhausts its budget and refuses. **The budget abort is a consequence of
the loop's length, not of a fault**, and the two things I had been treating as one mystery are
separate: the abort is explained, and the `0x0113D7D0` fault is still open.

**What is NOT established:** the entry value of `$v0` in the real caller. The debug `call` sets
`a0..a3` from arguments and leaves `v0` at zero, so this experiment **cannot** speak to what the
real caller passes. That is the next question, and it is the one that decides whether the 262,142
-iteration loop describes the product at all or only my positive control.

**Retracted:** "execution diverges from the decoded path inside the state block", and "that is a
code/translation problem, not a data one". Both were wrong, and both came from treating the
scheduler's normal terminal value as evidence of a fault.

### A green zero I built MYSELF, and the selftest that now kills it

Worth recording because this session spent its whole time finding dead taps and gates that
cannot fail, and then produced one.

The first `probe_cursor_poll.py --selftest` had four cases and **three behavioural mutations
survived it**. Every case was vacuous, in four different ways:

- `Endpoint(1)` tested the *environment* (that port refuses) not the code — deleting the check
  changed nothing;
- the sample-floor case compared a constant to a computed value, self-consistent by construction;
- `if collections.Counter() or True:` made the failure branch **dead code**;
- `if 0x801F8380 == 0x801F8300` compared two constants.

The fix is structural, not cosmetic: **every refusal and every verdict now lives in one pure
function**, `classify(histogram, reads, failures) -> (verdict, exit_code)`, with no I/O, no clock
and no defaults, and the selftest drives it with synthetic histograms. Two further defects only
appeared once the mutations ran:

- the `if not seen` guard was **unreachable**, because an empty histogram already fails the sample
  floor, so removing it changed nothing. The guards were reordered so both are live.
- the all-failed case asserted only `"REFUSED"`, which *either* guard produces, so it could not
  tell which one fired. It now asserts the specific message of each guard.

**Now verified: five of five mutations go red** — empty guard, sample floor, predicted-value
verdict, single-value verdict, and collapsing `PREDICTED_CURSOR` onto the observed value — and the
baseline is green. A gate that cannot fail is not a gate; this one now can.

## MEASURED 2026-09-29 — a REAL defect found and fixed (thread `$gp`), and it is NOT the cause of the fault

**FOUND: every thread was being resumed with `$gp = 0`.** Logging the raw `OpenTh` arguments and the
creating context's own `gp` settles it in one run, over five calls:

    a0(entry)=0x8001D064 a1(sp)=0x801FEC00 a2(gp)=0x00000000 callerGp=0x8012F418
    a0(entry)=0x80012A3C a1(sp)=0x801FF400 a2(gp)=0x00000000 callerGp=0x00000000

**SLUS_005.61 passes `a2 = 0` on every single OpenTh call.** It does not use the BIOS's third
argument; it relies on a thread inheriting the creating context's global base. `Service::open` took
the thread's gp from `r[6]`, so taking that zero at face value resumed **every** task with
`$gp = 0` — and MMX4's code is `$gp`-relative on the real base `0x8012F418`, so each of those tasks
read and wrote the low 16 KB of RAM in place of its own statics. The last three lines show the
**cascade**: contexts already resumed with a null gp creating further null-gp threads.

**FIXED, and it is not a substituted constant.** `resolveThreadGlobalPointer` in
`game/core/bios_threads.h` inherits the creating context's own `$gp` when the guest passes zero; an
explicit guest gp still wins, and **two zeros stay zero** — the port does not invent a global base.
After the change every thread reports `gp=0x8012F418`, including the call that previously inherited
from an already-broken context, so the cascade is gone.

**AND THE FAULT SURVIVES.** `0x0113D7D0` still appears and the run still exits 139. **So the null-gp
defect was real and is now fixed, and it is not what produces the corruption.** Recorded as a
separate fixed defect, not as a root cause — the distinction this investigation has had to relearn
several times now.

### What the fault now points at, and it is a SECOND resume path

With gp healthy the fault's own log names what immediately precedes it:

    [x4-thread] retail task entry 0x8001DAF8 needed more than one display field of guest CPU
                and was RESUMED at 0x800EA0F4 after 564486 cycle(s)
    [native-dispatch:error] guest address 0x0113D7D0 resolves to zero or multiple active code images
    [x4-guest:error] guest call 0x80012600 exited fault at 0x0113D7D0 after 0 cycles
      r0=0x00000000 r1=0x80200000 r2=0x801F8300 r3=0x00000001 r4=0x00000000

`r2 = 0x801F8300` is the cursor and `r1 = 0x80200000` is the scheduler's own `lui $a0, 0x8020`, so
the fault is inside the state-read block, 0 cycles into the dispatch.

**The lead is the resume that precedes it.** A task that overruns one display field is *resumed at
a host-chosen point*, and the fault lands immediately after. **That is a different resume path from
`Service::change`, and it is the one the switch census does not cover** — the census counts
`Service::change` resumes (14,000 of them, 0 with an invalid pc) and never sees this. So the census's
"0 invalid pc" is TRUE AND IRRELEVANT to this fault, which is the same false-absence shape as every
other dead tap in this workspace, in a place where the census looked like coverage.

**What is not established:** whether `0x800EA0F4` is a sound resume point, and whether the bad
`pc` belongs to the resumed task or to a task `ChangeTh` selects afterwards. The next instrument has
to cover the field-boundary resume, not the one the census already watches.

## MEASURED 2026-09-29 — the stack pointer is REFUTED as a cause, with a working instrument and a denominator

The fault's own register dump looked damning: `r29 = 0x801FFFE0`, and the retail scheduler's frame
sits at `0x80200000 - 0x20`, so the scheduler appeared to be entered with `sp = 0x80200000` — about
`0x1400` bytes above the `0x801FEC00` stack the guest handed `OpenTh`. A task running on a foreign
stack would explain a clobbered frame.

**The switch census classified `pc` and `r[31]` and said nothing about `r[29]`** — and `Service::open`
discarded the stack pointer after writing it, so there was no bound to check against. Both are fixed:
`Thread::stackTop` now retains it, and every resume is classified.

**The instrument then reported an honest zero over 14,000 resumes:**

    14000 task resume(s) scanned; 14000 with a pc inside a code image, 0 outside EVERY code image;
    of their link registers, 3 zero, 13997 in a code image and 0 not; of their stack pointers,
    0 were ABOVE the stack top the guest handed OpenTh, and 0 were zero

**So the stack pointer is refuted as a cause.** And on re-reading the dump, `sp = 0x801FFFE0` is
**main's** stack — its top is `0x801FFFF0` — so the scheduler's frame sits exactly where it should.
There was no corruption; I read a perfectly valid value as a symptom, which is the same error as the
self-pointer and the corrupted `j` before it.

**Why this negative is worth landing anyway.** The census is the thing that makes it trustworthy: a
census that only prints when it is worried is indistinguishable from one that is not running, so the
new counters are reported on the existing stride, and the run above is "scanned 14,000, matched 0"
rather than silence. The switch is now measured sound on `pc`, `r[31]` **and** `r[29]`, and
`sp = 0` or `sp` above the declared top will be reported at the switch, with slot and entry named,
rather than 13,000 fields later as a bare fault.

**What this leaves open:** the field-boundary resume is still the uncovered path, and the fault's
preceding line — a task resumed at a host-reported `pc` after 564,486 cycles — is still the only
thing pointing at it. The next instrument has to observe that resume's register state directly,
because the switch census by construction cannot see it.

## MEASURED 2026-09-29 — `0x0113D7D0` is produced by the BUDGET-RESUME path, established by dose-response

Four runs, changing only the guest turn budget, counting the budget resumes each one takes and
whether the fault appears:

| turn budget | budget resumes | `0x0113D7D0` | vblank reached |
|---|---|---|---|
| x1 (564,480 cycles — one display field) | 13,420 | **present** | — |
| x2 | 155 | **present** | — |
| x8 | 38 | **absent** | `0x783C` |
| x400 | 0 | **absent** | `0x77F4` |

**The fault tracks the resume COUNT, not the size of the budget.** The x8 run is a fair comparison
and not a different program: it still resumed 38 times — so the path was genuinely exercised — and
it reached `0x783C` against the x400 run's `0x77F4`, essentially the same point in the game. The
fault disappears between 155 resumes and 38.

**The x400 bisect on its own was WEAK evidence and is recorded as such.** It changed the guest's
entire timeline, and the run failed *differently* (`guest task 0x8001DAF8 faulted`, `r9 = 0xFF000000`,
`vblank = 0x77F4`). A single run that faults somewhere else is not a controlled result. The
dose-response above is what makes the claim, because the independent variable is the resume count
and the x8 point holds total runtime roughly constant.

### A comment of mine in the shipping source is REFUTED by the bytes

`game/core/guest_execution.cpp` asserts that the resume point "`0x800EA0F4` ... IS such a leaf" — a
`jr $ra`. Decoded, it is not:

    800EA0EC  jr    $ra
    800EA0F0  nop
    800EA0F4  lui   $v0, 0x8012      <- the resume point: a function ENTRY
    800EA0F8  lbu   $v0, -0x1e78($v0)
    800EA0FC  jr    $ra

`0x800EA0F4` is the first instruction of a three-instruction getter, with its `jr $ra` eight bytes
later. **So resuming there is an ordinary continuation, and the "a `jr $ra` is one-shot, so
re-executing it re-dispatches" hypothesis is refuted.** The comment is left to be corrected with the
defect rather than edited now, so the refutation stays visible next to the claim it kills.

### What has been checked and cleared, so the next reader does not repeat it

- **The exit lands on a block boundary.** `lightrec_execute` hands the remaining cycles to the
  generated dispatcher, so the limit is enforced between blocks and `state->curr_pc` is a block
  entry. Re-entering there is a sound continuation.
- **Registers are committed before the budget is examined.** In `LightrecExecutor`'s segment loop,
  `copyLightrecToCore(nextPc)` runs immediately after `lightrec_execute` and before the
  `BudgetExhausted` return, so there is no stale-register window at the exit itself.

**The one asymmetry found, and it is unproven.** `copyLightrecToCore` copies
`lightrec_get_registers(state)` with no register-cache flush, and `store-observer.c` proves the
regcache is not flushed at a store by default — it has to call `lightrec_clean_regs` explicitly. In
`emitter.c` the end-of-block path does `lightrec_jump_to_eob(...)` then
`lightrec_regcache_reset(reg_cache)` — **a reset with no preceding `lightrec_storeback_regs`**,
where the sync path at `emitter.c:3047` correctly stores back *then* resets. Whether that is a
defect or is compensated inside the end-of-block wrapper has **not** been established, and it is
the sharpest remaining lead: it would explain a guest register being stale specifically at a
segment boundary, which is exactly the boundary a budget resume re-enters through.

## CORRECTION 2026-09-29 — the dose-response does NOT show the fault disappearing; it shows it MOVING

The previous section read the four budget runs as "the fault tracks the resume count". **That is the
wrong reading, and the runs themselves refute it** once their terminal state is compared:

| run | resumes | task turns reached | failure |
|---|---|---|---|
| x2 | 155 | 14,141 | `0x0113D7D0` in the scheduler |
| x8 | 38 | 14,024 | `guest task 0x8001DAF8 faulted`, vblank `0x783C` |
| x400 | 0 | ~14,000 | `guest task 0x8001DAF8 faulted`, vblank `0x77F4` |

**All three reach the same depth — within 1% on task turns, vblank ~`0x7800` — and all three fail.**
The x8 run did not escape; it failed at a different address. So the budget does not decide whether
the corruption happens, only **which** corruption is observed.

### It is ONE corruption, and it is a pointer the guest jumped through

The x2 fault register file and the x8 fault register file share a value:

    x2: r4=0x0114BED0        (the run that faults at 0x0113D7D0)
    x8: r4=0x0114BED0  r2=r3=0x00139C30  r5=0x00FFFFFF  r6=0xFF000000

`r4 = 0x0114BED0` appears in **both**, and `0x0113D7D0` and `0x0114BED0` are the same shape:
`0x011xxxxx`. **This game's text spans `0x80010000..0x8012F800`, so `0x011xxxxx` is RAM, not code.**
The guest is fetching at a value it read from memory as though it were an address — **a corrupted
function pointer, return address, or jump-table entry.** `r6 = 0xFF000000` in the same dump is a
thread handle, which is legitimate, so the register file is not uniformly garbage.

**The common factor across every run is the same task: `0x8001DAF8`.** It is the task that needs more
than one display field, the one the budget resumes at `0x800EA0F4`, and the one whose entry the x8
and x400 runs fault at. One task, one corruption, surfacing at whichever address the current
schedule happens to reach first.

### What is refuted, so it is not repeated

- **The register cache is NOT the cause.** `emitter.c` flushes before the jump — `lightrec_clean_regs`
  runs at the end-of-block path *before* `lightrec_jump_to_eob`, and only then
  `lightrec_regcache_reset` resets the compiler's model. I reported an asymmetry there by reading the
  reset without seeing the flush twenty lines above it.
- **The GTE round-trip is symmetric.** `copyCoreToLightrec` calls `gte_export_registers` and
  `copyLightrecToCore` calls `gte_import_registers`, so no GTE state is lost across a segment.
- **A memory scan for the value is not currently possible.** A scan for `0x0114BED0` covered 16,384
  words — about 3% of RAM — and the run never reached the fault, so its zero is not evidence of
  absence and is not recorded as any. The coverage limit was measured earlier in this investigation
  and has not changed.

## MEASURED 2026-09-29 — every GUEST-side explanation is refuted; the bad PC is not in a register, not in a `j`, not a resume point

Three independent checks, each with the coverage it earned, and together they close the guest side.

**1. No register holds the fault address.** In the x2 run, where `0x0113D7D0` *was* the fault
address, the fault-time register file is

    r0=0x00000000 r1=0x80200000 r2=0x801F8300 r3=0x00000001 r4=0x00000000 r5=0xFFFF0000
    r6=0x80139554 r7=0x00000000 r8=0x80166C74 r9=0x0000002A r10=0x000000A0 r11=0x00000000
    r28=0x8012F418 r29=0x801FFFE0 r30=0x80200000 r31=0x800120EC

**Not one of the 32 holds `0x0113D7D0`**, and `r31 = 0x800120EC` is the correct return. So the bad PC
did not come from a `jr $reg`. The registers are internally consistent with the scheduler's
state-read block: `r1 = 0x80200000` is its `lui $a0, 0x8020`, `r2 = 0x801F8300` is the cursor, `r3`
is the `sltu` result.

**2. Neither `j` instruction is corrupted.** The call contains exactly two, and for either to name
`0x0113D7D0` the word would have to be `0x0913D7D0` — the address is below `0x04000000`, so it fits a
26-bit field. Polled with the histogram tool to the moment the process died:

    0x80012658  -> 0x080049C4  4,704 read(s)  100.0%
    0x80012674  -> 0x080049C4  5,581 read(s)  100.0%

**Unchanged, and the earlier "the `j` words are intact" claim is now measured at the fault rather
than thousands of frames before it.**

**3. The resume point is valid.** `"after 0 cycles"` means the fault is in a *resumed* segment, so the
resume address was the obvious suspect. Every `RESUMED at` address in the x2 run is KSEG0 code, and
the last before the fault is `0x800EA0F4` — the same task resume point throughout. **The bad PC is
not the resume point.**

**So the fault PC was produced by neither the guest's registers, nor its instruction stream, nor the
resume address. That leaves the framework's own `nextPc` at a budget exit** — `nextPc` is
`state->curr_pc`, and in Lightrec's block loop the cycle check sits *before* the store that updates
it:

    loop2 = jit_label();
    boundary_to_end = jit_blei(LIGHTREC_REG_CYCLE, 0);          // exits to `to_end` here ...
    jit_stxi_i(lightrec_offset(curr_pc), LIGHTREC_REG_STATE, JIT_V0);   // ... but curr_pc is set HERE

**That ordering is a real observation and it is NOT yet a defect**: `curr_pc` still holds the previous
block's stored pc, which is a valid code address. What is unestablished is whether some other exit
path leaves `curr_pc` holding something that is not one. **The named next step is a census on the pc
reported at `BudgetExhausted`** — flag any that is outside every code image, in the framework, next to
the exit that produces it. That is the same discipline the MMX4 censuses use, applied to the one
value that is still unaccounted for.

## The next step, named

1. **Why does the cursor at `0x801F8300` point at itself?** This is now the cheapest open question
   and it is in the GUEST's data rather than in the port, so it is worth more than another register
   reading. `Service::open` and the frame driver both write that neighbourhood, so the first check is
   which of them last stored `0x801F8300` there - the same "name the feeder" discipline the dead taps
   in this workspace demanded.
2. **Do not scan memory for it; catch the load.** Scanning is bounded below the run length by the
   endpoint's per-read cost, so the next instrument must be cheap per sample. A store observer is the
   right shape, because the value must have been written to RAM before it could be loaded from it —
   the port already has the `configureStoreObserver` seam.
2. **Ask which INSTRUCTION branches, not which value.** The scheduler at `0x80012600` is guest code
   whose `jalr`/`j` sites are countable in the image; the branch that produces a non-address is
   statically findable even when its target is dynamic, and that is far cheaper than chasing a value
   that is measurably too fast to sample.
3. **Supply boundaries for the remaining native-owner calls**, so the refusals become working calls.
   `tools/census_guest_call_sites.py` has the candidates: `kAppendBandsGuest` (0x80015ECD) has **no**
   `jal` site at all, so it needs a pointer/`jalr` reachability answer before a boundary can be
   derived for it; the `display_init` and `music_stream` entries have 2-24 sites each and the owner
   must name which one it stands in for.
4. **Widen `GuestDispatch` to carry the return address.** Five headers each declare their own
   `using GuestDispatch = void (*)(Core *, std::uint32_t);`, so a boundary cannot travel with a
   dispatch today, which is why `callWithRegisterReturn` exists as a verified-register compromise.
   One typedef, one owner, and the return address becomes impossible to drop.
5. Keep the boundary gate. `tools/census_guest_call_sites.py --verify-boundaries` re-derives the two
   hard-coded constants from the image and was confirmed red on a mutated constant.

## SUPERSEDED PLANS (kept so they are not re-derived)

*The four fixed RAM windows* (`0x8011C000`, `0x801FE000`, `0x801F8000`, `0x80139000`) were the right
first move — each region was added because the previous one came back empty — but they cover under 1%
of RAM and are replaced by a sliding slab, which is in turn bounded by the endpoint's per-read cost.

*Pointing the register census at the fiber switch* — done, and it refuted the switch: 14,000 resumes,
0 with a `pc` or `r[31]` outside a code image.

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
