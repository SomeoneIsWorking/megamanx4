---
id: C003
kind: claim
status: falsified
created: 2026-08-12
tags: status
depends: game/core/game_config.cpp, docs/re-frontier.md
falsified_on: 2026-08-12
---

## Claim

this port has NO recompiled substrate and NO RE'd guest address: every GameConfig address field is 0

## Evidence

2026-08-12. game/core/game_config.cpp is all zeros except port facts (discEnvVar, cardEnvVar/cardDefaultPath, paceQuota=1, windowTitle, preserveVramBackdrop=1) plus three static constexpr PS-EXE header values that are deliberately NOT wired into the boot group; generated/ does not exist, so cmake does not configure megamanx4_port at all and says so with a STATUS message naming RE-01/RE-02. tools/re_frontier.py check: 10 entries parsed, 0 re-verified, 0 hack — every entry todo, blocked or skip-by-design. No binary has ever been built or run in this repo. THIS CLAIM EXISTS TO STOP A LATER SESSION READING SCAFFOLDING AS PROGRESS: the tree has a compiling seam, three enhancement CVars, a full registry set and a vendored matching decomp, and none of that is a single RE'd address.

## What would falsify it

any non-zero guest address appearing in game/core/game_config.cpp, or generated/rec_sources.cmake existing, or tools/re_frontier.py reporting a non-zero re-verified count

## FALSIFIED 2026-08-12

ITS OWN FALSIFIER FIRED, exactly as written: 'any non-zero guest address appearing in game/core/game_config.cpp'. RE-01 landed 2026-08-12 and the crt0 boot group is now ten MEASURED addresses (entry 0x800DAE8C, bss [0x8012F418,0x80175F38), stackTopBase 0x800DAF3C, stackTopBase2 0x8011CB74, heapBase 0x80175F38, gp 0x8012F418, libcInit 0x800EDCDC, gameMain 0x80012024, plus stackBias {1,0}), each re-derived from SLUS_005.61's own instruction stream by tools/verify_crt0.py and diffed against the shipping file by --check (PASSED, 19 comparisons). The claim's PURPOSE still stands and is now carried by C005: do not read scaffolding as progress. What has changed is only that ONE group is real. Still true and NOT superseded: generated/ does not exist, there is no megamanx4_port target, and no binary has been built or run in this repo.

> Anything that cited this claim as proof must be re-checked. Grep the repo for it.
