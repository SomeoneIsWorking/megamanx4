---
id: C016
kind: claim
status: falsified
created: 2026-08-22
tags: architecture,widescreen,fps60
depends: game/core/x4_runtime.cpp#validateRenderEnhancements
reconfirmed: 2026-08-22 18:10:37
verified_at: 2026-08-22 18:10:37
falsified_on: 2026-08-26
---

## Claim

X4Runtime enforces SLUS_005.61's widescreen-only render target: synthetic temporal interpolation is unsupported while the retail 60 Hz cadence and widescreen target remain allowed

## Evidence

X4Runtime::validateRenderEnhancements reads only cv_fps60 after Game construction loads persisted settings; a true value refuses with a title/layer-specific error. mmx4_runtime_test proves the neutral default passes, a persisted Value-layer true fails, all temporal legacy hooks are null, targetsWidescreen is true, and native-depth/native-producer prerequisites are false. A real built megamanx4_port with PSXPORT_FPS60=1 exits 2 with the SLUS_005.61 refusal. Full Clang build and CTest pass 6/6.

## What would falsify it

X4Runtime stops rejecting a resolved interpolation request, any temporal hook becomes non-null, widescreen is blocked by this policy, or the USER changes the already-60fps widescreen-only scope

## Re-confirmed 2026-08-22 15:32:23

Post-format Clang built mmx4_runtime_test and megamanx4_port; cpp_policy and x4_runtime pass. The real built executable with PSXPORT_FPS60=1 exits 2 and names SLUS_005.61 plus the env layer, while validation reads no widescreen knob and the compile-time policy keeps targetsWidescreen true.

## Re-confirmed 2026-08-22 17:48:53

2026-08-22: x4_runtime CTest and behavior.py check pass after BIOS-thread integration; unsupported temporal interpolation remains refused.

## Boundary clarification 2026-08-22

This claim proves request-policy enforcement only: X4Runtime rejects enabling the synthetic tier. It
does not prove the shipping call graph is independent of interpolation-owned code. VBlank still calls
`Fps60::frame_commit` for the non-temporal frame fence; C018 is falsified and issue #12 tracks the
framework extraction. The narrower claim above remains true.

## Re-confirmed 2026-08-22 18:10:37

2026-08-22 clean psxport ad5cf802: x4_runtime and full CTest pass; synthetic interpolation remains rejected. This is request-policy evidence, not operational independence; C018/#12 remain unchanged.

## FALSIFIED 2026-08-26

X4Runtime::validateRenderEnhancements was removed when temporal policy moved to RenderCapabilities/Mods; unsupported fps60 is now omitted/refused without the title-local startup exit asserted by this claim.

> Anything that cited this claim as proof must be re-checked. Grep the repo for it.
