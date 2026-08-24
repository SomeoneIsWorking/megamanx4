---
id: C022
kind: claim
status: holds
created: 2026-08-24
tags: player-object,camera,input,spawn,RE-07,ghidra,mmx4
depends: game/core/player_object.h, tests/test_x4_player_object.cpp, docs/re-player-object.md
---

## Claim

RE-07's four pillars of Mega Man X4's player-object system are LOCATED and MEASURED from two
independent sources (AGPL mmx4 decomp symbols/headers + our own binary bytes — instruction
scans of extracted SLUS_005.61 and Ghidra decompiles of resident RAM): the player struct
(`g_Player = 0x801418C8`, PlayerObj 0xE4, measured field offsets incl. position halves at
+0xA/+0xE and character byte at +2), the camera owner (3 layer structs @ 0x801419B0 stride
0x54, scroll x/y at +0xA/+0xE per layer, mode-dispatched follow via table 0x800F3134 driven
by func_80027850 reading the player's position halves), the input route (libpad buffers
0x80166D68 / 0x8012F46C → router func_80012328 → P1 held/prev/edge 0x80166C08/C0A/C0C and a
decoded-but-unconsumed P2 trio 0x80166D50/D52/D54), and the spawn path (func_80035240 sets
active=1 and takes the character from engine byte 0x80172203; init_objects func_80023DB8 /
reset_objects func_8002A7D0 manage all pools; update_main_objects func_80021234 dispatches
table 0x800F24A4 by id).

## Evidence

docs/re-player-object.md carries the per-item table (source × fact). Denominators: binary
scan floors are 123 xrefs for 0x801418C8, 9 for 0x80175D58, 77 for controller_state
0x80166C0C, 128/112 sites for the camera scroll halfwords; function boundaries attributed
against our generated manifest (7,531 entries). The typed lens over these blocks is pinned by
ctest `x4_player_object` (positive planted-state reads through every accessor plus
non-aliasing negative classes); 9/9 ctest green and the boot gate reproduces frames
67/67/67/82/83 with ABI violations 0 after the change (scratch/logs/re07-postchange-bootgate.log).

## What would falsify it

- Any single address: a runtime probe (e.g. planting a marker via the debug server or an
  FNTRACE-guarded write) showing gameplay state NOT living at 0x801418C8 / 0x801419B0 /
  0x80166C08..0C falsifies the corresponding pillar.
- The struct offsets: `tests/test_x4_player_object.cpp` static_asserts and planted-offset
  checks fail to compile or run if a re-measurement contradicts them.
- The P2-unconsumed half of the input claim: ANY site outside func_80012328 found reading
  0x80166D50/D52/D54 falsifies it (the scan undercounts base-register-relative accesses, so
  this claim is stated as scan-supported, not exhaustive).
- The spawn chain: tracing func_80035240 during a real new-game flow that does NOT reach it,
  or reaching it without active becoming 1, falsifies the spawn-path description.
