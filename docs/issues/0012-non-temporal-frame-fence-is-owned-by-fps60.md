---
id: 12
title: Non-temporal frame fence is owned by Fps60
status: open
symptom: MMX4 rejects interpolation and never schedules an interpolated frame, but its shipping VBlank handler must call c->game->fps60.frame_commit(c,1); removing that dependency either loses presentation/pacing or lets RenderQueue captures accumulate until overflow.
tags: architecture,framework,fps60,widescreen,dependency,frame-fence
created: 2026-08-22
updated: 2026-08-22
---

## Root cause

psxport unified both configurations by moving every non-diff RenderQueue flush into Fps60::rq_capture and making Fps60::frame_commit the only consumer. With Fps60::active() false, frame_commit skips rate detection and the extra interpolated pass, but still owns the real-frame presentPass(t=1), presentation ledger reconcile/reset, capture-slot rotation/reset, gpu_present_ex, debug capture, and gpu_pace_frame. Thus no lerp executes, yet the non-temporal frame boundary operationally depends on the interpolation subsystem and its temporal storage.

## Proper fix

Extract a neutral per-Game frame fence/presenter outside Fps60. It must own current-frame queue capture/sequence accumulation, real-frame emission, ledger reconciliation, one-field/whole-frame cadence, GPU present, diagnostic capture, and current-frame reset. Fps60 becomes an optional decorator/consumer that owns only previous-frame history, rate detection, temporal camera/object/background/billboard rotation, extra-pass scheduling, lerped re-render, and split-subframe pacing. X4 then calls the neutral commit(c, 1). Do not copy this pipeline into MMX4 and do not restore raw gpu_present plus a separate pacer.

## Future negative dependency gate

After the extraction, add a first-party dependency gate to normal CTest that scans the shipping MMX4 source closure and rejects fps60.h, Fps60, c->game->fps60, FPS60_*, rate/interpolation hooks, and temporal-rotation entry points. Give it a positive fixture using only the neutral frame service and mutation negatives that inject a direct Fps60 call/include. The stronger framework control is a no-interpolation link configuration: build MMX4 without fps60.cpp and run a focused frame-fence test proving one captured queue is emitted once, presented once, paced for one guest field, reconciled/reset, and cannot call a poisoned interpolation service. The gate is blocked until the neutral framework API exists.

## Existing gate debt

`tools/verify_vsync.py` currently requires the literal
`c->game->fps60.frame_commit(c, 1)` and uses raw `gpu_present(c)` as its negative mutation. That was a
valid completeness gate for issue #10, but it now mechanically requires the forbidden owner. The
framework extraction must atomically retarget this verifier to the neutral one-field commit and retain
the raw-present negative, so the capture reset/presentation/pacing regression remains detectable while
the direct Fps60 dependency becomes forbidden.
