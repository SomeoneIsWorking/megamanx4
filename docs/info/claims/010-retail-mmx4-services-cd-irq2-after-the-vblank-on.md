---
id: C010
kind: claim
status: holds
created: 2026-08-21
tags: RE-04,cd,irq,HookEntryInt,recompiler
depends: psxport.pin, tools/verify_cd_irq.py#verify, game/recomp_seeds.json
reconfirmed: 2026-08-21 13:14:32
verified_at: 2026-08-21 13:14:32
---

## Claim

Retail MMX4 services CD IRQ2 after the VBlank-only SysEnq element declines it by restoring HookEntryInt buffer 0x8011CBCC, resuming at 0x800E5194 with non-zero V0, and dispatching trapIntr slot 2 to libcd callback 0x800E7944; the recompiler therefore requires 0x800E5194 as a `main_reentry` seed.

## Evidence

tools/verify_cd_irq.py checks six retail/shipping groups and its 6/6 selftest rejects IRQ2 verifier polarity, the trapIntr edge, a missing or duplicated reentry seed, and the wrong callback slot. Retail emission is 6,193 seeds to 7,534 functions. scratch/logs/re04-pinned-runtime.log shows I_STAT 0x004 delivered through the custom exit and FNTRACE 0x800E7944 reached five times from trapIntr slot 2 with zero ABI violations; that callback-focused trace is used only for reach/ABI because it perturbs the later render-overflow symptom. Independent untraced scratch/logs/re04-ce2-frame-commit-runtime.log, built against exact framework pin ce2c83ad, shows Getstat, Init, Demute, and Setmode responses serviced with IRQ2 acknowledged, followed by paced main-loop frames. scratch/logs/re11-final-runtime.log is the pre-fix negative where IRQ2 remained pending and CdInit retried.

## What would falsify it

if the verifier accepts a missing 0x800E5194 reentry or wrong IRQ2 callback edge, if a rebuilt runtime does not reach 0x800E7944 from trapIntr slot 2, if I_STAT remains asserted after service, or if boot no longer advances beyond CdInit

## Re-confirmed 2026-08-21

The pinned verification used Clang 22.1.8 and exact psxport `9f1bb927`: verify_cd_irq passed six
groups and 6/6 selftests; bootstrap passed 2/2 with 6,193 seeds to 7,534 functions; CTest passed
4/4. The runtime reached CD callback `0x800E7944` five times and sync callback status 2/result
`0x8013BA78` with zero ABI violations. Its 20-second lack of a later capture overflow is not used as
progress evidence because callback FNTRACE perturbs that symptom.

## Re-confirmed 2026-08-21

Post-landing pinned Clang build and CTest 4/4 passed; verify_cd_irq passed six groups and 6/6; runtime reached 0x800E7944 five times with correct sync result and zero ABI violations.

## Re-confirmed 2026-08-21 12:08:50

The callback-focused FNTRACE remains valid only for callback reach/ABI, not as a forward-progress discriminator: it perturbs whether issue #10 reproduces. Independent untraced scratch/logs/re04-frame-commit-runtime.log shows Getstat, Init, Demute, and Setmode responses all serviced with IRQ2 acknowledged, then 20 seconds of paced main-loop frames. tools/verify_cd_irq.py remains six groups and 6/6 both-answer selftest.

## Re-confirmed 2026-08-21 13:14:32

Exact pin ce2c83ad: verify_cd_irq passes six groups and 6/6 falsifiers; fresh bootstrap emits 6,193 roots to 7,534 functions and selftests 2/2; untraced scratch/logs/re04-ce2-frame-commit-runtime.log services Getstat, Init, Demute, and Setmode through IRQ2 before paced fields.
