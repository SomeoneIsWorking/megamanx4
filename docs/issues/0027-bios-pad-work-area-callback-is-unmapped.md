---
id: 27
title: BIOS pad work-area callback is unmapped in the Lightrec product
status: resolved
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
including both pad-enable and pad-disable entry points, through a real image or authenticated
host service. X4's existing per-field pad packet service can then consume its
measured buffers without title-local copies of Sony's pad machinery. The first
focused test should execute the shipping InitPAD/StartPAD path and check callback
dispatch and return state; a negative must refuse a missing or invalid work-area
publication. Then a bounded real-title Lightrec run must cross field one with
nonzero translated execution and explicit fallback telemetry.

## Shared correction and bounded product result

Shared psxport `b3fbe300` dispatches both
work-area leaves. The authenticated local SCPH-1001 v2.2 BIOS (SHA-1
`10155d8d6e6e832d6ea66db9bc098321fb5e8ebf`) aligns the documented
`B0[0x5B]+0x884/+0x894` leaves with stores of 1/0 to guest word `0x74B8`;
both return without changing V0. The shipping-path `test_bios_pad_work_area`
first failed at `0x8000E884`, then passed callback dispatch, guest flag,
StartPAD/StopPAD packet gating, and missing-publication negatives. The Clang
framework combined gate passed 146/146 tests after extracting the pad cases
from the capped HLE file.

One bounded retail-CHD run from title `f78a2a1` against the then-uncommitted
framework change that became `b3fbe300` crossed the former fault, completed the boot prefix,
entered the native frame loop, and completed archive/direct CD requests 64/65.
It then aborted before a committed field: the title's required-return guest
call received `FrameBoundary` at authenticated VSync `0x800E4DB0` after 706
cycles. The existing full-entry `PlatformHle` trap owns that result; issue #25
owns the next caller classification. This abort bypassed Lightrec shutdown
telemetry, so translated-block and fallback counts remain unknown. The BIOS
callback fault is resolved; issue #25 remains the product's first-frame blocker.
