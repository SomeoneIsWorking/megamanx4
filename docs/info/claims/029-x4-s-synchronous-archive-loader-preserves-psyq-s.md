---
id: C029
kind: claim
status: falsified
created: 2026-08-24
tags: RE-09,fastwait,runtime
depends: game/core/fast_wait.cpp#vsync
reconfirmed: 2026-08-24 23:09:53
verified_at: 2026-08-24 23:09:53
falsified_on: 2026-08-27
---

## Claim

X4's synchronous archive loader preserves PsyQ's VSync(-1) GPU-timeout query and completes the first real-disc request sequence without presenting from the loader scope

## Evidence

Retail/generated chain 0x80014780 -> 0x800147AC -> LoadImage 0x800148EC -> PsyQ set_alarm 0x800ECB38 calls VSync(-1); generated VSync returns 0x8011DC50 on the negative-query branch without entering the wait helper. The focused production-leaf test plants counter 317 and proves the scoped super-call returns 317 without mutating counter or phase. Full Clang CTest passes 11/11. A bounded 20-second uninstrumented real-disc run on psxport 7bd24f2b completed requests 64/65/113/51 as 49/6/154/3 sectors and remained live until timeout.

## What would falsify it

Falsified if any non-query VSync is admitted in Delivering, VSync(-1) returns a fabricated value or mutates loader/counter state, or a real archive request aborts or fails to reach terminal state through the current synchronous route.

## Re-confirmed 2026-08-24 23:06:36

Retail/generated chain 0x80014780 -> 0x800147AC -> LoadImage 0x800148EC -> PsyQ set_alarm 0x800ECB38 calls VSync(-1); generated VSync returns 0x8011DC50 on the negative-query branch without entering the wait helper. The focused production-leaf test plants counter 317 and proves the scoped super-call returns 317 without mutating counter or phase. Full Clang CTest passes 11/11. A bounded 20-second uninstrumented real-disc run on clean psxport 9c2e3f1c completed archive requests 64/113/51 as 49/154/3 sectors and direct requests 65/80 as 6/4 sectors, and remained live until the deliberate timeout.

## Re-confirmed 2026-08-24 23:09:53

On commit a53c255 against clean psxport 9c2e3f1c, full Clang CTest passed 11/11 including the counter-317 VSync(-1) focused control. A bounded 20-second uninstrumented real-disc run completed archive requests 64/113/51 as 49/154/3 sectors and direct requests 65/80 as 6/4 sectors, then remained live until deliberate timeout with no loader presentation or state fault.

## FALSIFIED 2026-08-27

The full VSync trap removes fast_wait's successful VSync(-1) super-call, so the synchronous archive route no longer preserves that guest query and must migrate its timeout owner.

> Anything that cited this claim as proof must be re-checked. Grep the repo for it.
