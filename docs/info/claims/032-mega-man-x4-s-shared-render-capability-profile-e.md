---
id: C032
kind: claim
status: holds
created: 2026-08-26
tags: rendering,fps60,capabilities
depends: game/core/x4_runtime.h#renderCapabilities, tests/test_x4_runtime.cpp, psxport.pin
reconfirmed: 2026-08-26 23:56:14
verified_at: 2026-08-26 23:56:14
---

## Claim

Mega Man X4's shared render-capability profile exposes GTE as its only player renderer, excludes Native and temporal interpolation, neutralizes a persisted fps60 request, and links no Fps60 implementation

## Evidence

Exact psxport 99a42aa396eb810b7872c17bcc4610d21252a61c Clang 22 build and full CTest passed 13/13 in both the fresh capability tree and conventional build. mmx4_runtime_test exercises the production RenderCapabilities/Mods path, while verify_no_temporal_dependency reports 23 clean shipping sources and no Fps60 implementation across 44,454 linked symbols; selftest passed 11/11.

## What would falsify it

X4Runtime::renderCapabilities changes, shared menu/settings/render-path consumers stop honoring it, a live X4 menu shows Renderer or 60fps Interpolation, or the shipping link contains an Fps60 symbol

## Re-confirmed 2026-08-26 23:56:14

Exact psxport 99a42aa3 X11 product inspection: screenshot scratch/screenshots/mmx4-capability-menu-99a42aa3.png (SHA-256 ade7e1bc3be312b4c436b05f21610842a5102a417aa5286ae5ff17a8c8c08582) shows Display rows Aspect Ratio, Internal Resolution, and Face Ordering only—Renderer and 60fps Interpolation are absent. Paired log scratch/logs/mmx4-capability-x11-99a42aa3.log (SHA-256 e29a2c9e6f0040911f6f13e75207c29544ce80bf6bfa805514e07281bebb0d69) records unsupported native resolved to GTE, X4_WIDESCREEN=true at Default, menu 33 rows, and guest projection 320x240 -> 428x240 with OFX 214/draw width 428. The captured PID 2001596 was terminated after inspection. The generic Aspect Ratio row still said Vanilla and remains issue #24; it is not cited as the X4-wide control.
