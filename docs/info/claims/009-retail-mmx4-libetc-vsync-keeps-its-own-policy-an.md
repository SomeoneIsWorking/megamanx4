---
id: C009
kind: claim
status: holds
created: 2026-08-21
tags: RE-11,vsync,vblank,irq
depends: psxport.pin, game/core/vsync_sync.cpp#deliver_field, tools/verify_vsync.py#verify
reconfirmed: 2026-08-21 13:14:32
verified_at: 2026-08-21 13:14:32
---

## Claim

Retail MMX4 libetc VSync keeps its own policy and delegates only counter waiting: helper 0x800E4EF8 waits on 0x8011DC50, while IRQ-0 handler 0x800E56FC increments that counter and walks eight callbacks at 0x8011DC30.

## Evidence

tools/verify_vsync.py checks six groups against retail SHA-1 213733031136d095ca275d6957695aa25011cfa5 and selftests 5/5, including broken-edge, seven-slot, collapsed-window, and raw-present-without-frame-fence refusals. Clang runtime installs only the exact helper window 0x800E4EF8..0x800E4F94. scratch/logs/re04-ce2-frame-commit-runtime.log, built against exact framework pin ce2c83ad, exercises blocking VSync for 20 seconds: the retail IRQ-0 handler advances the counter and the authoritative one-field frame commit presents, rotates the capture, and paces without a watchdog or overflow.

## What would falsify it

Falsified if the retail sites no longer decode to this counter/table/handler contract, if the shipping window admits code outside the helper, or if a real blocking VSync reaches the native helper and does not advance via the retail handler.

## Re-confirmed 2026-08-21 03:30:17

Final Clang runtime scratch/logs/re11-final-runtime.log installs 0x800E4EF8 and reaches guest main. It produces no x4-vsync field event before the CD IRQ2 boundary, preserving the claim's stated runtime gap. Static verifier remains 6 groups and selftest 4/4.

## Re-confirmed 2026-08-21 03:34:25

Final tree: verify_vsync check passes six retail contract groups and selftest 4/4; Clang build and full CTest 3/3 pass; scratch/logs/re11-final-runtime.log installs 0x800E4EF8 and reaches guest main, then confirms the declared runtime gap by stopping at unclaimed CD IRQ2 without entering the blocking helper.

## Re-confirmed 2026-08-21

Post-landing verify_vsync passed six retail contract groups and all four positive/opposite-answer selftests; scoped CTest passed 3/3.

## Re-confirmed 2026-08-21 12:05:51

tools/verify_vsync.py still derives six retail groups and now selftests 5/5, including refusal of a raw gpu_present path with no frame fence. Clang runtime scratch/logs/re04-frame-commit-runtime.log exercises blocking VSync for 20 seconds: retail IRQ-0 handler advances the counter, Fps60::frame_commit remains on the timeout backtrace, and no capture overflow or watchdog fault occurs.

## Re-confirmed 2026-08-21 13:14:32

Exact pin ce2c83ad: Clang CTest 4/4, verify_vsync six groups and 5/5 falsifiers, and untraced scratch/logs/re04-ce2-frame-commit-runtime.log runs 20 seconds with Fps60::frame_commit on the bounded-timeout stack and no capture overflow or watchdog fault.
