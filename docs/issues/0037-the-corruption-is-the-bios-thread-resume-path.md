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

## MEASURED 2026-09-29 — the framework's budget-exit pc is REFUTED, and that weakens one of my OWN refutations

`psxport` now classifies the pc every budget exit reports, against the loaded code images, and
publishes it through the debug server so a live run can be asked. On MMX4, rebuilt against it:

    budget_exit: exits=466 pc_in_code_image=466 pc_outside_code_image=0
    budget_exit: exits=488 pc_in_code_image=488 pc_outside_code_image=0
    budget_exit: exits=509 pc_in_code_image=509 pc_outside_code_image=0

**The denominator moves, the partition holds, and 500+ budget exits reported a pc inside a code
image. So `nextPc` at a budget exit is REFUTED as the source of `0x0113D7D0`.**

**A near-miss worth recording, because it is the exact shape this investigation has been about.** The
first attempt at this measurement reported zero - and the zero was worthless, because MMX4's binary
was still linked against the previous psxport build and **did not contain the census at all**. An
instrument that is not in the product reports "0 of 0" and looks identical to a clean result. It was
caught only by asking for the *denominator* over the debug server and finding the line missing
entirely. "The number is zero" and "the thing that counts the number is not running" must be told
apart, and the only way is to see the counter move.

### WHICH OF MY REFUTATIONS WAS WEAKER THAN I SAID

**"No register holds the fault address" does not refute what I used it to refute.** The
"register file at the fault" is `core.r[]`, which `copyLightrecToCore` fills **at a block
boundary**. A guest `jr $reg` whose `$reg` was written by a load *in the same block* has a value
that is still sitting in the JIT's register cache and **has never been spilled into `core.r[]` at
all**. So the dump is a snapshot of the boundary state, not of the fault-instant state, and a bad
value produced and consumed inside one block is structurally invisible to it.

That is the most natural remaining explanation - a corrupted pointer loaded and jumped to within a
single block - and the evidence I offered against it cannot exclude it. **The claim is downgraded
from refuted to not-established**, and the refutation of the *framework's* budget-exit pc above is
unaffected, because that value is a genuine block-boundary quantity.

### THE STALE-`curr_pc` CANDIDATE IS REFUTED, AND THE TRACED PATH IS SHORT

The candidate named at the end of the last section was that a host-service boundary could capture a
`curr_pc` never stored for the current block, because the cycle check precedes the store:

    loop2 = jit_label();
    boundary_to_end = jit_blei(LIGHTREC_REG_CYCLE, 0);
    jit_stxi_i(lightrec_offset(curr_pc), LIGHTREC_REG_STATE, JIT_V0);

**Traced, and it does not hold.** The two later patches close it:

    jit_patch_at(jit_bnei(JIT_V1, 0), loop);      /* V1 != 0, no boundary: jump to `loop` */
    jit_ldxi_ui(JIT_V0, LIGHTREC_REG_STATE, lightrec_offset(curr_pc));
    ...
    jit_patch(to_end);
    jit_patch(boundary_to_end);                   /* both skip the callback entirely */
    if (state->ops.block_boundary)
      jit_patch(boundary_exit);
    jit_stxi_i(lightrec_offset(curr_pc), LIGHTREC_REG_STATE, JIT_V0);   /* the exit store */
    jit_retr(LIGHTREC_REG_CYCLE);

**The argument, precisely.** Reaching the `jit_ldxi_ui` reload of `V0` from `curr_pc` requires
`V1 == 0`, i.e. the boundary really fired. The only way to arrive there is to fall through
`boundary_to_end`, and falling through that branch is exactly the case where the cycle budget was
NOT exhausted, which is exactly the case where the store at `loop2+1` DID run. **The stale read is
therefore unreachable: the store and the reload are guarded by the same condition, in opposite
phases.** When the budget IS exhausted, `boundary_to_end` forwards past both the store and the
callback, and the exit store at the bottom re-stores `V0` - the correct value - before returning.

**So the block's exit pc is a real value from the guest's control flow, and it is not a stale
framework quantity.** On the exit path that value is the register the block's terminating jump
produced, and that register was flushed at the block end, which is what the earlier live-register
measurement covers.

**Where this leaves the frontier, honestly.** Every framework-side origin is now refuted with a
denominator: the budget-exit pc (500+ exits), the boundary's `curr_pc` provenance (control-flow
trace), the resume point the title logs, both `j` words, and the register file at the fault. **The
value is genuinely produced by the guest's own terminating jump inside a block, and nothing so far
says why that jump computed it.** The next step is therefore not another framework census but the
block itself: identify which block ends at the host-dispatch boundary and read the guest
instructions that compute its exit target.

**What would settle it:** the fault has to be reported with the failing block's live register
values, not `core.r[]`. That is a framework change in the fault path, beside the census just
added, and it is the next piece of work.

### THE DOWNGRADE ABOVE WAS ALSO WRONG, and the path proves it

