---
id: 12
title: Non-temporal frame fence is owned by Fps60
status: resolved
symptom: The former framework path forced MMX4's non-temporal fence through Fps60 even when interpolation was inactive.
tags: architecture,framework,fps60,widescreen,dependency,frame-fence
created: 2026-08-22
updated: 2026-08-24
---

## Root cause

psxport unified both configurations by moving every non-diff RenderQueue flush into Fps60::rq_capture and making Fps60::frame_commit the only consumer. With Fps60::active() false, frame_commit skips rate detection and the extra interpolated pass, but still owns the real-frame presentPass(t=1), presentation ledger reconcile/reset, capture-slot rotation/reset, gpu_present_ex, debug capture, and gpu_pace_frame. Thus no lerp executes, yet the non-temporal frame boundary operationally depends on the interpolation subsystem and its temporal storage.

## Proper fix

Extract a neutral per-Game frame fence/presenter outside Fps60. It must own current-frame queue capture/sequence accumulation, real-frame emission, ledger reconciliation, one-field/whole-frame cadence, GPU present, diagnostic capture, and current-frame reset. Fps60 becomes an optional decorator/consumer that owns only previous-frame history, rate detection, temporal camera/object/background/billboard rotation, extra-pass scheduling, lerped re-render, and split-subframe pacing. X4 then calls the neutral commit(c, 1). Do not copy this pipeline into MMX4 and do not restore raw gpu_present plus a separate pacer.

## Integration status

The recorded 7bd24f2b framework exposes `Game::presentation`, makes the temporal product an optional
`GameRuntime` factory, and provides the typed guest-wide latch. X4 calls `presentation.commit(c, 1)`,
derives `GameRuntime` directly, uses its neutral temporal default, and has no title-local fence. That
direct migration removes the complete Fps60 implementation from the shipping binary. The same pin
separates temporal-only helper translation units; issue #18 records that completed split.

## Negative dependency gate

`tools/verify_no_temporal_dependency.py` is now in normal CTest. It scans all shipping `game/core`
sources and rejects fps60.h, Fps60 products/types, Game::fps60, FPS60 macros, the old frame_commit, and
temporal hook calls. Its neutral-present positive plus five mutation negatives prove both answers.
The Clang shipping link proves the direct-runtime consumer emits/presents/paces/reconciles/resets
without resolving an interpolation symbol.

## Existing gate debt

`tools/verify_vsync.py` now requires `c->game->presentation.commit(c, 1)` and retains raw
`gpu_present(c)` as a negative mutation. It passes six retail groups plus 8/8 controls, so the earlier
checker no longer mechanically requires the forbidden owner.

## Widescreen contract consequence

The neutral fence is also the atomic boundary for X4's guest-wide frame plan. X4 presents the
previously completed OT at VSync and then builds the next field, so a live widescreen toggle cannot
let projection, host draw clip, renderer margin coverage, and present sampling read independent
values. The inherited title request is fixed Gte geometry at 320x240 with retail OFX/OFY/H
160/120/512 and explicit 16:9; the framework resolver produces width 428, margin 54, OFX 214, and
host clip right 427. The completed plan is presented first, then the next plan is latched and its OFX
applied before the following OT. This contract remains disabled for Psx, ORACLE, and SBS and must not
relax `RenderMode::enhancementsAllowed()` or acquire Fps60/native-depth dependencies.

### Resolution (2026-08-24)
Resolved at framework pin 7bd24f2b: X4 commits fields through Game::presentation, constructs no Fps60 product, and full Clang CTest 11/11 includes the linked-binary temporal-symbol refusal.
