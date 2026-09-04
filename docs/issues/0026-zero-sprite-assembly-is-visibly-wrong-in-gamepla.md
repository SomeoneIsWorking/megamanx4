---
id: 26
title: Zero sprite assembly is visibly wrong in gameplay captures
status: investigating
symptom: Player and foreground sprite pieces appear overlapped or misassembled in MMX4 gameplay, and the same defect is present in raw guest VRAM and the GTE-presented image
tags: rendering,sprite,guest-state,packet,assets
state_items: S004
created: 2026-08-27
updated: 2026-08-27
---

## Current localization

The visible defect is upstream of the player-facing GTE presenter. The 2026-08-27 bounded gameplay
run captured both representations at the same presentation fields:

- `scratch/screenshots/shot_{1800,2400}.ppm` are the guest GPU/VRAM pictures at 428x240.
- `scratch/screenshots/present_{1800,2400}.ppm` are the corresponding GTE-path 960x720 pictures.

Zero's overlapping/segmented assembly and the duplicated foreground forms are already present in the
guest VRAM captures. Cropping the 960x720 presentation to its 960x538 aspect-fit image and scaling it
back to 428x240 gives normalized RMSE 0.0134 at field 1800 and 0.0102 at field 2400 with point/box
sampling. The remaining small difference is raster/scaling behavior; it does not create the visible
assembly defect. Therefore changing the GTE renderer, enabling the unsupported native renderer, or
adding interpolation cannot fix this symptom.

The retail common object draw `0x80024334` constructs each animation as a list of 16x16 SPRT/FT4
packets from the object's animation table, world/camera position, flip flags, decompressed frame
texture, and scratchpad packet/OT cursors. It does not use GTE projection. The defect must be isolated
among guest animation state/table contents, decompressed player texture uploads, packet generation or
ordering, or earlier asset-load state.

## What was tried / dead ends

- Renderer-only diagnosis: rejected because the raw guest GPU result already contains the symptom.
- Widescreen OFX diagnosis: rejected for sprite assembly. OFX affects GTE-projected geometry, while
  `0x80024334` publishes direct screen-space sprite positions. The separate 320-of-428 left-anchoring
  defect remains issue #19/S006 and must not be conflated with this issue.
- Frame-loop call-order suspicion: the title's `X4FrameDriver` currently transcribes the measured
  `0x80012024` loop order exactly. That structural equality is not an oracle for sprite state, so a fresh
  live reference comparison remains required.

## Next falsifier

After the current STR/XA startup frontier again permits representative gameplay, capture the same
deterministic field with widescreen off/on and the diagnostic PSX/GTE paths. Dump the `0x80024334`
player packets together with `g_Player` animation fields (`+0x38/+0x3c/+0x47..+0x49`), camera-relative
origin, animation-list bytes, and the queued VRAM upload rectangles. A reference-emulator capture or
state trace from the same disc/input sequence must identify the first differing fact. Do not patch
coordinates, UVs, or animation indices before that first divergence is known.
