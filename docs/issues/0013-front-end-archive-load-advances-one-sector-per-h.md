---
id: 13
title: Front-end archive load is instruction-time starved and restarts after four sectors
status: resolved
symptom: SLUS_005.61 reaches func_80012E38 but never returns to func_8001512C; each sector is delayed by sparse guest-instruction time and the title then restarts the same request after LBAs 222..225
tags: boot,cdrom,timing,framework,RE-04,next-boundary
created: 2026-08-22
updated: 2026-08-22
---

## Proven boundary and root cause

The retail scheduler/thread boundary is not the blocker. A focused FNTRACE run reaches
`func_8001D064`, `func_80012E38`, the request path, and alternate ready callback `0x80013E68`, but
the pinned framework never returns to initializer `0x8001512C`. Retail table entry `0x800F1118`
identifies request `0x40` as LBA 222, length `0x18800` (49 sectors).

The shared CDC scheduled every 2x ReadN sector at `Timing::guestInstructionTicks + 225792`. X4's
retail loader yields once per VSync, while a condensed host field wait advanced only the few guest
instructions executed between fields. The first indirect sector handler was therefore delayed from
frame 8 until frame 260. This is a time-domain ownership defect: physical CD deadlines used a sparse
instruction counter that did not advance across the emulated display-field time consumed by the
wait.

The apparent second failure was a consequence of the same defect. `PSXPORT_WWATCH` attributes the
restart exactly: after LBA 224, retail `func_80014C70` exhausts its 601-iteration wait, calls
`0x800E4DB0` at RA `0x80014D64`, writes `D_801406AC=0xC0`, and then rearms request `0x40`. It was not
an unexplained type-3 decoder or callback failure.

Two independent payload controls rule out sector framing as the cause. The RAM header for LBA 223
is `00 04 73 02` and advances the retail expected-position byte to `0xDF`. More strongly, all 2048
payload bytes delivered to guest RAM `0x8012F4B4` equal bytes 2048..4095 of the extracted retail
`ARC/LOAD_U.ARC` (matching SHA-256
`5d794589b763c29afcebbbae36611d81d4608811587ae89d2e1e5a5a8c811572`).

## What was tried / dead ends

- Capcom-logo/MDEC investigation was downstream of this defect: neither `PlayCapcomLogo`
  `0x8001D10C` nor `func_800182E8` was reached on the pinned framework; both are reached by the
  shared timing candidate.
- A bad three-byte position-header offset and shifted payload are ruled out by the two RAM controls
  above. Changing the LBA, request size, or skipping the retry would still be a magic-value workaround.
- `PSXPORT_NOPACE=1` is not a timing fix. A 35-second control still reaches `0x80012E38` once and
  never reaches `0x8001512C`, because host presentation pacing and the CDC's guest-instruction clock
  are separate.
- Do not add an X4 synchronous loader, force-success callback, reduced sector deadline, or local
  "fast CD" path. Each would bypass the retail callback/state machine and leave every other title
  using the same time owner broken.

## Resolution

The shared psxport candidate owns Q32 emulated CPU time across both instruction execution and
condensed display-field waits. Its X4 consumer run services LBA 225 onward, completes both startup
archives, reaches `0x8001512C`, `PlayCapcomLogo`, and the subsequent task entry with zero traced ABI
violations, and never writes the timeout-state `0xC0` during the first request. Final PRESENT-stage
captures at frames 800 and 1000 show the coherent Gte title screen after the real loading/logo path;
the normally paced control reproduces every reach frame and reports 49.27% / 50.31% non-black pixels.
No title-local CD override, reduced deadline, or synchronous-success path exists. Framework landing,
pin bump, and a fresh full project gate remain integration work, not an unresolved cause.

### Resolution (2026-08-22)
Resolved by the shared psxport emulated-time candidate: exact watchpoint attribution shows the LBA222..225 restart is retail func_80014C70 exhausting its 601-iteration wait, invoking 0x800E4DB0 at RA 0x80014D64, writing D_801406AC=0xC0, and rearming. The candidate advances authoritative emulated CPU time across condensed display-field waits, services LBA225 onward, and reaches 0x8001512C at frame 67 plus PlayCapcomLogo/task entry with zero traced ABI violations. Extracted LOAD_U.ARC LBA223 payload matches guest RAM byte-for-byte, independently ruling out sector/DMA shift. Evidence: scratch/logs/re04-baseline-state-watch.log and scratch/logs/re04-cdtime-candidate.log. Framework candidate remains unlanded, so pin/integration verification is still pending.
