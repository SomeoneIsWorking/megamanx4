---
id: 40
title: The record-path picture is corrupt at internal resolution above 1x (the Auto default)
status: open
symptom: With `ires` above 1 the title and the demo stage show single-row displacements and a grid of vertical bars; the same fields at `ires=1` are clean and `recordcheck` reports mismatched=0
tags: render,record-path,ires,psxport
state_items: S004
created: 2026-10-09
updated: 2026-10-09
---

## Reproduction

Headless, `aspect=0`, post-movie title (menu after Start), one frame after the menu appears:

- `ires=3` (`PSXPORT_SETTINGS` copy of `psxport_settings.ini` with `ires=3`; `ires=0` is Auto and resolves to
  scale 3 on the headless 960x720 sink): the logo is torn into rows taken from other rows, purple row fragments
  sit outside the logo and a regular grid of vertical bars covers the background.
- `ires=1`: the same field is clean (logo, GAME START / CONTINUE / OPTION, planet) and every
  `recordcheck` line reports `mismatched=0`.

The guest VRAM dump (`vkvram 0 0 1024 512`) is clean in both, so the guest drew correctly and the defect is in
how the record rasterizer composes the picture above 1x.

## State

Not investigated beyond the reproduction. Suspect area: psxport `runtime/psx/gpu/gpu_vk_record_raster.cpp` and
`record_raster_setup.cpp` (`planRecord`, `PlanBuilder::textureReads`, `nativeOf`): a texture-read versus
VRAM-write ordering or a native-to-scaled rect conversion that only matters when `scale_` is above 1. X4 uploads
VRAM rectangles every field (`x4::vram_rect::upload`) and draws about 670 textured rects per title field, so
it exercises that path harder than the titles that were checked at 3x.

## Falsifier

Closes when the title menu and the demo stage at `ires=3` are visually identical to `ires=1` apart from
resolution, and a framework test over a scaled plan with a mid-field upload followed by a read of the uploaded
rectangle fails before the fix.
