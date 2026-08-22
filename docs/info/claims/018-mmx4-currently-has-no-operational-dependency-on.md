---
id: C018
kind: claim
status: falsified
created: 2026-08-22
tags: architecture,fps60,widescreen
depends: game/core/vsync_sync.cpp#deliver_field
falsified_on: 2026-08-22
---

## Claim

MMX4 currently has no operational dependency on psxport interpolation-owned code

## Evidence

Earlier scope prose treated the USER no-lerp decision as if the shipping dependency boundary already matched it.

## What would falsify it

Any shipping MMX4 source calls Fps60 or requires interpolation-owned capture/rotation/present state.

## FALSIFIED 2026-08-22

Observed on 2026-08-22: game/core/vsync_sync.cpp::deliver_field calls c->game->fps60.frame_commit(c,1). RenderQueue::flush routes every non-diff queue through Fps60::rq_capture even when active() is false; frame_commit then uses present_vk/presentPass(t=1), capture rotation, ledger reconciliation, gpu_present_ex, dumpPresent, and gpu_pace_frame. No interpolated pass executes, but operational independence is false.

> Anything that cited this claim as proof must be re-checked. Grep the repo for it.
