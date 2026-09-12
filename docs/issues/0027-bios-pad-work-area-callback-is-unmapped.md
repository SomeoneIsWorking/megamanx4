---
id: 27
title: BIOS pad work-area callback is unmapped in the Lightrec product
status: investigating
symptom: The native/Lightrec product aborts before its first field when StartPAD jumps to 0x8000E884
tags: bios,pad,lightrec,boot,framework,RE-02
state_items: S002,S003
created: 2026-09-12
updated: 2026-09-12
---

## Measured cause

The Clang `megamanx4_port` built from title `fa363b6` against shared psxport `161cb132`
loads the authenticated `SLUS_005.61` (SHA-1
`213733031136d095ca275d6957695aa25011cfa5`), publishes the 428-wide guest
projection, then faults during the guest boot prefix at `0x8000E884` after 72,620
Lightrec cycles. Native dispatch reports no active code-image identity there; no
field or title picture has been reached.

The exact retail instruction chain explains that address. `InitPAD` calls
`0x800EE3A4`; at `0x800EE3B4` that function calls BIOS B0:0x57 (`GetB0Table`),
loads B0[0x5B] at `0x800EE3C0`, adds `0x884` and `0x894` at `0x800EE3C8` and
`0x800EE3D4`, and publishes the resulting callback pointers to
`0x8012F454/0x8012F458`. `StartPAD` calls `0x800EE37C` from `0x800EE174`;
the leaf loads `0x8012F454` and jumps through it. The shared HLE's
`Hle::workAreaInit()` publishes B0[0x5B] as `0x8000E000`, so the first target is
exactly `0x8000E884`. The resident title image begins at `0x80010000` and does
not own that BIOS work area.

The HLE publishes the work-area base but has no executable callback or native
service for these two BIOS pad offsets. Merely enlarging the title's image range
would give low RAM a false title identity and still leave callback behavior
unimplemented. Historical RAM snapshots contain zero words near `0x8000E884`,
but they predate this Lightrec run and do not establish its transient RAM bytes.

## Correct owner and discriminator

The shared BIOS/pad owner must implement the B0[0x5B] work-area callback contract,
including both start and stop entry points, through a real image or authenticated
host service. X4's existing per-field pad packet service can then consume its
measured buffers without title-local copies of Sony's pad machinery. The first
focused test should execute the shipping InitPAD/StartPAD path and check callback
dispatch and return state; a negative must refuse a missing or invalid work-area
publication. Then a bounded real-title Lightrec run must cross field one with
nonzero translated execution and explicit fallback telemetry.
