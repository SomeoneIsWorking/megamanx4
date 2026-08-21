---
id: C010
kind: claim
status: holds
created: 2026-08-21
tags: RE-04,cd,irq,HookEntryInt,recompiler
depends: psxport.pin, game/recomp_seeds.json, tools/verify_cd_irq.py, cmake/megamanx4_port.cmake
reconfirmed: 2026-08-21 11:16:05
verified_at: 2026-08-21 11:16:05
---

## Claim

Retail MMX4 services CD IRQ2 after the VBlank-only SysEnq element declines it by restoring HookEntryInt buffer 0x8011CBCC, resuming at 0x800E5194 with non-zero V0, and dispatching trapIntr slot 2 to libcd callback 0x800E7944; the recompiler therefore requires 0x800E5194 as a `main_reentry` seed.

## Evidence

tools/verify_cd_irq.py checks six retail/shipping groups and its 6/6 selftest rejects IRQ2 verifier polarity, the trapIntr edge, a missing or duplicated reentry seed, and the wrong callback slot. Retail emission is 6,193 seeds to 7,534 functions. scratch/logs/re04-pinned-runtime.log, built against recorded framework pin `9f1bb927`, shows I_STAT 0x004 delivered through the custom exit, FNTRACE 0x800E7944 reached five times from trapIntr slot 2 with zero ABI violations, sync result callback a0=2/a1=0x8013BA78, and execution advancing beyond the shared runtime's fail-loud non-local B0:17 unwind to the external 20-second bound; scratch/logs/re11-final-runtime.log is the pre-fix negative where IRQ2 remained pending and CdInit retried.

## What would falsify it

if the verifier accepts a missing 0x800E5194 reentry or wrong IRQ2 callback edge, if a rebuilt runtime does not reach 0x800E7944 from trapIntr slot 2, if I_STAT remains asserted after service, or if boot no longer advances beyond CdInit

## Re-confirmed 2026-08-21

The pinned verification used Clang 22.1.8 and exact psxport `9f1bb927`: verify_cd_irq passed six
groups and 6/6 selftests; bootstrap passed 2/2 with 6,193 seeds to 7,534 functions; CTest passed
4/4. The runtime reached CD callback `0x800E7944` five times and sync callback status 2/result
`0x8013BA78` with zero ABI violations, then ran to the external 20-second bound without watchdog or
capture overflow.
