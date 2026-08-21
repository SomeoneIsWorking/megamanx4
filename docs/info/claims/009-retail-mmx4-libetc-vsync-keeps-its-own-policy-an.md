---
id: C009
kind: claim
status: holds
created: 2026-08-21
tags: RE-11,vsync,vblank,irq
depends: game/core/vsync_sync.cpp#deliver_field, game/core/vsync_sync.cpp#wait_for_counter, game/core/vsync_sync.cpp#install, tools/verify_vsync.py#verify, game/core/game_config.cpp#g_x4_cfg
reconfirmed: 2026-08-21
verified_at: 2026-08-21 03:45:49
---

## Claim

Retail MMX4 libetc VSync keeps its own policy and delegates only counter waiting: helper 0x800E4EF8 waits on 0x8011DC50, while IRQ-0 handler 0x800E56FC increments that counter and walks eight callbacks at 0x8011DC30.

## Evidence

tools/verify_vsync.py checks six groups against retail SHA-1 213733031136d095ca275d6957695aa25011cfa5 and selftests 4/4, including broken-edge, seven-slot, and collapsed-window refusals. Clang runtime installs only the exact helper window 0x800E4EF8..0x800E4F94. The boot path does not yet execute the blocking helper, so runtime faithfulness beyond installation remains open.

## What would falsify it

Falsified if the retail sites no longer decode to this counter/table/handler contract, if the shipping window admits code outside the helper, or if a real blocking VSync reaches the native helper and does not advance via the retail handler.

## Re-confirmed 2026-08-21 03:30:17

Final Clang runtime scratch/logs/re11-final-runtime.log installs 0x800E4EF8 and reaches guest main. It produces no x4-vsync field event before the CD IRQ2 boundary, preserving the claim's stated runtime gap. Static verifier remains 6 groups and selftest 4/4.

## Re-confirmed 2026-08-21 03:34:25

Final tree: verify_vsync check passes six retail contract groups and selftest 4/4; Clang build and full CTest 3/3 pass; scratch/logs/re11-final-runtime.log installs 0x800E4EF8 and reaches guest main, then confirms the declared runtime gap by stopping at unclaimed CD IRQ2 without entering the blocking helper.

## Re-confirmed 2026-08-21

Post-landing verify_vsync passed six retail contract groups and all four positive/opposite-answer selftests; scoped CTest passed 3/3.
