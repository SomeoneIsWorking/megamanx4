---
id: 0039
title: The override differential found TWO real register clobbers in the rectangle-queue owner, localised the deliberate deviation to one store, and refuted psxport 0050 as this title's corruption cause
status: open
symptom: |
  The operator landed a mandatory per-override differential (psxport 0138) and a finding that an
  interior-word executable write never revokes its Lightrec block (psxport 0050). `game/core/
  vram_rect_queue.*` is a first-class candidate for the first — it replaced three guest functions and
  encodes a deliberate deviation — and the second is a live hypothesis for the 0x0113D7D0 dispatch.
  This issue is both: what the differential found, and what 0050 is not.
state_items: S002, S004
tags: native-dispatch,overrides,differential,diagnostics,gate,invalidation
created: 2026-09-29
updated: 2026-09-29
---

## 0. Summary

**The gate found two real defects in the owner this repository shipped in `970f346`, and both were
register clobbers with zero memory difference.** `clear` and `upload` left `v1` and `v0` holding
whatever the CALLER had; the appender left `ra` holding the decompressor's return point. All three
are fixed, and all three were invisible to a run because a register nobody reads after the call is
not observable from outside the function.

**The deliberate deviation is now measured rather than asserted.** After the fixes,
`vram_rect::append` shows **184 calls seen, 34 sampled, 33 match, 1 mismatch** — and the gate
localised the single mismatch to `ram [0x00141F68,0x00141F69) original 3C native 30` plus 9 bytes
over 5 ranges. That is the cursor byte (`0x3C` = the guest's unbounded `base + 9*12`, `0x30` = this
owner's bounded `base + 8*12`) and the queue's own records. **The gate named the deviation this
issue's predecessor chose to make, on the call that makes it, and nothing else.**

**psxport 0050 is REFUTED as the cause of `0x0113D7D0` on this title, with a denominator.** Over a
whole run: **1,449,972 store records landed inside the image's address range, and 0 of 1,449,972
landed below `0x800E0000`** — the guest never writes its own executable text, so there is no
interior-word write to a translated guest block for 0050's mechanism to act on. A **positive control**
on the same instrument in the same build reports **1,449,972** matching stores, so the zero is a
measurement and not a dead tap.

**Two framework findings, both reported and not patched** (psxport is read-only here): the
differential's final report is never written on this title's exit path, and the sampler sees **all**
calls for a guest-invoked override but only **one** for a host-invoked one.

## 1. The commands, and what each one answered

Every run is headless, silent, unpaced, bounded, and went through `heavy.py --kind run`; the build
through `heavy.py --kind build`.

| purpose | command |
|---|---|
| arm the per-field overrides, clean exit | `PSXPORT_OVERRIDE_DIFF="vram_rect::clear vram_rect::upload"`, `PSXPORT_NATIVE_FRAMES=1500`, `PSXPORT_OVERRIDE_DIFF_FIRST=6`, `PSXPORT_OVERRIDE_DIFF_EVERY=64` |
| gate that run | `python3 external/psxport/tools/port/override_differential_gate.py scratch/diff/clearupload2.json --require vram_rect::clear --require vram_rect::upload` |
| arm the appender, run to the fault | `PSXPORT_OVERRIDE_DIFF="vram_rect::append"`, `PSXPORT_NATIVE_FRAMES=200000`, `FIRST=12`, `EVERY=8` |
| gate that run | `… override_differential_gate.py scratch/diff/appfix.json --require vram_rect::append --allow-incomplete` |
| 0050 census, code range | `PSXPORT_WWATCH=80010000,8012F800` (`scratch/probe_exec_writes.py --tag code`) |
| 0050 positive control | `PSXPORT_WWATCH=801659D0,80165A30` (`--tag control`) |

`--allow-incomplete` is used for the appender run and only for that: the appender is reachable **only
in the field that faults**, so a run that samples it cannot also shut down cleanly. That is stated
here rather than buried, and the run's own log is the evidence for it.

## 2. Defect 1 — `clear` and `upload` did not reproduce the guest's register clobber

The gate's first two verdicts, on the build `970f346` shipped:

```
[override-diff] vram_rect::clear  @0x80015E0C call 1: none -> mismatch — first difference
   register v1: original 0x80165A38 native 0x80166D52 (1 register(s), 0 memory range(s) / 0 byte(s) differ)
[override-diff] vram_rect::upload @0x80015E54 call 1: none -> mismatch — first difference
   register v0: original 0x801659D0 native 0x00000000 (2 register(s), 0 memory range(s) / 0 byte(s) differ)
```

**`0 memory range(s) / 0 byte(s) differ` on both.** The queue's contents were byte-for-byte correct;
only the register file was wrong. That is the narrowest possible statement of the defect and it is
worth keeping: the owner did the WORK correctly and failed the CONTRACT.

**The values, from the bytes, not from a run.** The clearer's loop runs exactly `kEntryCapacity`
times, so its counters are terminal by construction:

| register | value | instruction |
|---|---|---|
| `$a0` | `kQueueBase + 8*12` = `kQueueEnd` | 8x `addiu $a0,$a0,0xc` (`0x80015E48`) |
| `$a1` | 8 | 8x `addiu $a1,$a1,1` (`0x80015E3C`) |
| `$v0` | 0 | `sltiu $v0,$a1,8` (`0x80015E40`) with `$a1` already 8 |
| `$v1` | `kQueueBase + 8 + 8*12` = `kQueueEnd + 8` | `addiu $v1,$a0,8` (`0x80015E20`) then 8x `addiu $v1,$v1,0xc` (`0x80015E38`) |
| `$at` | `0x8014` | `lui $at,0x8014` (`0x80015E14`) |

The uploader leaves `$v0 = kQueueBase` (`0x80015EA4/8`) and `$v1 = kQueueEnd`
(`addiu $v1,$s0,0x60` at `0x80015E64`, never rewritten). **Its `$a0`/`$a1` need no publishing** — the
guest sets them to the entry and its source pointer and then `jal`s `LoadImage`, so the BIOS B-call
clobbers them, and this owner makes the same call with the same arguments and gets the same clobber.
Publishing them would have BROKEN the match.

`sp` and `$s0`-`$s3` are not published: the guest's own epilogue reloads them from its frame
(`0x80015FE4`-`0x80015FF4`), so the guest leaves them at their entry values, and so does an owner
that does not touch them.

**After the fix, both match:**

```
[override-diff] vram_rect::clear  @0x80015E0C call 1: none -> match — 0 side effect(s) replayed, 0 dead-stack byte(s) ignored
[override-diff] vram_rect::upload @0x80015E54 call 1: none -> match — 0 side effect(s) replayed, 3 dead-stack byte(s) ignored
```

## 3. Defect 2 — the appender left `$ra` holding the decompressor's return point

`runGuest` set `r[31] = caller` for the nested `guest::call` and never restored it. The guest's
appender saves and reloads `$ra` from its own frame (`sw $ra,0x20(sp)` at `0x80015ED8`,
`lw $ra,0x20(sp)` at `0x80015FE4`), so the guest leaves `$31` exactly as it found it and the
differential compares `ra` as a continuation register.

**The measurement is the interesting part: 1 mismatch in 32 samples, 31 matches, 0 memory bytes
differing, and the mismatch was on call 168 — the FIRST call that did any work.** 167 of the 184
appender calls early-return without decompressing, so most sampled calls never touched `r[31]` at
all. **A register clobber that only manifests on the calls that do real work is exactly what a
per-call gate catches and a run-time observation cannot**, and it is the whole argument for 0138
existing.

## 4. The deviation, measured and localised by the gate itself

```
vram_rect::append @0x80015ECC: 184 seen, 34 sampled: 33 match, 1 mismatch, 0 incomparable
first_mismatch: {"call": 184, "what": "ram [0x00141F68,0x00141F69)",
                 "original": "3C", "native": "30",
                 "registers_differing": 0, "memory_ranges_differing": 5, "memory_bytes_differing": 9}
```

Read it: `0x80141F68` is the append cursor global. **`0x3C` is the guest's unbounded
`kQueueBase + 9*12 = 0x80165A3C`; `0x30` is this owner's bounded `kQueueBase + 8*12 = 0x80165A30`.**
`registers_differing: 0` is the register work landing. `9 bytes over 5 ranges` is the queue's
records.

**So: 33 of 34 sampled calls are identical to the guest, and the 34th differs by exactly the one
store this repository chose to bound — on the call that makes it.** 0035's deviation is no longer a
claim in a document; it is a gate verdict that names its own address, its own byte, and its own call
number. `0x0113D7D0`'s own absence (`0` occurrences) and the refusal line
(*"8 of 9 entries this run fit"*) are unchanged from 0035.

## 5. psxport 0050: refuted for this title, with a denominator and a control

**The hypothesis.** 0050 says an interior-word executable write is counted and has no effect, so a
stale block keeps executing. That would produce a jump to an address the current bytes do not
contain — which is precisely the shape of `0x0113D7D0`: a `guestPc` in **no** register
(`0 of the 32 general registers already hold that address`, issue 0037), reached from inside the
scheduler. So the hypothesis was worth testing.

**The test, and why this instrument.** `PSXPORT_WWATCH` fires from `Core::writeGuestMemory<Value>`
for every width and for DMA's sector fill, and it takes a **RANGE** — so one arming is a closed census
of every store that reached the range, whatever its source. The question is whether the range was
written at all, and the instrument's `pc`/`ra` weakness (segment boundary, not store site) is
irrelevant to it.

**The expected count, stated before naming a lead.** The guest's own text has no legitimate writer
at all, so the interesting quantity is the **minimum** target observed, not the total. A large total
would be unsurprising: `0x800E0000`-`0x8012F800` is the BIOS/service region the port itself emulates,
and service code writes emulated device state into guest RAM inside that window.

**What was measured, over a whole run:**

| quantity | value |
|---|---|
| store records inside `[0x80010000, 0x8012F800)` | **1,449,972** |
| distinct target addresses | 2,386 |
| distinct `(pc, ra)` sites | 67 |
| distinct fields reached | 14,773 |
| **records landing below `0x800E0000`** | **0 of 1,449,972** |
| **distinct targets below `0x800E0000`** | **0** |
| lowest target observed | `0x800EDB30` — an `addiu` forming a `0x800F1BD4` data pointer, inside the service region |

**The positive control, same instrument, same binary:** armed on the rectangle queue
`[0x801659D0, 0x80165A30)`, it reports **1,449,972** matching stores. The zero above is therefore a
measurement of this title's behaviour and not a dead tap — which is the only reason it may be quoted.

**The verdict.** The X4 guest never writes its own executable text, so there is no interior-word
write to a translated **guest** block, and 0050's mechanism cannot be what produces `0x0113D7D0`
here. The frontier stays where issues 0036-0038 put it: what computes the value.

**THE SCOPE LIMIT, stated because the number is large and could be misread.** Those 1,449,972 writes
*are* writes into what psxport calls the code image, and 0050's mechanism **would** apply to an
interior word of a translated **service** block. Whether any of them hit one is a question the title
cannot answer — it needs the block map, which is the framework's to hold. That is the operator's to
take from the framework side, and nothing here claims otherwise.

## 6. Two framework findings, reported and not patched

`psxport` is read-only for this session, so both are stated with evidence.

**6.1 — the final report is never written on this title's exit path.** The run that produced the
`clear`/`upload` match **exited 0** (`[boot] native boot returned`, plus this repository's own
`run-end` census lines) and its report still reads `complete: false`, which the gate reports as
*"report is incomplete: the run did not shut down and write its final report"*. **Measured: 3
`override-diff` lines in that run, 0 of them the destructor's summary.** `writeReport(true)` is in
`~OverrideDifferential`, and `OverrideDifferential` is a `Core` member
(`runtime/psx/core.cpp:33`), so the final write needs `~Core` to run. This is the **same
teardown-not-reached defect** issue 0033 §5.2 already recorded for `store_observe_report`, hitting a
second report, and the per-call verdicts are unaffected because they are emitted live.

**6.2 — the sampler sees every call for a guest-invoked override and ONE for a host-invoked one.**
`override_differential.cpp:148` increments `callsSeen` on every intercepted call, so the number is
directly comparable with an independent counter. In the same process, the same run:

| override | invoked by | this repository's own count | the report's `calls_seen` |
|---|---|---|---|
| `vram_rect::append` | guest `jal` (`0x80022058`) | 184 | **184** |
| `vram_rect::clear` | the host frame driver's `guest::call` | **15** | **1** |
| `vram_rect::upload` | the host frame driver's `guest::call` | **14** | **1** |

**That is a thin denominator masquerading as a clean one.** `clear` and `upload` run once per
non-movie field, and the report's `1 of 1 matched` would read as strong evidence to anyone who did
not know the real count is 15. Anyone gating a title-owned override that only the HOST calls is
currently sampling it once per run. `native_dispatch.cpp` consults the differential on the
host-dispatch route; the title's own `guest::call` goes through the entry-classify route, and the
log names the two (`dispatchGuest was handed … via the entry classify path (not a host-dispatch
boundary)`), so the two routes are distinguishable and the finding is specific rather than vague.

## 7. The gate, and the byte gate that grew with it

`tools/verify_vram_rect_queue.py` grows from **64 comparisons to 78** and its `--selftest` stays at
**10/10**. The 14 new claims are the register post-states of all three bodies, each derived from the
instruction that produces it (`8x addiu $a0,$a0,0xc`, `sltiu $v0,$a1,8`, `addiu $v1,$a0,8`,
`addiu $v1,$s0,0x60`, `sll $v0,$s0,0x10`, `sra $v1,$v0,0x10`, `addiu $a2,zero,0x40`,
`addiu $a3,zero,0x10`, `lbu $v1`/`lbu $v0`), so the C++ cannot drift from the image again.

Writing those claims found **three of my own claims wrong before the gate was right** — all in the
same way, and all in this file's comments now: a MIPS **shift** puts its source in the `rt` slot and
its destination in `rd`, while every other SPECIAL operation puts its source in `rs`; and the
register-field helper was reading index 0 as the opcode. The same lesson 0035 recorded, twice in one
session.

**Gate:** `ctest --test-dir build -N` prints **41 tests**; the run is **41/41**. `tools/verify.py`'s
own `build/ci` reconfigure is blocked by an in-flight, not-mine change to the shared pinned
dependency `shared/lightrec` (an added `lightrec_invalidation_contract_test` target; its library
sources are untouched, which is why building against the already-generated rules is sound here).

**`tools/check_license_containment.py`: 9 hard-class hits, unchanged, and 0 in any file this session
touched** (`game/`, `tools/verify_vram_rect_queue.py`, `docs/issues/003*`). All nine are in
`external/psxport` docs and tooling, which are not this repository's to edit.

## 8. What remains

1. **The pin was bumped** `7981f596 -> c777c320`, from the build receipt rather than the framework's
   HEAD, after the tree was built and gated against `c777c320`. The override differential exists only
   in that commit, so the bump is what this repository's verification is actually against.
2. **0x0113D7D0** — unchanged and owned by issues 0036-0038. This issue removes 0050 from the list of
   live hypotheses and does not advance the frontier itself.
3. **The two deliverable asks not addressed here**, stated plainly rather than implied:
   - **the Start/Cross skip route** — not started. No owned code, no measurement, nothing claimed.
   - **the two named unowned guest bodies**, the pool initialiser at `0x80012F10` and the ring
     producer behind `0x8001EFE8` — not started. Both are still guest-executed.
4. **`vram_rect::clear`/`upload` sampling** depends on framework finding 6.2. Until it is addressed,
   the `1 of 1` match for those two is one sample, and the honest strength of that evidence is one
   sample — which is why the 15-versus-1 comparison is in this issue rather than only in the log.
