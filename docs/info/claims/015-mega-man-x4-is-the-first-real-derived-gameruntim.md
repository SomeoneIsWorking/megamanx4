---
id: C015
kind: claim
status: holds
created: 2026-08-22
tags: architecture,game-runtime
depends: game/core/x4_runtime.cpp#bootInit
---

## Claim

Mega Man X4 is the first real derived GameRuntime consumer: its process-lifetime X4Runtime owns render-path selection, boot dispatch, and override installation while GameConfig/GameHooks remain measured compatibility debt only.

## Evidence

Clang built megamanx4_port and megamanx4_seam against committed psxport `7f5d3f13`; full CTest passed 6/6 including mmx4_runtime_test, which proves derived installation/Core snapshot, non-null measured legacy views, null legacy boot/override slots, and the unchanged gte/psx/native policy. A direct headless diagnostic reached X4Runtime::bootInit and dispatched measured gameMain 0x80012024.

## What would falsify it

main installs the legacy pair directly, boot or override callbacks return to GameHooks, render-path selection bypasses X4Runtime, or new behavior/facts grow the compatibility bags instead of a typed owner
