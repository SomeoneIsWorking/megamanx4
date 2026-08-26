---
id: 19
title: Widescreen title composition is translated left because its 2D primitives never consume OFX
status: investigating
symptom: The 16:9 title image moves 162 host pixels left instead of exposing newly composed margins
tags: widescreen,title,2d,composition,RE-08
state_items: S006
created: 2026-08-24
updated: 2026-08-26
---

## Measured root cause

Matched frame 800/1000 PPMs are 1284x720. The 4:3 non-black bounds begin at host x=164; widescreen begins at x=0, a 164-pixel observed shift (the expected 54 guest-pixel margin scales to 162 host pixels). The frame-800 primitive dump contains 635 sprites, 635/635 marked 2D and 0 marked 3D. SetGeomOffset/OFX therefore moves none of this screen: it only re-centers GTE-projected 3D. Widening the draw/presentation span from 320 to 428 removes the host 4:3 pillarbox while the title-authored x coordinates remain 0..319, so the whole 2D composition becomes left-anchored.

Evidence: scratch/screenshots/re08-integrated-{4x3,wide}-f{800,1000}.ppm and scratch/logs/prims_f800.csv.

## Game-owned boundary

A direct read of SLUS_005.61's retail tables narrows this from "all 2D" to a front-end subsystem:
`D_800F21B0[1]` at `0x800F21B4` is `0x8001E708`, the title loop selected by
`game_info.unk0 == 1`. That loop owns title effect/misc/quad updates before the ordinary object draw.
The retail object tables identify misc title IDs `0x13 -> 0x800CB848` (TitleUpdate) and
`0x1D -> 0x800CDC84` (TitleLogoUpdate), plus quad ID `0x0B -> 0x800D76F8` (TitleUpdate2).
The matching decomp cross-read shows their authored fixed-screen positions (including x=144/208/216)
and `bg_offset=-1`; this is not camera-projected geometry.

The common object renderer at `0x80024334` is intentionally not a patch site: retail update/draw code
routes player, weapons, shots, visual, item, misc, unknown, and quad pools through it. Offsetting that
function would silently impose title composition on gameplay/HUD and is the blanket workaround this
issue refuses. The next implementation seam must be owned by the measured title state/subsystem and
derive any placement from the latched guest-wide plan, not repeat a literal 54-pixel correction.

## Retail coordinate publications

`tools/verify_title_composition.py` now grounds two title-only publication chains rather than stopping
at object ownership. Title mode 0 (`0x8001DCCC`) calls the quad allocator with ID `0x0B`, variant
`0x0A`. The ID and state tables reach initializer `0x800D6F94`, which indexes 16-byte rows at
`0x8010FCCC`; row `0x0A` is exactly `(319,0) (319,239) (0,239) (0,0)`. This is an authored 320x240
edge quad, not a camera projection or a renderer-wide placement rule.

Title mode 12 (`0x8001E54C`) creates nine misc ID `0x13` objects from variant list
`0x800F21F8`. Their title-only state-0 owner `0x800CB634` indexes six-byte rows at `0x8010E71C` and
publishes x/y as s16.16. The nine retail positions are `(128,72)`, `(176,72)`, `(144,72)`,
`(208,72)`, `(248,72)`, `(160,160)`, `(160,216)`, `(288,120)`, and `(176,216)`. This is the first
exact title layout seam: future widescreen work can distinguish the full-screen quad from menu/logo
placement at their title-owned sources without changing shared gameplay drawing semantics.

The verifier's 10/10 selftest mutates both coordinate chains, including the spawn variant, menu
variant list, x/y publication, one menu coordinate, and one white-quad edge. It still does not
classify every title primitive or prove the eventual wide pixels.

An exact-`dbdb2baf` real-disc run of the new retained/native initializer reached `0x800D6F94` and
passed mirror verification, but present samples at 120, 600, 1000, and 1100 through 1600 were the
same dark title field. The present instrument called that field 55.52% non-black because the display
rectangle is near-black rather than zero; visual inspection rejects that statistic as evidence of a
rendered logo. An earlier capture did contain the Mega Man logo, so frame-number sampling is not a
stable title-state selector. Future matched widescreen evidence must first select the same visible
state in both legs rather than treating a nonzero coverage percentage as a picture.

## Refused workaround

Do not add +54 to every 2D primitive in the renderer or shift the final image. That would make this title frame look centered while silently imposing one anchoring rule on gameplay HUD, full-width backgrounds, menus, and cinematics. Resolve the game-owned coordinate publications/subsystem classes and patch their semantic anchors.

## Next falsifier

Fresh matched-frame captures after the framework/API integration must show the title composition centered without moving the 3D gameplay center. A classified primitive census must distinguish center-safe UI, edge-anchored HUD, and full-width/background draws; any universal 2D translation fails this issue by design.
