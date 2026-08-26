---
id: C013
kind: claim
status: falsified
created: 2026-08-22
tags:
depends: game/core/x4_runtime.cpp#configureRenderPath
reconfirmed: 2026-08-22 15:30:37
verified_at: 2026-08-22 15:30:37
falsified_on: 2026-08-26
---

## Claim

Mega Man X4 now defaults to the guest GTE render path and refuses the producer-only native path.

## Evidence

game/core/x4_runtime.cpp sets only PSXPORT_RENDER_PATH Default to gte before framework resolution; mmx4_runtime_test passes and proves the same gte/psx/native policy now belongs to the derived runtime. The earlier bounded rebuilt run announced render path = gte, while an explicit native selection exited 2 with the missing-producer reason.

## What would falsify it

X4Runtime::configureRenderPath, game/core/main.cpp, or framework render-path semantics change; or X4 gains complete native producers.

## Re-confirmed 2026-08-22 15:30:37

mmx4_runtime_test after the render-policy change proves the unchanged gte default, diagnostic psx support, and explicit native refusal; full Clang CTest passes 6/6.

## FALSIFIED 2026-08-26

X4Runtime::configureRenderPath was removed when render-path policy moved to the shared RenderCapabilities resolver; unsupported Native now warns and resolves to GTE instead of exiting 2.

> Anything that cited this claim as proof must be re-checked. Grep the repo for it.
