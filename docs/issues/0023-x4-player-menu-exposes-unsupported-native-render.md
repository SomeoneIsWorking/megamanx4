---
id: 23
title: X4 player menu exposes unsupported native-renderer and interpolation controls
status: resolved
symptom: Mega Man X4's player menu offers Renderer/Native and 60fps interpolation even though the title is fixed to guest GTE and has no temporal product
tags: ui,rendering,fps60,scope,ownership
state_items: S005
created: 2026-08-26
updated: 2026-08-26
---

## Root cause

The player menu was a framework-wide static inventory: it offered every renderer and the temporal
interpolation toggle without asking the installed title runtime which products it actually owns.
Mega Man X4's former title-local startup guards already refused native rendering and synthetic
interpolation, but those guards were not connected to the player-facing menu or settings persistence.

## What was tried / dead ends

A game-owned copy of the framework menu was staged under `scratch/` to delete the two rows. That put
generic fonts/styles and a nearly identical document behind a second title-local asset pipeline, so
every future framework menu change could drift. It was removed in favor of one shared capability
consumer.

## Resolution

At psxport `99a42aa3`, one `RenderCapabilities` contract is consumed by render-path resolution,
settings persistence, and the live menu. Mega Man X4 declares the `widescreenOnly()` profile: GTE is
the player path, diagnostic PSX remains available outside the player renderer selector, native is
unsupported, and temporal interpolation is absent. The tracked title settings file no longer carries
`fps60=0` because unsupported keys are neither offered nor persisted.

The exact Clang consumer build passes 13/13 CTest gates, including the production runtime policy and
linked-binary temporal closure. The exact X11 product run at psxport `99a42aa3` then proved the player
surface: `scratch/screenshots/mmx4-capability-menu-99a42aa3.png` (SHA-256
`ade7e1bc3be312b4c436b05f21610842a5102a417aa5286ae5ff17a8c8c08582`) shows the Display pane with
exactly Aspect Ratio, Internal Resolution, and Face Ordering. Renderer and 60fps Interpolation are
absent.

The paired log `scratch/logs/mmx4-capability-x11-99a42aa3.log` (SHA-256
`e29a2c9e6f0040911f6f13e75207c29544ce80bf6bfa805514e07281bebb0d69`) records 33 live menu rows,
refuses the unsupported framework-native default, installs GTE, resolves `PSXPORT_X4_WIDESCREEN=true`
from its default layer, and publishes `320x240 -> 428x240` with OFX 214 and draw width 428. The process
was terminated by its captured PID after inspection. C032 records the combined static/link/live
evidence and S005 is verified.

The screenshot's surviving Aspect Ratio row says Vanilla while the readout says `render 428x240`.
That row does not control X4's guest-wide policy and remains open separately as issue #24; it does not
invalidate the removal proven here.
