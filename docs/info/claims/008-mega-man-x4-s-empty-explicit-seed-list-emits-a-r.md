---
id: C008
kind: claim
status: falsified
created: 2026-08-21
tags: recompiler bootstrap RE-02
depends: game/recomp_seeds.json, tools/verify_recomp_bootstrap.py, game/core/recomp_register.cpp, game/core/game_config.cpp
reconfirmed: 2026-08-21
verified_at: 2026-08-21 03:45:48
falsified_on: 2026-08-21
---

## Claim

Mega Man X4's empty explicit seed list emits a real resident substrate: 6,192 binary roots grow to 7,533 functions, including crt0 and gameMain, with zero overlays; the generated registry links and runtime reaches guest main

## Evidence

Retail SLUS_005.61 SHA-1 213733031136d095ca275d6957695aa25011cfa5; tools/verify_recomp_bootstrap.py --selftest 2/2; Clang megamanx4_port build; software-Vulkan bounded boot logs InitHeap then dispatching guest main() 0x80012024

## What would falsify it

if verify_recomp_bootstrap refuses the retail image, generated interface/range changes, the Clang port no longer links, or a bounded boot fails before guest-main dispatch for a substrate/routing reason

## Re-confirmed 2026-08-21 02:50:21

2026-08-21: verify_recomp_bootstrap.py --selftest 2/2 (6,192 -> 7,533, crt0/gameMain, zero overlays); Clang megamanx4_port linked; software-Vulkan boot reached InitHeap and guest main with no recomp miss before CD/VSync; CTest 2/2 against current dirty framework tree

## Re-confirmed 2026-08-21 03:00:02

2026-08-21 clean framework 2b5ef7b5: bootstrap selftest 2/2 (6192 -> 7533, crt0/gameMain, zero overlays); Clang megamanx4_port linked; CTest 2/2; software-Vulkan boot reached InitHeap and guest main with no recomp-MISS before the CD/VSync poll; pin check passed

## Re-confirmed 2026-08-21 03:15:01

2026-08-21 post-landing verify_recomp_bootstrap.py --check: 6192 binary roots -> 7533 functions; crt0/gameMain present; zero overlays; recompiler version 2026-08-12.1

## Re-confirmed 2026-08-21

Post-landing verify_recomp_bootstrap selftest passed 2/2: 6192 roots to 7533 functions and an out-of-text seed refusal.

## FALSIFIED 2026-08-21

Retail/live HookEntryInt evidence proved one required indirect mid-function re-entry at 0x800E5194; the explicit seed list is no longer empty and emission now yields 7,534 functions.

> Anything that cited this claim as proof must be re-checked. Grep the repo for it.
