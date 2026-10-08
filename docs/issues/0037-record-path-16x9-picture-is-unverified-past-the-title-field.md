---
id: 37
title: The record-path 16:9 picture is unverified past the title field
status: open
symptom: No reachable frame shows 3D, HUD, a fade over content or gameplay at 16:9, so margin content and 2D placement are unmeasured
tags: widescreen,record,evidence
state_items: S006
created: 2026-10-07
updated: 2026-10-07
---

## What is measured

X4 presents on psxport's record path. At 16:9 the framework plan keeps OFX 160 and RECT.w 320, the
seven cull sites widen by 54, and the record canvas is 428x240 (1284x720 at 3x). Headless runs,
`PSXPORT_SHOT_AT`, artifacts under `scratch/record/`:

- `y43` / `y169` (record, 4:3 / 16:9) against `yg43` / `yg169` (`PSXPORT_RENDER_PATH=gte`), presents
  1281, 1284, 1287, 1290. 1284-1290: the 16:9 record picture is the 4:3 picture centred with 162
  black host columns each side, pixel-identical to the GTE-path 16:9 capture scaled 3x, and its centre
  is pixel-identical to the 4:3 record picture. 1281 (the first fade-in step): record shows the faint
  field the device drew (`recordcheck` mismatched=0); the GTE path showed black.
- Every 15-bit present in 1,500 presents (264 of them) has `recordcheck` mismatched=0 at 4:3 and 16:9.

The title field is a 320-wide guest primitive, not a buffer-wide fill, so the margins stay black by
design.

## What is not measured

- Margin content from widened 3D or culled-in objects: no reachable frame draws any.
- HUD placement: no HUD is reachable. The record path does not move guest 2D; a HUD element that must
  anchor to the 16:9 edges needs a title producer.
- Fades over content, the title menu and the white logo quad (`title_quad`, authored 320 wide).
- 2D background layers at the margins in gameplay: if the stage BG draws only the 320-column window,
  the margins will show partial tiles or black.

## Blockers

The post-movie park (S002, issues 0028/0029/0036) and XA BGM holding the title at 4:3 with its draw
prefix skipped (`docs/issues/0038`).

## Next falsifier

Once a gameplay field is reachable by a title debug option, matched `PSXPORT_SHOT_AT` captures at 4:3
and 16:9 on the record path: the 16:9 centre must equal the 4:3 picture and the margins must show the
widened scene.
