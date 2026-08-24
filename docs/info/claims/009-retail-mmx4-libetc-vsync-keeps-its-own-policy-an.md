---
id: C009
kind: claim
status: holds
created: 2026-08-21
tags: RE-11,vsync,vblank,irq
depends: psxport.pin, game/core/vsync_sync.cpp#deliver_field, tools/verify_vsync.py#verify
reconfirmed: 2026-08-25 00:56:30
verified_at: 2026-08-25 00:56:30
---

## Claim

Retail MMX4 libetc VSync keeps its own policy and delegates only counter waiting: helper 0x800E4EF8 waits on 0x8011DC50, while IRQ-0 handler 0x800E56FC increments that counter and walks eight callbacks at 0x8011DC30.

## Evidence

tools/verify_vsync.py checks six groups against retail SHA-1 213733031136d095ca275d6957695aa25011cfa5 and selftests 8/8, including broken-edge, seven-slot, collapsed-window, raw-present, hardcoded-handler, missing-pad-service, and missing-SPU-service refusals. Clang runtime installs only the exact helper window 0x800E4EF8..0x800E4F94. scratch/logs/re04-3418-frame-commit-runtime.log, built against exact framework pin 3418a79b, exercises blocking VSync for 20 seconds: the retail IRQ-0 handler advances the counter and the authoritative one-field frame commit presents, rotates the capture, and paces without a watchdog or overflow.

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

## Re-confirmed 2026-08-21

Post-landing ce2c83ad VSync verifier passed six retail groups and 5/5 falsifiers; the shipping helper uses frame_commit(c,1) and refuses raw present/pacing.

## Re-confirmed 2026-08-21 14:13:43

Exact pin 3418a79b: Clang CTest 4/4, verify_vsync six groups and 5/5 falsifiers, and untraced scratch/logs/re04-3418-frame-commit-runtime.log runs 20 seconds with Fps60::frame_commit on the bounded-timeout stack and no capture overflow or watchdog fault.

## Re-confirmed 2026-08-21

Post-landing Clang verification passed VSync shipping groups and 5/5 falsifiers; the 20-second runtime stayed in frame_commit pacing without overflow against psxport 3418a79b.

## Re-confirmed 2026-08-22 15:30:37

Full Clang CTest after the X4Runtime render-policy change passes verify_vsync's six retail groups and 5/5 falsifiers; the title policy touches no VBlank ownership.

## Architecture audit 2026-08-22

The runtime evidence remains valid, but “authoritative frame commit” describes current ownership, not
the correct subsystem boundary. With interpolation inactive, `Fps60::frame_commit` still owns the
current queue capture, real `t=1` present, ledger reconcile/reset, capture rotation, GPU present,
diagnostic capture hook, and pacing. Issue #12 requires extracting that non-temporal service; C018
records that operational independence is currently false.

## Re-confirmed 2026-08-22 18:10:37

2026-08-22 clean psxport ad5cf802: VSync evidence/selftest passes 6 groups and 5/5; bounded retail run advances through the helper without overflow. This confirms behavior only; C018 remains falsified and issue #12 remains open for the Fps60-owned non-temporal fence.

## Re-confirmed 2026-08-22 18:55:26

2026-08-22 candidate framework rerun: verify_vsync passes all six retail groups and 5/5 controls; full Clang CTest passes 7/7, and the real-disc candidate advances the exact helper through the retail IRQ-0 handler. Issue #12 remains open; this confirms retail behavior, not correct Fps60 ownership.

## Re-confirmed 2026-08-24 23:09:45

On commit a53c255 against clean psxport 9c2e3f1c, verify_vsync.py passed six retail contract groups plus all 8/8 opposite-answer cases. Full Clang CTest passed 11/11, and the bounded real-disc runtime delivered fields through the live class-0 handler chain while completing five synchronous disc requests and remaining live until timeout.

## Re-confirmed 2026-08-25 00:56:30

At the exact recorded framework pin 75456947 (named by both build/psxport_resolved.txt and scratch/build/player/psxport_resolved.txt), verify_vsync.py passed all 6 retail groups and 8/8 opposite-answer controls. The complete 9c2e3f1c..75456947 framework delta changes only Gte presentation policy/docs/tests, not VSync, IRQ, timing, or the X4 seam; the retained exact-pin frame-180 capture has 29,921/691,200 non-black pixels, so blocking field delivery/presentation advanced on this pin.
