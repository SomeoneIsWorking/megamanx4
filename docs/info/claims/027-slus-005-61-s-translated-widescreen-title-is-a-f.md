---
id: C027
kind: claim
status: holds
created: 2026-08-24
tags: widescreen,title,architecture
depends: docs/issues/0019-widescreen-title-composition-is-translated-left.md
---

## Claim

SLUS_005.61's translated widescreen title is a fixed-screen front-end composition, and the shared object renderer is not a valid correction seam

## Evidence

Retail table bytes: D_800F21B0[1]=0x8001E708; misc IDs 0x13/0x1D resolve to 0x800CB848/0x800CDC84 and quad 0x0B to 0x800D76F8. The matching-decomp cross-read shows fixed x=144/208/216 with bg_offset=-1. Frame 800 has 635/635 2D sprites, while 0x80024334 is the common renderer for every object pool; issue #19 records bounds and refused blanket correction.

## What would falsify it

falsified if the retail table or call graph does not identify game_info state 1 as the title owner, or matched gameplay classification proves the title and every gameplay 2D class share one semantic anchoring rule
