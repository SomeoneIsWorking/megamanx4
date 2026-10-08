---
id: 36
title: Every run dies at presented field ~2,848 on a SysEnq element whose VERIFIER word is not code
status: open
symptom: Deterministic SIGSEGV at presented field ~2,848 after exactly 306 task-turn budget resumes
tags: frame-loop,irq,sysenq,crash
created: 2026-10-04
updated: 2026-10-04
---

Found while measuring the `task_resume_evidence` gate (`docs/project-state.md` S002), because that gate
cannot have a window long enough to reach a task turn that needs more than one display field of guest
CPU: the product dies first. This is that blocker, stated with its own measurement.

## What was measured

`build/ci/bin/megamanx4_port`, headless, silent, unpaced, `PSXPORT_NATIVE_FRAMES=3000`, twice, same
result both times:

- **306** `[x4-thread] retail task entry 0x8001DAF8 ... RESUMED at 0x… after ~564,4xx cycle(s)` lines,
  i.e. the whole run is 603 field-boundary turns (the STR pull's retry loop) followed by 306 whole-host-turn
  resumes;
- then, in the same order both times, the guest VBlank counter census at **field 5,696** and the exit
  status **139** (SIGSEGV):
  - `[irq:error] interrupt element 0x8013BBF8 has VERIFIER 0x0313AE20 at [0x8013BC00], which is in NO
    loaded code image; dispatching it would fault. handler=0x7841B000 mask=0x00580027`
  - `[x4-guest:error] guest call 0x80012600 exited fault at 0x0313AE20 after 0 cycles, and this owner has
    no return point for it: ambiguous code-image identity. 0 of the 32 general registers already hold
    that address`

The guest VBlank counter advances twice per presented field (issue 0028's measured doubling), so field
5,696 is presented field ~2,848. The cap is confirmed by construction: a 2,000-present run reaches only
field 3,968 and exits 0; a 2,840-present run with samples at 500/1000/1500/2000/2400/2700/2830 exits 0.

## Why this is its own issue and not 0028/0029

0028 and 0029 are about the guest PARKING in its own state machine on an unfinished CD read. This run
does not park: it is executing, it is uploading rectangles (the same runs log
`[x4-vram-rect] … append call(s) … REFUSED at kQueueEnd`), it is consuming hundreds of full host turns
of guest CPU, and then it dispatches a SysEnq interrupt element whose VERIFIER word is `0x0313AE20` —
a value that is not a guest address at all (`claimed by none`), so the framework refuses it and the
process dies inside that refusal. The three questions this issue therefore owns, none of them answered:

1. **who wrote `0x0313AE20` into `0x8013BC00`.** `0x8013BBF8` is the SysEnq element the boot log
   registers at priority 1 ("`[irq] registered interrupt element 0x8013BBF8 prio=1 (chain now 1)`"), and
   the framework reads its handler/verifier from the two words that follow. `handler=0x7841B000` is also
   not a guest address (and not a PSX RAM word either: bit 0 is set), so **two adjacent words of a live
   chain element hold values that are neither code nor data in any mapped space**. That is the shape of a
   store that landed on the wrong address, and issue 0035 is the same class of finding for a different
   store. Nothing in this port writes `0x8013BC00`.
2. **whether the SysEnq element that got here is the one the guest registered.** The boot line says the
   chain has exactly 1 element; the crash-time handler word is not executable, so the chain was mutated
   after registration. Who mutated it is not established.
3. **whether the guest's own exception path would have used this element at all.** `0x80012600` is the
   retail task scheduler and `0x80012600`'s caller here delivered it through the framework's
   custom-exception exit ("`[irq] pending I_STAT&I_MASK=0x004; no SysEnq element claimed it (1 in chain),
   custom exception exit installed`" at boot), so the call came from an interrupt handoff the port owns.

## Re-measured against psxport as of 18:24 local, same day

A 3,000-present run reproduces it exactly: **306** RESUMED lines, guest VBlank counter field 5,696, the
same `0x0313AE20` verifier refusal, exit **139**. Two things are now measured that were not before:

- the owner-published task-turn census (`x4::bios_threads::Service::reportCensus`, published from
  `game/boot/main.cpp` at the end of the frame loop) prints **`0 of 0` turns in a 200-present window** and
  **prints nothing at all in this run**, because the product dies before the loop returns. That is the
  measurement the `task_resume_evidence` gate was missing: its "0 task turns resumed" was an absence, and
  the run-end census makes the same number a count;
- the crash is downstream of 306 whole-host-turn resumes of task `0x8001DAF8`, so the CD work the task is
  doing at that point is not what leaves a valid SysEnq element behind.

## Falsifier

This closes when a 3,000-present run exits 0. It does NOT close the wall behind it: every sampled present
from 100 to 2,830 measured 0.00% non-black (`PSXPORT_PRESENT_SHOT_AT=100,200,…,2830`), so even with the
crash fixed, no present in this window satisfies `task_resume_evidence`'s 1% non-black floor. The picture
has to exist first, which is issue 0028/0029's subject.