Tracing the fault's own path in `psxport` shows the host dispatch is a **block boundary**:

    if (flags & LIGHTREC_EXIT_BLOCK_BOUNDARY) {
      switch (boundary.reason) {
      case BoundaryReason::HostDispatch:
        ...
        ExecutionResult result = dispatchGuestHostService(impl.core, boundary.pc);

and in the segment loop `impl.copyLightrecToCore(nextPc)` runs **before** that handling, and that
copy is fed by a `lightrec_clean_regs` flush at every block end. **So `core.r[]` at the fault IS the
live register state, and the downgrade is withdrawn.** "No register holds `0x0113D7D0`" stands as a
refutation of a `jr $reg` with a mid-block load.

**Which relocates the suspect rather than removing it.** The bad pc is `boundary.pc` — the value the
executor captured for the host-dispatch boundary — and it is not any guest register, not either `j`
word, and not a budget-exit pc. **Its provenance inside Lightrec's block loop is the one thing in this
investigation that has not been traced**, and the loop is known to update `curr_pc` at a point where
the cycle check runs first:

    loop2 = jit_label();
    boundary_to_end = jit_blei(LIGHTREC_REG_CYCLE, 0);      // may exit BEFORE curr_pc is stored
    jit_stxi_i(lightrec_offset(curr_pc), LIGHTREC_REG_STATE, JIT_V0);

Whether a host-service boundary can capture a `curr_pc` that was never stored for the current block
is **not established**, and it is now the single remaining candidate. Naming it precisely is worth more
than another black-box probe: the next step is to log `boundary.pc` together with the `curr_pc` the
JIT stored, at the boundary, and compare them.

## MEASURED 2026-09-29 — THE FATAL TRANSFER IS NOT A HOST DISPATCH. IT IS A NESTED CALL TO A CORRUPTED FUNCTION POINTER.

A new `psxport` diagnostic reports the block that produced any control transfer to an address no
code image claims. It fires constantly and harmlessly on this run:

    guest transferred control to 0x000000A0 ... the block that produced this target began at 0x800EDCDC
    guest transferred control to 0x000000A0 ... the block that produced this target began at 0x8001810C
    guest transferred control to 0x00000000 ... the block that produced this target began at 0x800DD7FC

**Those are the guest jumping to a null BIOS table pointer (`0xA0`/`0xB0`/`0xC0` are the BIOS entry
addresses) and are not fatal — the run continues past dozens of them.** They are a separate class and
are not this fault.

### THE DIAGNOSTIC WAS SILENT ON THE FATAL CASE, and that is worth more than the fix

The first version fired only when `currentImageIdentity` found NO image. **It never fired for
`0x0113D7D0`** — and the reason is the finding below, not a bug in the condition. The condition is now
unconditional, and the fault names its own verdict:

    [native-dispatch] guest address 0x0113D7D0 resolves to zero or multiple active code images;
        image identity lookup: claimed by none

**A diagnostic that reports the ordinary case and stays silent on the one that kills the program is
the dead-tap shape again, and it is exactly why the verdict is now printed on every fault rather
than inferred by the caller from which line appeared.**

### WHAT THE PATH ACTUALLY IS, and why every earlier refutation is consistent with it

The fatal fault is **not** raised at a host-dispatch boundary. `dispatchGuest` classifies first and
calls `dispatchGuestHostService` directly:

    const GuestHostDispatchKind kind = classifyGuestHostDispatch(core, guestAddress);
    if (kind != GuestHostDispatchKind::ExecuteGuest) {
      return dispatchGuestHostService(core, guestAddress);
    }

so the segment-loop diagnostic could never see it. And MMX4's own line says what asked:

    [x4-guest] guest call 0x80012600 exited fault at 0x0113D7D0 after 0 cycles,
        and this owner has no return point for it

**`0x80012600` is the scheduler.** So the scheduler performs a **call through a function pointer whose
value is `0x0113D7D0`**, and psxport is asked to run guest code at it. **The corruption is a bad entry
in a function-pointer table, reached by `jalr $reg` — not a corrupted branch, not a stale return, and
not a framework pc.** This is consistent with every refuted hypothesis at once, and explains the two
that were hardest:

- **No register held `0x0113D7D0` at the fault** — correct, and now unsurprising: the fault is
  reported in the scheduler's OUTER frame, whose registers are the scheduler's, not the callee's.
  The register holding the bad pointer was consumed by the `jalr` in an inner frame that had already
  returned by the time the fault surfaced.
- **The resume point and the budget-exit pc were both valid** — correct, because neither is the
  quantity at fault. The bad value is a table entry read by the guest.

### THE FUNCTION-POINTER TABLE IS REFUTED — MY OWN HYPOTHESIS FROM THE PREVIOUS SECTION

The table is not a guess. Decoding the scheduler gives every constant:

    80012618  lui $s0, 0x801f ; 8001261C  ori $s0,$s0,0x8300   cursor base 0x801F8300
    80012710  lw  $v0, ($s0) ; 80012718  addiu $v0,$v0,0x80     advance 0x80 per entry
    800126A0  lw  $a0, 8($v0)                                    the dispatch argument is cursor+8
    80012708  sw  $v0, 8($v1)                                    a delay slot writes cursor+8 back
    80012714  ori $v1,$v1,0x82ff ; 8001271C sltu $v1,$v1,$v0    loop while cursor <= 0x801F82FF

`tools/probe_dispatch_table.py` therefore sweeps **250 slots** (`0x801F8308`..`0x801FFF88`, stride
`0x80`) continuously until the port faults, and keeps both answers: whether any sweep ever saw the
target, and the last complete sweep before death.

    completed 6 sweep(s) of 250 slots (0x801F8308..0x801FFF88, stride 0x80)
    LAST sweep before the port ended: 250 words, 5 distinct values, 5 non-zero
      non-zero slot 0x801FEA88 = 0x800ED1C0
      non-zero slot 0x801FEB08 = 0x8018A000
      non-zero slot 0x801FEB88 = 0x8018A000
      non-zero slot 0x801FFF08 = 0x80139618
      non-zero slot 0x801FFF88 = 0x80019168
    NO SWEEP of 6 saw 0x0113D7D0 in the table (0 matches of 1500 words read)

**0 of 1,500 words, across 6 sweeps spanning the run up to the fault, ever held `0x0113D7D0`, and
every non-zero slot holds a valid code address. The function-pointer table is REFUTED as the
holder.** The previous section's "the corruption is a bad entry in a function-pointer table" is my
own hypothesis and it is wrong; it is kept above only so it is not rediscovered.

**Two measurement traps were hit and defeated while producing this, both worth naming.**

- **A single sweep is a measurement of the wrong MOMENT.** The first run read the table once, ~12 s
  in, and reported zero matches. That looked exactly like this refutation and was not one: the fault
  is at ~40 s. The probe now sweeps until the port dies and reports the last complete sweep, which
  is the state the faulting dispatch actually read.
- **THE CONTROL CHANNEL DESYNCHRONISES, AND A NAIVE CLIENT RECORDS CONFIDENTLY WRONG VALUES.** It
  interleaves unsolicited telemetry (`guest:`, `fallback:`, `---END---`) with command replies.
  Taking "the next line" returned the data line for `0x801F8308` in answer to a request for
  `0x801F8300` — so every slot would have been recorded one address out, and the resulting table
  would have been a confident, entirely fabricated answer. The probe now matches the reply's own
  format AND checks the address against the request, refusing anything else.

**WHAT THE TABLE ACTUALLY SHOWS, which is the useful part.** The live entries are at indices
**207, 208, 209, 248, 249** — clustered at the very top of the table, against main's stack top at
`0x801FFFF0` — and the rest are zero. **The cursor at the fault was `0x801F8300`, which is index 0,
and index 0 is ZERO.** So the scheduler was reading an entry that has never been initialised, and
`lw $a0, 8($v0)` handed `0` to `ChangeTh` as its argument. That is a real defect with a real
address, and it is NOT `0x0113D7D0` — which is why the table was the wrong place to look, and why
the value must be produced somewhere the guest computes it rather than reads it.

### CORRECTION: MY OWN SCAN READ 250 ADDRESSES, NONE OF THEM A DISPATCH SLOT

The previous section's refutation is **void and withdrawn**, because the probe behind it was wrong in
a way the disassembly did not show. It took the table base from `ori $s0, $s0, 0x8300` at
`0x8001261C`. That instruction does not set the table base. `$s0` holds the **CELL**, and the table
base is stored *into* that cell one instruction later:

    80012604  lui  $v0, 0x801f
    80012608  ori  $v0, $v0, 0x8100      v0 = 0x801F8100      <- the TABLE base
    80012624  lui  $at, 0x8020
    80012628  sw   $v0, -0x7d00($at)     [0x80200000-0x7d00 = 0x801F8300] = 0x801F8100
    80012630  lw   $a0, -0x7d00($a0)     a0 = the entry, loaded back out of the cell
    80012638  lhu  $v1, ($a0)            state halfword at entry+0
    800126A0  lw   $a0, 8($v0)           the dispatch argument is entry+8

**So the table is FOUR entries, not 250**, and the probe's 250 addresses (`0x801F8308`..`0x801FFF88`)
do not contain a single one of them. A constant lifted from a listing is not a derivation; only
checking the arithmetic against the loop's own walk catches this. The probe now derives the entries
by walking `while LOOP_END >= entry + 0x80`, which is the guest's own test.

**Two smaller defects in the same file, both worth recording.** A single sweep is a measurement of
the wrong moment — the fault is at ~40 s and the first read was at ~12 s, so the table is now swept
until the port dies. And **the control channel desynchronises**: it interleaves unsolicited
telemetry (`guest:`, `fallback:`, `---END---`) with replies, so a client taking "the next line"
received the data line for `0x801F8308` in answer to a request for `0x801F8300`, which would have
recorded every slot one address out. The probe now matches the reply's own format **and** checks the
address it answers against the one asked.

### THE CORRECTED SCAN: REFUTED, AND THE TABLE IS NOT EVEN FUNCTION POINTERS

    completed 423 sweep(s) of 4 slots (0x801F8108..0x801F8288, stride 0x80)
    LAST sweep before the port ended: 4 words, 3 distinct values, 2 non-zero
      non-zero slot 0x801F8108 = 0xFF000001
      non-zero slot 0x801F8208 = 0xFF000002
    NO SWEEP of 423 saw 0x0113D7D0 (0 matches of 1692 words read)

**0 of 1,692 words, over 423 sweeps spanning the run to the fault, ever held `0x0113D7D0`.** The
whole table, for the record:

    entry 0x801F8100   entry+8 = 0xFF000001
    entry 0x801F8180   entry+8 = 0x00000000
    entry 0x801F8200   entry+8 = 0xFF000002
    entry 0x801F8280   entry+8 = 0x00000000

**`0xFF000001` and `0xFF000002` are not addresses at all** — the image is `0x80010000..0x8012F800`,
so both are outside it. They read as a handle or tag pair (high byte `0xFF`, id 1 and 2), not code.
And the call that consumes them is direct: `jal 0x800eddbc` is `ChangeTh`, whose target is a fixed
address in the listing. **So `entry+8` is a handle passed to `ChangeTh`, and the scheduler does not
call through a pointer at all.**

**This relocates the frontier one level deeper, and it is the first time the scheduler has been
cleared rather than blamed.** The chain is `scheduler -> ChangeTh(handle) -> ...`, and whatever
computes `0x0113D7D0` is downstream of `ChangeTh` at `0x800EDDBC` — reached through a handle, not
through a table of addresses. That is a different search with a different tool, and it is the first
one where the table is not the place to look.

### THE NEXT STEP IS NOW A TABLE, NOT A TRAP

The scheduler's dispatch reads its cursor from `0x801F8300` and advances by `0x80`. The table is
therefore a `0x80`-strided array of function pointers in the image's data, and **`0x0113D7D0` is a slot
in it.** The next measurement is to locate the slot the scheduler was on when it dispatched, and ask
what wrote it — which is a bounded, indexable question against the image's own data rather than a
full-RAM scan, and is therefore finally within the cost that was blocking the earlier attempts.

## MEASURED 2026-09-29 — TWO CLAIMS ABOUT WHERE THE VALUE CAME FROM ARE BOTH UNSUPPORTED, AND ONE IS A NULL-VALUE ERROR

Two other origin claims now exist for `0x0113D7D0`. Neither survives, and they fail in *different*
ways, which is why both are recorded.

### 1. THE `0xD7D0` UNIQUENESS IS AT OR BELOW THE NULL, so it supports no derivation

Issue 0038 reports that the halfword `0xD7D0` occurs exactly once in the loaded image, at
`0x800F2194`, where the word is `0x8001D7D0` — and concludes the producing instruction is "a
halfword load of that table entry". **The uniqueness is exactly true and I verified it independently
(1 hit over 588,800 halfwords). The inference is not supported, because uniqueness here is not
remarkable:**

    4-byte-aligned words scanned: 294400
    observed sharing low halfword 0xD7D0: 1   -> 0x800F2194
    expected by CHANCE alone:        4.49      (294400 / 65536)
    words with high halfword 0x0113:  4         (chance expectation 4.49)

**Observed is BELOW the chance expectation.** A bare match count means nothing without its null
distribution: 294,400 words should produce ~4.5 incidental low-halfword matches, and this image has
one. **So `0x8001D7D0` is exactly the kind of coincidence chance predicts, and the fault value being
derived from it by a high-half corruption is a hypothesis, not evidence.** I also looked for code
that materialises the table address (`lui $rt,0x800f` + `addiu $rt,$rt,0x2170/0x2194`) and found
**0 sites in 294,400 instructions**, so the region is not reached the ordinary way either.

### 2. NO BUDGET EXIT EVER CARRIED IT, and the log says what did

Issue 0038 also states "the segment before it ended as `BudgetExhausted` carrying `guestPc =
0x0113D7D0`". **The log does not contain that.** The three lines around the fault are:

    [x4-thread]      retail task entry 0x8001DAF8 ... RESUMED at 0x800EA0F4 after 564486 cycles
    [native-dispatch] guest address 0x0113D7D0 resolves to ... claimed by none
    [x4-guest]       guest call 0x80012600 exited fault at 0x0113D7D0 after 0 cycles

**There is no budget-exit line carrying that address; the event immediately before the fault is a
task RESUME at `0x800EA0F4`, a valid code address** — which is the same "adjacent line of the same
log" misread that issue 0038 itself retracts in its own §1, one paragraph earlier. The framework
census is the authority that closes it, and its coverage is complete rather than partial: **exactly
two sites in the entire runtime create a `BudgetExhausted` result** — the cycle budget at
`lightrec_executor.cpp:842` and the host-dispatch budget through `recordBudgetExit` — and both are
instrumented. The other three matches for that enum are a name string and two consumers.

### WHAT IS ACTUALLY LEFT

The memory hypothesis is closed, and it is closed **well**: issue 0038's RAM census read
**1,438,562,048 words over 2,743 sweeps** and found zero, *with the feeder proven* by a near-miss
family firing 47 times with real heap addresses. That is the strongest single measurement in this
investigation and it should not be weakened by the two claims above.

So the value is **computed in a register at run time** and never exists anywhere to be read. The
sequence is a valid task resume at `0x800EA0F4`, then a guest call to the scheduler at `0x80012600`
that faults at `0x0113D7D0` having consumed 0 cycles. **The next step is a translation watch — which
instruction writes `0x0113D7D0` into a register — and it must be counted against a measured null,
not against a match count.**

## MEASURED 2026-09-29 — THE THREAD PATH IS CLEARED END TO END, AND A COMMENT OF MINE WAS WRONG

The scheduler's only dispatch is `jal 0x800eddbc`, a **direct** call to `ChangeTh`, and `$a0` **is**
`$r[4]`. So the word the scheduler loads at `cursor+8` is the handle `change_thread` receives, and
the chain is fully first-party from there:

    change_thread:  handle = core->r[4];  core->r[2] = handle;  Service::change(handle)
    Service::slotForHandle:  slot = handle & 0xFF, valid if slot < kThreadCount
    kMainThreadHandle = 0xFF000000

The measured handles `0xFF000001` and `0xFF000002` are **legitimate** — slots 1 and 2 — not wild
pointers. And `Service::open` stores what it is given with **no validation at all**:

    thread.entry = entry;
    thread.regs.pc = entry;

which made the entry the obvious next thing to check, since a bad one would be stored and resumed
later. **It is not the source.** Every `OpenTh` in the run, from the port's own log line:

    3 x  entry=0x80012A3C  sp=0x801FF400  gp=0x8012F418
    1 x  entry=0x8001DAF8  sp=0x801FEC00  gp=0x8012F418
    1 x  entry=0x8001D064  sp=0x801FEC00  gp=0x8012F418
    3 distinct entries; 0 outside the loaded image 0x80010000..0x8012F800

**Five calls, three distinct entries, all valid, and every one reporting the correct
`gp = 0x8012F418`** — which is the `resolveThreadGlobalPointer` fix confirmed working in a live
product run rather than only in a unit test.

### A COMMENT OF MINE WAS OFFERING A FIXED DEFECT AS THE EXPLANATION

`bios_threads.cpp` carried a comment I wrote at the time of the `$gp` fix: a thread resumed with a
null `$gp` takes every global access to address 0, "and a value read that way is a plausible source
of the runtime branch target `0x0113D7D0`". **That is refuted. The fault survived the fix.** The
defect was real, the fix is right, and the claim about the fault was an offer rather than a
measurement — the exact shape this investigation keeps punishing. It is corrected in place, with
the correction kept visible, because a comment that names a closed path sends the next reader down
it.

### WHERE THE THREAD PATH NOW STANDS

Cleared, with denominators: the scheduler's dispatch (direct `jal`, no pointer), the handle
resolution (both live handles are valid slots), the stored entry (3 of 3 valid), the stored link
register (13,997 of 14,000 in a code image, 3 zero, 0 invalid), the budget-exit pc (500+ exits, 0
outside), and RAM (1.44 billion words, 0 hits, feeder proven). **The value is computed in a
register after a valid resume at `0x800EA0F4`, which is a `jr $ra` leaf — so the register that
matters is `$ra` at that leaf, and the census has not yet classified `$ra` at the moment of
execution rather than at the moment of resume.** That is the specific gap the next measurement has
to close.

## MEASURED 2026-09-29 — THE VALUE IS AN INTERRUPT-TABLE HANDLER WORD, AND THE CENSUS THAT REFUTED THE INTERRUPT SLOT WATCHED ONE CLASS

Naming the supplier took one more instrument, and it is the first that points at a WORD rather than
at a mechanism. `dispatchGuest` now records which of its four callers handed it the address:

    dispatchGuest was handed 0x0113D7D0, which is in no loaded code image, via the entry
    classify path (not a host-dispatch boundary); caller: guest_call.cpp: callGuest

`callGuest` is `dispatchGuestWithArguments`, whose only callers are `dispatchGuest0..4` — and of
those, exactly one site is reached at fault time, in the interrupt delivery path:

    runtime/psx/hle_interrupt.cpp
      for (int i = 0; i < irq_n; i++) {
        const uint32_t elem     = irq_elem[i];
        const uint32_t handler  = c->mem_r32(elem + 4);      <<< THE VALUE IS READ HERE
        const uint32_t verifier = c->mem_r32(elem + 8);
        ...
        const auto result = psx::cpu::dispatchGuest0(*c, handler, ...);

**So `0x0113D7D0` is the HANDLER WORD of an interrupt-table element.** That is a location, and it
explains every awkward fact at once: it is not in a guest register (0 of 32), not a branch the
guest took (0 transfer occurrences in a whole run), not in the dispatch table, and not in RAM at any
of the 2,743 sweeps — because it is read out of the interrupt table at the instant of delivery,
which is exactly the kind of value a cadence census samples *between* rather than *at*.

### WHY ISSUE 0038'S REFUTATION IS CORRECT AND STILL MISSES IT

Issue 0038 armed `PSXPORT_WWATCH=8011CB98,8011CB9C` and measured **6 stores, none of them
`0x0113D7D0`**, concluding the class-0 interrupt slot is not corrupted. **That census is sound and
its conclusion is true — of class 0.** `kSetInterruptTable = 0x8011CB98` is a `4 * class` array
(`bios_threads.cpp` and `vsync_sync.cpp` both index it that way), and delivery reads
`elem + 4` for **whichever class is pending**. One class's slot being provably clean says nothing
about the others, so "the interrupt slot is not corrupted" and "no interrupt slot is corrupted" are
different claims and only the first was measured.

**The next measurement is therefore four words, not a census:** read every `kSetInterruptTable +
4 * class` at the moment of delivery and name which class carries the bad handler. That is a bounded
question against a known base, and it is the first one in this investigation whose subject is
stated rather than searched for.

### AND THE CADENCE CENSUS HAS A NAMED COVERAGE GAP

2,743 sweeps at a stride of 64 fields cover 175,552 fields, and the fault is at field 175,501 — so
the final ~50 fields, including the one that matters, were never sampled. A value written in that
window is invisible to the census **by construction**, not by bad luck. The census's own conclusion
("0 words, in 0 of 2,743 sweeps") is true and is not evidence about the last minute of the run; the
gap is named here so the number is not read as more than it is.

## MEASURED 2026-09-29 — THE INTERRUPT CLASS TABLE IS REFUTED TOO, AND THE REMAINING GAP IS A LINK I ASSUMED

The measurement named above is now a real instrument: `vsync_sync.cpp` reads **every** class in
`kSetInterruptTable` on a stride of 64 fields, classifies each with `Core::currentImageIdentity`,
reports the count, and names any class whose handler is not executable. The feeder is shown — a
census reporting only bad cases cannot be told from one that is not running, so the summary line
prints every time.

    IRQ table census at field 0:   scanned 16 of 16 classes, 7 populated, 2 outside every code image
    IRQ table census at field 64:  scanned 16 of 16 classes, 7 populated, 2 outside every code image
    ... 462 census points in the run

    IRQ class 11 handler at [0x8011CBC4] is 0x0000000D, which is in NO loaded code image
    IRQ class 15 handler at [0x8011CBD4] is 0x80200000, which is in NO loaded code image

**`0x0113D7D0` appears in NONE of the 16 classes at ANY of the 462 census points** — 0 occurrences.
The only non-code values ever seen are those two, and they are **stable for the whole run** (two
distinct values across all 462 points), so neither is a value that arrived and was dispatched.
**The interrupt class table is refuted as the holder.** That is the fourth origin refuted with a
denominator, after the budget-exit pc, the boundary `curr_pc`, and the function-pointer table.

### TWO THINGS I AM NOT CLAIMING, because I did not measure them

**The two non-code slots are NOT reported as defects.** `0x0000000D` and `0x80200000` are stable,
`0x80200000` is main's stack top, and neither looks like a handler. The likeliest explanation is
that **`kIrqClassCount = 16` is my assumption and the real table is shorter**, so the census is
reading adjacent globals and calling them handlers. The retail `FUN_800E53F0` stores at
`0x8011CB98 + 4*class` and the guest demonstrably uses only a few classes; nothing measured here
establishes the table's extent. Calling these two "corrupt handlers" would be the same mistake this
whole investigation keeps making — a confident reading of a number whose subject was never
established.

**AND THE LINK THAT REMAINS IS ONE I ASSUMED.** The caller-naming diagnostic established that the
supplier is `hle_interrupt.cpp`, which reads `c->mem_r32(elem + 4)` where `elem` comes from
`irq_elem[i]`. **It has NOT been established that `irq_elem` is MMX4's `kSetInterruptTable`.** The
census above reads the title's table; the dispatch reads the framework's registered element list.
If those are the same memory, the hypothesis is dead. If they are not, the search has been pointed
at the wrong array this whole time. **One question settles it: print `irq_elem[i]` alongside the
census, and compare the addresses.** Until then the honest state is that the interrupt delivery
path is the confirmed *supplier* and the *table* is unconfirmed.

## MEASURED 2026-09-29 — FOUND. IT IS THE VERIFIER WORD OF THE GUEST'S INTERRUPT ELEMENT, AND THE ELEMENT IS GARBAGE

    [irq:error] interrupt element 0x8013BBF8 has VERIFIER 0x0113D7D0 at [0x8013BC00],
      which is in NO loaded code image; dispatching it would fault.
      handler=0xE1000005 mask=0x0113D7C0

**One occurrence in the entire run, at an exact address.** `0x0113D7D0` is the word at
**`0x8013BC00`** — the VERIFIER field of the single `InterruptElement` the guest registers. The
element is `0x8013BBF8`, and all three of its words are garbage:

    [0x8013BBF8] mask     = 0x0113D7C0
    [0x8013BBFC] handler  = 0xE1000005
    [0x8013BC00] verifier = 0x0113D7D0     <<< the faulting value

**The mask and the verifier share their top three bytes** (`0x0113D7`) and differ by `0x10` — the
element is not one bad field, it is a structure the guest registered before it was ever populated.
The delivery loop reads `elem + 4` and `elem + 8` and dispatches both, so the verifier faults first
and the handler never runs.

### THE LAST DIAGNOSTIC WAS AIMED AT THE WRONG WORD, AND THE RUN PROVED IT

The previous commit guarded the HANDLER at `elem + 4`. It reported **nothing, all run**, while the
fault reproduced exactly — because this loop dispatches **two** words and the verifier at `elem + 8`
goes first. **That is the same partial coverage as the census on one of sixteen classes, one level
down, and it produced the same confident zero.** A guard on one of two adjacent words is not a
guard; the zero was a real measurement of the wrong subject, which is the only kind of zero that has
cost this investigation the most time. Both words are guarded now.

### AND THE TITLE-SIDE CENSUS WAS MEASURING THE WRONG ARRAY

The `kSetInterruptTable` census in `vsync_sync.cpp` read `0x8011CB98 + 4*class`. The element the
delivery loop actually walks is **not** that table: `irqEnq(a0, a1)` takes the element address
**from the guest** (`hle.cpp`, the BIOS interrupt-registration HLE), and MMX4 registers exactly one,
at `0x8013BBF8`. So the class-table census refuted a subject that is not the one being dispatched.
Its two non-code slots were, as suspected, adjacent data rather than handlers.

**The useful thing that census did establish stands, though:** `0x0113D7D0` is in none of those 16
words at any of 462 census points, and the RAM census's "0 of 1,438,562,048 words" is consistent —
because the real location, `0x8013BC00`, is a **.bss** address the cadence sweeps sampled only
between fields, and the value was evidently short-lived at the moment of delivery.

### WHAT IS STILL OPEN, AND IT IS NOW ONE ADDRESS

Not *where* — that is settled at `0x8013BC00` — but **who wrote it, and when**. The value is not in
the loaded image, is not in a register, and is not produced by a guest branch; it is written into a
guest structure that is then registered and dispatched. The next instrument is a **store** watch on
`0x8013BC00` and the two words below it, armed for the whole run, which names the writing
instruction and its field. Everything before this turn was searching for a location; from here the
question is a single store.

## MEASURED 2026-09-29 — THE WRITER IS NAMED: A BYTE-WISE COPY RUNS OVER THE ELEMENT, AND THE VALUE IS TRANSIENT

`PSXPORT_WWATCH=0x8013BBF8,0x8013BC04` armed for the whole run closes the last question. The
element is initialised correctly, and then **one instruction stream overwrites it at field 14,773**:

    f1     store [8013BBF8]=00000000  by pc=800DAE8C  ra=DEAD0000      <- clean init, correct
    f14773 store [8013BBF8]=00000027  by pc=80015ECC  ra=80015F5C
    f14773 store [8013BBF8]=0113D7C0  by pc=80015ECC  ra=80015F5C      <- the mask, clobbered
    f14773 store [8013BBFA]=00000058  by pc=80015ECC  ra=80015F5C
    f14773 store [8013BBFB]=00000001  by pc=80015ECC  ra=80015F5C
    f14773 store [8013BBFC]=00000000  by pc=80015ECC  ra=80015F5C
    f14773 store [8013BBFC]=E1000005  by pc=80015ECC  ra=80015F5C      <- the handler, clobbered
    f14773 store [8013BBFD]=000000B0  by pc=80015ECC  ra=80015F5C
    f14773 store [8013BBFE]=00007841  by pc=80015ECC  ra=80015F5C
    f14773 store [8013BC00]=0113D7D0  by pc=80015ECC  ra=80015F5C      <<< THE FAULTING VALUE
    f14773 store [8013BC00]=0313AE20  by pc=80015ECC  ra=80015F5C      <- overwritten again
    f14773 store [8013BC03]=00000001  by pc=80015ECC  ra=80015F5C
    f14773 store [8013BC03]=00000003  by pc=80015ECC  ra=80015F5C

**`0x80015ECC` IS A BYTE-WISE COPY.** The watch addresses `0x8013BBFA`, `0x8013BBFB`, `0x8013BBFD`,
`0x8013BBFE` and `0x8013BC03` are misaligned, and only a byte-granular writer produces those, and
the disassembly agrees:

    80015ECC  addiu $sp, $sp, -0x28
    80015ED0  sw    $s2, 0x18($sp)          a full register-save prologue: not a leaf
    80015ED4  move  $s2, $a2
    80015EE8  lbu   $v1, 0x47($a0)         byte loads through a pointer
    80015EF4  beq   $v0, $v1, 0x80015fe4    and a byte COMPARE branching to a return

**So a `memcpy`-family routine is writing decompressed or copied bytes straight over the guest's
registered interrupt element, and the element is then delivered.**

### THIS IS WHY 1,438,562,048 SAMPLED WORDS NEVER SAW IT

Look at the two lines for `0x8013BC00`: it is written `0x0113D7D0` and then **immediately rewritten**
`0x0313AE20` by the same instruction. **`0x0113D7D0` exists only between two byte stores of one
pass.** A census sampling every 64th field is not unlucky to miss that — it is arithmetically
certain to. The RAM census's zero was a true measurement of the wrong instants, and its cadence was
the reason, exactly as the coverage gap predicted once it was named. **A value that lives for
microseconds cannot be found by a sampler; it can only be found by a watchpoint.**

### WHERE THE FAULT NOW STANDS

Complete, and every earlier refutation is a consequence of it rather than a separate fact:

1. The guest registers an `InterruptElement` at `0x8013BBF8`, correctly initialised.
2. At field 14,773 a byte-wise copy at `pc=0x80015ECC` (returning to `0x80015F5C`) runs **over**
   that element, replacing its mask, handler and verifier with data.
3. The next interrupt delivery reads `elem + 4` and `elem + 8` and dispatches both; the verifier now
   holds `0x0113D7D0`, which is in no code image, and the dispatch faults with 0 cycles.

**The remaining question is a single one and it is about the copy, not the interrupt: what buffer
and length is `0x80015ECC` given, and why does its destination range include `0x8013BBF8`?** Its
arguments are `$a0` (source, indexed `+0x47`), `$a1` (destination, saved to `$s3`) and `$a2`
(saved to `$s2`). Those three values at the call are the whole remaining measurement, and the
watchpoint already shows the call's `ra = 0x80015F5C` — the same return boundary the decompress
owner was corrected to use earlier today, which is worth checking first.

## MEASURED 2026-09-29 — THE CALL'S ARGUMENTS, AND A CONTRADICTION THAT MUST NOT BE SMOOTHED OVER

`PSXPORT_WWATCH_GPR=1` (added to the watchpoint, opt-in, because the copy's destination is saved to
`$s3` and incremented in the loop — printing `$a0..$a3` would have shown nothing) gives the
block-entry register file at the exact store that wrote `0x0113D7D0`:

    r4  ($a0) = 0x80186BAA      r5  ($a1) = 0x8018F676      r6  ($a2) = 0x00000000
    r18 ($s2) = 0x800F21B0      r19 ($s3) = 0x00000000      r20 ($s4) = 0x00000000
    pc = 0x80015ECC   ra = 0x80015F5C

**`$s3` is zero here, which is expected and worth saying: `pc` is the BLOCK start, and the prologue
that does `move $s3, $a1` has not run at a block boundary.** The callee-saved registers being clear
is the signature of a block-entry snapshot, not of a function that forgot to set its destination.

### THE CONTRADICTION, STATED RATHER THAN RESOLVED

Taking `$a1` as the destination, the copy starts at **`0x8018F676`** and the store landed at
**`0x8013BC00`** — **`0x53A76` = 342,646 bytes BELOW its start.** A forward byte copy from `$a1`
cannot reach a lower address. So one of three things is true, and this measurement does not say
which:

- **(a)** the copy runs backwards, or
- **(b)** the destination is not `$a1` in this block, or
- **(c)** `0x80015ECC` is the block START but not the copy loop that was disassembled.

**(c) is the one this investigation has already been bitten by**, in the most expensive way: the
`$s0`-is-the-cell mistake read `ori $s0,$s0,0x8300` as a table base when it set a pointer to a
pointer, and 250 addresses were scanned that were not one of them. **A PC from a block-boundary
snapshot is the block's entry, not the instruction that executed the store**, and treating the
former as the latter is the same error with the same costume.

**So the disassembly of `0x80015ECC` as "the byte-wise copy" stands only as a hypothesis about the
block that contains the store, and the store's own PC has still not been observed.** What is NOT
hypothetical is the chain above it: a store at an exact address, an exact value, an exact field, an
exact instruction stream, and an exact field number. The next measurement is one instruction long —
print the **exact** store PC rather than the block start — and until that is done the function
identity stays marked as unconfirmed rather than quietly upgraded to fact.

## MEASURED 2026-09-29 — THE CALL SITE IS THE DECOMPRESSOR, AND MY OWN INSTRUMENT'S SILENCE IS NOT EVIDENCE

`ra = 0x80015F5C` puts the call immediately before it, and it is the decompressor this port already
owns:

    80015F44  lui   $a0, 0xf
    80015F48  ori   $a0, $a0, 0xffff
    80015F4C  and   $a0, $a1, $a0          $a0 = $a1 & 0xFFFFF
    80015F50  addu  $a0, $a2, $a0          DESTINATION = $a2 + ($a1 & 0xFFFFF)
    80015F54  jal   0x80016FF4              kDecompressGfxGuest — the RLE decompressor
    80015F58  move  $a1, $s1                SOURCE, set in the delay slot
    80015F5C  lui   $a1, 0x8014

**So the store that wrote `0x0113D7D0` belongs to the decompressor's output, and the port already
owns that boundary** — `0x80016FF4` is `kDecompressGfxGuest`, invoked from `0x80015F54`, returning to
`0x80015F5C`, which is exactly the return this port was corrected to use earlier today.

### AND I AM NOT TREATING MY OWN INSTRUMENT'S SILENCE AS A REFUTATION

The store observer was armed on all **7** store instructions inside `0x80015ECC..0x80016020`
(`sb 0x48($a0)`, `sh ($a1)`, `sh -4($a0)`, `sw 2($a0)`, `sh -2($a0)`, `sh ($a0)`, `sh -2($a0)`), and
it produced **no per-hit observation**, while the memory watchpoint fired **3 times in the same
run** on `0x8013BC00`. That looks like a clean refutation of "the writer is in that function".

**It is not one, and the reason is the same discipline this whole investigation has been about —
applied to my own tool rather than to the guest.** Two things are unverified about that silence:

1. **A run with the store observer armed is NOT the program being measured.** Arming it invalidates
   every compiled block, instruments every store in every block, and flushes the register cache
   (`psxport/docs/issues/0039`). Its telemetry is evidence about a *modified* execution.
2. **I have never verified that the observer reports `sb` and `sh` at all.** Its own banner says it
   watches "STORE-INSTRUCTION PCs" and the armed set here is almost entirely byte and halfword
   stores. **A zero from an instrument whose coverage of the relevant store width has never been
   demonstrated is a zero about the instrument.**

So the honest statement is: the writer has not been shown to be in `0x80015ECC`, and the evidence
that would show it either way — the exact store PC — is still missing. **What did not change: the
decompressor is on the call path with a destination of `$a2 + ($a1 & 0xFFFFF)`, and its output is
what lands on the element.**

### THE ONE MEASUREMENT THAT WOULD SETTLE IT, AND IT IS NO LONGER GUESSWORK

Disarming nothing and adding nothing: the decompressor's **destination and length** at
`0x80015F54` are `$a2 + ($a1 & 0xFFFFF)` and the routine's own loop bound. If the destination range
that the decompressor is given **includes `0x8013BBF8`**, the fault is a destination/length defect
in the port's own guest-call boundary and is fixed there. If it does not, the decompressor is being
run with arguments the guest never intended, and the fault is upstream of it. **That is one
register read and one comparison**, and it decides between two entirely different owners.

## MEASURED 2026-09-29 — THE COPY OVERRUNS ITS DECOMPRESSED SIZE BY ~56 KB, AND THE OVERRUN'S TAIL LANDS ON THE ELEMENT

The register file at the clobbering store, with `ra = 0x80015F5C` proving the store happened during
the **decompressor's** execution, and the routine at `0x80015ECC` doing `move $s3, $a1`:

    destination at the block ($a1 -> $s3) : 0x8018F676
    address actually stored               : 0x8013BC00
    the copy walked DOWN                   : 342,646 bytes  (0x53A76)
    expected decompressed size             : 286,720 bytes  (0x46000)
    OVERRUN beyond the decompressed size   :  55,926 bytes  (0xDA76)
    the element at 0x8013BBF8 sits 8 bytes into the end of that overrun region

**That is the shape of the defect, and it is the first actionable number in this investigation.** A
decompress that writes 286,720 bytes is walking roughly 342,646 — **about 56 KB further than the
data it is decompressing** — and the last few bytes of that walk are what land on the interrupt
element and become `0x0113D7D0`. A fixed-size overrun of this shape is not a wild pointer and not a
stale register; it is a length or bound defect, and it is the first candidate in this whole
investigation that a C++ owner can be written against.

**A CORRECTION TO THE MEASUREMENT I ATTEMPTED FIRST, because it nearly became a wrong answer.** I
first applied the call site's own formula, `dest = $a2 + ($a1 & 0xFFFFF)` at `0x80015F50`, to the
registers captured at the store — and got `0x0008F676`, nowhere near the element. **That comparison
was invalid: the formula's operands belong to the CALLER's block and the registers were captured in
the decompressor's inner block.** Applying a formula from one function to another function's
registers is the same category of error as the `$s0`-is-the-cell mistake, and it would have produced
a confident "NO, the range excludes it" from two unrelated subjects. The numbers above use only what
the captured block actually shows.

### WHAT IS ESTABLISHED, AND WHAT IS STILL A HYPOTHESIS

**Established, each with its own evidence:** the exact address (`0x8013BC00`), the exact value
(`0x0113D7D0`), the exact field (the element's verifier), the exact field number (14,773), the
`ra` proving the decompressor was executing, the block-entry destination register, and the size of
the walk. The value is transient — written and rewritten within one pass — which is why 1.44
billion sampled words never saw it.

**Still a hypothesis, and deliberately not upgraded:** that the block at `0x80015ECC` is the copy
routine, and that its destination is `$a1`. The store observer armed on that function's own store
instructions stayed silent, and while that silence is not trustworthy (the observer is invasive per
`psxport/docs/issues/0039`, and its coverage of `sb`/`sh` has never been demonstrated), it is also
not refuted. **The overrun arithmetic above holds for any routine that entered the block with
`$a1 = 0x8018F676` and walked downward** — the function's identity is not load-bearing for the
number, only for naming the owner.

**The next step is therefore narrow and specific:** read the decompressor's output length and
destination at `0x80016FF4` and find the bound that permits 342,646 bytes where 286,720 were
decompressed. That is a guest-side loop bound in a function this port already owns.

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
