---
id: 24
title: Player Aspect Ratio row does not control X4 guest widescreen
status: open
symptom: The surviving player Aspect Ratio row changes a host-native setting that the GTE path ignores, while X4 guest widescreen is controlled by a separate title CVar
tags: ui,widescreen,rendering,ownership
state_items: S006
created: 2026-08-26
updated: 2026-08-26
---

## Root cause

The generic menu binds Aspect Ratio to `Mods::aspect`. That value controls the framework's
host-native video plan and is deliberately locked out when `RenderMode::enhancementsAllowed()` is
false. Mega Man X4 ships on the GTE path, where title-authored widescreen instead enters through
`X4Runtime::guestWidescreenProjection()` and the separate `PSXPORT_X4_WIDESCREEN` Boolean CVar.

The row therefore remains visible and cycles Vanilla/16:9/21:9/Auto, but none of those four labels is
the authority X4's guest projection reads. Its presence is not evidence that widescreen is working.

## Refused workaround

Do not copy or fork the shared menu into this title, map every non-4:3 row state onto X4's Boolean
16:9 policy, or claim the row works because the title's independent default is already on. Each would
leave player-visible text disagreeing with the behavior it controls.

## Proper boundary

The shared UI needs a title-authored aspect capability/binding that can describe the supported aspect
choices and route a selection to the guest projection owner. Mega Man X4 should then expose exactly
the choices its projection/controller implements, while the generic host-native binding remains the
owner for native-render titles.

This is follow-on work after issue #23's Native/60fps removal. Until it lands, verify X4 widescreen
through the title projection plan and actual output pixels/logs, not the generic Aspect Ratio row.

## Live confirmation

The exact psxport `99a42aa3` X11 product inspection made the split visible in one frame. The menu
readout reported `render 428x240`, while the surviving Aspect Ratio row reported Vanilla. Its paired
log resolved `PSXPORT_X4_WIDESCREEN=true` from the default layer and published the X4-owned guest
projection as `320x240 -> 428x240`, OFX 214, draw width 428. The title projection is active, but the
player row describes a different owner and therefore remains an open truthful-control defect.
