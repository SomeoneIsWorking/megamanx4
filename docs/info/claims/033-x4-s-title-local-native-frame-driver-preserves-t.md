---
id: C033
kind: claim
status: holds
created: 2026-08-27
tags: []
depends: game/core/x4_frame_driver.cpp#X4FrameDriver::stepFrame, game/core/vsync_sync.cpp#deliverField, game/core/x4_runtime.cpp#bootInit
---

## Claim

X4's title-local native frame driver preserves the finite 0x80012024 boot prefix and exact VSync-free one-field retail call order

## Evidence

Clang built the full port and 21/21 CTests against shared psxport 124b85c8. The frame-driver test exercises production bootPrefix/stepFrame, the ordered retail leaves, one field service, movie-active suspension, draw-buffer flip, and counter ownership. Isolated real-disc PID 3087406 and provenance-clean PID 3109960 each reconciled 90/90 fields without a guest VSync call or dropped layer; inspected movie frames 30/60/90 were coherent and both frame-30 24-bit VRAM buffers contained live pixels across columns 0..479.

## What would falsify it

Falsified if the generated 0x80012024 body changes, the driver call sequence or field-service count changes, full VSync is no longer trapped, or a combined product launch fails before/inside the native shell-driver boundary.
