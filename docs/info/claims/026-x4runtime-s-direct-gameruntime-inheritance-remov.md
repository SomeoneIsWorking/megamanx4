---
id: C026
kind: claim
status: holds
created: 2026-08-24
tags: architecture,fps60,inheritance
depends: game/core/x4_runtime.cpp#X4Runtime::X4Runtime
---

## Claim

X4Runtime's direct GameRuntime inheritance removes the concrete Fps60 implementation from the shipping binary; two framework temporal-helper translation-unit residues remain and issue #18 owns them

## Evidence

Before migration, nm -C reported 38 temporal symbols including the Fps60 vtable/methods/accessor. After direct inheritance and typed GuestProgramImage ownership, all concrete Fps60 symbols are absent; the strengthened verifier still correctly rejects game_fps60_* and gpu_fps60_* residues rather than claiming full closure.

## What would falsify it

a rebuilt shipping binary contains any Fps60 method, vtable, typeinfo, or fps60(Game&) accessor, or direct inheritance no longer provides the measured program image
