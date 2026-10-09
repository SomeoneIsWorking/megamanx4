---
id: 40
title: The record-path picture is corrupt at internal resolution above 1x (the Auto default)
status: closed
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

## Cause

psxport `runtime/psx/shaders_gpu/record.frag` `main` found a scaled pixel's native pixel with
`floor(vec2(p) / float(S))`. GPU float division is not exact, so at S = 3 the first row and column of each 3x3
block resolved to the native pixel before it: uploads, sprites and texel fetches there read the neighbouring
row or column. That is the torn rows and the vertical bars, and S = 2 was clean because the divide is exact.
The planner was not involved: the bad title record replayed from the device's previous VRAM matched the device
at 1x and missed it at 3x with zero entries, an upload of VRAM alone.

Not X4-only: Crash Bash Polar Push at `ires=3` showed torn HUD faces and timer digits from the same cause.

## Falsifier

Closes when the title menu and the demo stage at `ires=3` are visually identical to `ires=1` apart from
resolution, and a framework test over a scaled plan with a mid-field upload followed by a read of the uploaded
rectangle fails before the fix.

## Resolution

`record.frag` divides in integers. psxport `tests/test_record_raster.cpp`
`a_scaled_upload_and_a_read_of_it_fill_whole_blocks` (an upload, a sprite reading it, a wrapped upload, at
S = 3 and 5) failed before the fix with 2,622,095 mismatched scaled pixels and passes after. The title menu and
the first stage at `ires=3` show the same picture as `ires=1` apart from resolution, title presents report
`mismatched=0` at 3x, and the `ires=1` run to the first stage stays `mismatched=0` on every present.
