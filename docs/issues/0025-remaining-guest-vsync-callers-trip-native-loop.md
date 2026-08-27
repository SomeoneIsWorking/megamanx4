---
id: 25
title: Remaining guest VSync callers trip native frame ownership
status: open
symptom: Setup, loading, CD, movie, memory-card, or alarm code aborts at full VSync entry 0x800E4DB0
tags: frame-loop,vsync,timing,RE-09,RE-11
created: 2026-08-27
updated: 2026-08-27
---

## Finding

The native `X4FrameDriver` removes the main loop's `VSync(0)` call and owns one complete field. Full
libetc VSync is now a fail-fast PlatformHle trap for every mode, and the former successful helper and
fast-loader query/setup exceptions are gone. Generated code still contains 41 direct call edges from
23 functions, grouped across setup/loading, movie/display changes, memory-card/service code, libcd
waits, and alarm/deadline queries. Reaching any of them is now an ownership violation by design.

## Required fix

Classify each caller by semantic owner. Blocking setup/display transitions must become finite native
operations driven from the host loop; CD and alarm users must consume direct controller/clock state;
memory-card waits need their own host-owned service. Do not restore a mode-specific VSync success
path or fabricate counter values.

## Evidence and current limit

`tools/verify_vsync.py --check --selftest` proves the full-entry trap and absence of the old helper.
`x4_frame_driver` proves the main loop itself no longer calls VSync. The first combined product launch
falsified the former unobserved-startup assumption at guest `VSync(-1)`, RA `0x800E68FC`:
`bootPrefix -> 0x8001213C -> 0x80013588 -> CdInit -> CdReset -> CD_init -> CD_cw -> CD_sync ->
0x800E4DB0` (`scratch/logs/mmx4-native-loop-first-live.log`). The root cause is ownership, not a
controller timeout: title setup `0x80013588` is a finite initialization transaction but delegated its
completion clock to libcd before the native frame shell exists.

`game/core/startup_cd.{h,cpp}` now owns that whole title boundary. It retains `gen_func_80013588` as
the generated super, preserves the measured diagnostics, interrupt hook, CD/SPU volume init, three
callback publications, seven title-state clears, and final `0x80016334` call, while publishing
completed Setmode `0xA0` directly to the native controller and XA state. Its hermetic test rejects a
guest VSync/CdInit/CdControl dispatch and checks the exact retained leaf order, arguments, callback
RAM, title RAM, stack, and RA. Combined Clang build plus the second through sixth real-disc launches
cross that boundary without returning to its VSync call chain.

Those launches then grounded four independent downstream owners instead of treating each abort as a
mode exception. `gpu_timeout.*` replaces set_alarm `0x800ECB38`'s VSync(-1) query with the title's
native-owned field counter. `fast_wait.*` owns the complete direct/archive CD setup functions
`0x80013968` and `0x80013DA8`, omitting their now-meaningless VSync(3) settling delays only after the
scoped native CD commands complete. `display_init.*` owns `0x800185F8` and publishes both retail draw
environments without its nested VSync(0). The fifth and sixth real-disc runs consequently completed
archive request 64 (49 sectors) and direct request 65 (6 sectors) before reaching the next distinct
frontier (`0x80018788`, STR/MDEC movie-stream startup, through libcd VSync(-1)). Focused Clang tests
cover each finite owner.

The next real-disc run crossed the native `0x80018788` startup and its first retained
`StCdInterrupt`, then presented 240 black fields before the bounded first-frame poll failed and its
cleanup reached `VSync(-1)` through `0x80018E50 -> CdControlB`. That cleanup call is a consequence,
not a new timing owner: libstr never received a ready ring entry. Retail `DMACallback` at
`0x800E59A0` stores per-channel callbacks in the seven-entry table at `0x8011DC5C`, so DMA3's slot is
`0x8011DC68`. The native startup instead wrote `StDataReadyCallback` `0x800E8188` to `0x8011CBA4`,
which is the distinct generic IRQ-class-3 slot, while `GameConfig::dmaCallbackTable` remained zero.
The framework therefore acknowledged the armed DMA3 completion with no callback; the ring header
stayed in state 3, while `StGetNext` accepts only state 2.

`stream_startup::installReadCallbacks` now preserves the generic IRQ slot, writes the callback to
`0x8011DC68`, and `GameConfig` publishes the measured `0x8011DC5C` base. Focused shipping-helper and
runtime-config checks cover that address derivation. Fresh Clang-linked PID 2710117 then proved the
live publication at field 8, DMA3 fill of seven chunks at `0x80192000`, final-chunk interrupt arming,
slot resolution to `0x8011DC68`, and execution of `0x800E8188` at field 15. It also proved the native
XA movie path starts at LBA 12947 and decodes matching file-1/channel-1 sectors. Narrow ring-watch
PID 2717335 proves the complete first-frame state chain rather than merely inferring it: the seven
chunk headers become state 3, callback `0x800E8188` publishes state 2 to `0x80192000`, `StGetNext`
changes that same slot to state 4, and `StFreeRing` clears all seven headers to state 0. The fatal
VSync(0) at `0x80018BC4` was therefore the next `0x80018B88` invocation waiting for frame two while
the blocking movie loop still occupied one host `stepFrame`; it was not a callback-table or ring-index
defect. `X4FrameDriver` now preserves that blocking transaction across host fields by resuming at
`UpdateTasks`, skipping the gameplay draw/clear prefix while stream ownership remains live, and
running the suffix when the movie releases. Real-disc PID 3087406 completed 90/90 fields with no guest
VSync and coherent inspected presents at 30/60/90. Its frame-30 VRAM dump has nonzero pixels across
all columns 0..479 in both movie buffers; before this fix, the active buffer had data only in columns
320..479 because the restarted gameplay clear erased words 0..319. No GetlocP/command `0x11` or later
BGM trigger was reached; movie XA decode is not evidence that the user's separate music regression is
fixed.

## Falsifier

A generated-call census reaches zero, or a bounded product run exercises every classified owner with
the full trap armed and no guest VSync abort.
