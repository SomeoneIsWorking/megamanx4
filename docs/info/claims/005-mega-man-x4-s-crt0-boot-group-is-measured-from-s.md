---
id: C005
kind: claim
status: holds
created: 2026-08-12
tags: boot,crt0,re-01
depends: game/core/game_config.cpp
reconfirmed: 2026-08-24 23:09:42
verified_at: 2026-08-24 23:09:42
---

## Claim

Mega Man X4's crt0 boot group is measured from SLUS_005.61: BSS
`[0x8012F418,0x80175F38)` (size `0x46B20`), stack-top source `0x800DAF3C` with
no bias (`sp=0x80200000`), secondary stack-top source `0x8011CB74`, heap base
`0x80175F38` (size `0x820C8`), `gp=0x8012F418`, `libcInit=0x800EDCDC`,
`gameMain=0x80012024`, and `crt0=0x800DAE8C`. This crt0 has no heap-size or
heap-base globals.

## Evidence

The identity-checked 1,179,648-byte executable (SHA-1
`213733031136d095ca275d6957695aa25011cfa5`) was disassembled and symbolically
executed from `pc0=0x800DAE8C` through its terminating break. Its 43
instructions contain exactly one absolute store, `sw ra,-3048(at)` to
`0x8012F418`, which is the complete negative evidence for the absent heap
globals. Independent corroboration comes from the executable's BSS clear loop,
the decoded A(39h) InitHeap thunk, psxport's neutral PS-X EXE inspection, and a
recorded runtime that observed the stated SP, GP, heap, libcInit, and gameMain
values. The measured values are owned by `game/core/game_config.cpp`.

## What would falsify it

A fresh executable-derived boot inspection disagreeing with any owned value, or
a native/Lightrec trace of the authenticated image observing a different SP,
GP, heap base/size, libcInit, or gameMain at the corresponding boundary.
