---
id: 18
title: Shipping X4 binary still links temporal helper TUs after direct runtime migration
status: resolved
symptom: No source-level Fps60 use and no temporal product is constructed, but nm still reports game_fps60_* and gpu_fps60_* helpers in megamanx4_port
tags: architecture,linkage,fps60,widescreen,framework
created: 2026-08-24
updated: 2026-08-24
---

## Root cause

X4Runtime inherited LegacyGameRuntimeAdapter, whose vtable TU owns `make_unique<Fps60>`; this pulled the complete Fps60 implementation into an already-60Hz title. Direct GameRuntime inheritance removes that concrete product. Two temporal helper groups remain because neutral services share translation units with temporal-only functions: FramePresenter needs gpu_native.cpp, which also defines gpu_fps60_present_pass; the ordinary fade accessor needs game_hooks_opt.cpp, which also defines game_fps60_* adapters.

## Refused workaround

Do not weaken the binary symbol gate, add an X4 allowlist, or rely on title-only dead stripping. Split the temporal helper ownership in psxport so neutral presentation/fade services do not link temporal-only functions.

## Falsifier

`python3 tools/verify_no_temporal_dependency.py --check --binary scratch/bin/megamanx4_port --selftest` passes after a Clang shipping link, and `nm -C` contains neither concrete Fps60 symbols nor game_fps60_*/gpu_fps60_* helpers.

### Resolution (2026-08-24)
Resolved at framework pin 7bd24f2b: temporal game/GPU helpers were split into dedicated translation units; the Clang megamanx4_port link and no_temporal_binary_dependency test contain no Fps60, game_fps60_*, or gpu_fps60_* symbols.
