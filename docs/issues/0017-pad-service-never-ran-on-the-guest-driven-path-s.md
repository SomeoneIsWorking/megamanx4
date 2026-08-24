---
id: 17
title: Pad service never ran on the guest-driven path, so no host input binding reached the game
status: resolved
symptom: no input bindings; keyboard and gamepad do nothing; pad decode products never change; REPL/REPLAY/force input has no effect
tags: input,pad,framework,RE-06,co-op
created: 2026-08-24
updated: 2026-08-24
---

## Root cause
Pad::serviceFrame (host poll -> packet -> both InitPAD buffers) was called only from native_step_frame, Tomba!2's PC-driven frame loop. X4Runtime::bootInit dispatches the guest gameMain and never returns, so the service never ran and both measured packet buffers stayed at their init state.

## Fix
x4::vsync::deliver_field calls pad.serviceFrame() once per delivered field (the hardware per-VBlank SIO cadence). Slot-1 presence became an explicit framework policy, but X4 leaves it absent: the current host input owner has only one finalized mask, so reporting a connected slot 1 would mirror player 1 rather than provide a real second controller. RE-07's measured P2 route remains the seam for future distinct per-slot bindings.

## Evidence
Forced START -> P1 decode products 0x0800 (PADstart, PSY-Q convention); forced Select -> P2 trio 0x0100 (PADselect) with correct edge tracking. scratch/logs/input-probe1.log, input-p2b.log; router decompile scratch/decomp/x4_router.c. Claim C024. Distinct per-slot button masks remain future co-op work.
