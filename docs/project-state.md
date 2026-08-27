# Project state

Factual capability coverage for the Mega Man X4 enhancement port. Epic intent lives in
`docs/project-goals.md`, atomic work in `docs/issues/`, ownership in `docs/codemap.md`, and ordered
binary evidence in `docs/re-frontier.md`.

| ID | Capability / observable outcome | State | Dependencies | Goals |
|---|---|---|---|---|
| S001 | USA executable and disc inputs are reproducibly identified and provisioned | verified | — | G001 |
| S002 | Retail resident code is reproducibly recompiled into the shipping product | partial | S001 | G001 |
| S003 | Guest field service delivers retail timing, input, and audio work | partial | S002 | G001, G004 |
| S004 | The product boots and presents the retail front end through guest GTE rendering | partial | S002, S003 | G001, G002 |
| S005 | Player-visible renderer and cadence choices match the title's actual capabilities | verified | S004 | G001 |
| S006 | Title-owned widescreen composes correct 16:9 title and gameplay pictures | partial | S004 | G002 |
| S007 | Measured loading operations complete without loading-only waits or presentation | partial | S004 | G003 |
| S008 | A second player can join as the other hunter | missing | S003, S004 | G004 |
| S009 | Representative gameplay is verified playable end to end | missing | S003, S004 | G001 |

## Current focus

S006 is the current focus: resolve the measured fixed-320 title composition at title-owned coordinate
publications, then capture matched 4:3 and 16:9 title and gameplay fields.

## Capability details

### S001 — Reproducible retail inputs

Evidence: `tools/extract_exe.py`, `tools/resolve_disc.py`, and `tools/verify_decomp_targets.py` identify
`SLUS_005.61` as 1,179,648 bytes with SHA-1 `213733031136d095ca275d6957695aa25011cfa5`, matching the
pinned decomp target. No game bytes are tracked.

### S002 — Recompiled shipping substrate

The retail executable emits thousands of binary-rooted functions, links `megamanx4_port`, and retains
the generated dispatch/super-call seam. `tools/verify_recomp_bootstrap.py` and the Clang build cover
the resident substrate.

Gap: future indirect-only targets remain execution-derived, and full-game execution coverage is not
established by emission or linking.

### S003 — Guest field service

The title now exposes a finite boot prefix and a one-step `X4FrameDriver`. Focused production-seam
tests prove the measured retail call order, one field-service call, draw-buffer flip, and frame-counter
increment. That field service dispatches the current retail class-0 handler, pad packets, one SPU
advance, snapshot, and neutral presentation; full libetc VSync is trapped for every mode.

Live PID 2710117 proves the corrected shipping path writes `StDataReadyCallback` `0x800E8188` to
measured DMA3 slot `0x8011DC68`, leaves generic IRQ slot `0x8011CBA4` alone, fills a seven-chunk libstr
frame, arms DMA3 only on the final chunk, and dispatches `0x800E8188` at field 15. Narrow ring-watch
PID 2717335 proves state 3 -> 2 -> 4 -> 0 through DMA completion, `StGetNext`, and `StFreeRing`.
`X4FrameDriver` now preserves the retail blocking-movie transaction: while stream ownership is live,
it resumes at `UpdateTasks` instead of restarting the gameplay draw/clear prefix, then runs the retail
suffix when the movie releases. Real-disc PID 3087406 reconciled 90/90 fields without guest VSync or
a dropped layer; inspected presents 30/60/90 are coherent full-width movie frames. Its frame-30 VRAM
dump has nonzero pixels in every one of columns 0..479 in both 24-bit buffers, falsifying the prior
right-third-only corruption caused by the gameplay clear erasing words 0..319.

Gap: distinct shipping P2 host state is absent, the separate GetlocP/Sub-Q music path was not reached
and remains unaudited, and representative gameplay has not verified timing/input/audio together.

### S004 — Guest-rendered front end

The product reaches guest `gameMain`, crosses the BIOS-thread handoff, completes front-end archive
requests, and has rendered the Mega Man X title image through the GTE path. Native selection is not a
picture source because this title has no native graphics producers.

Gap: sampled title state is not deterministic, representative gameplay has not been reached and
inspected in the current combined product, and the open title-composition defect affects wide output.

### S005 — Truthful player capability surface

Evidence: Mega Man X4's title runtime declares the guest GTE path, no native renderer, and no temporal
interpolation. The tracked settings file no longer carries a synthetic `fps60` value, and unsupported
explicit requests are refused or resolved with a warning rather than silently activating a feature.
The exact psxport `99a42aa3` Clang build passes all 13 consumer gates; C032 records the source,
runtime-policy, shipping-link, and live product evidence. The exact X11 product menu contained only
Aspect Ratio, Internal Resolution, and Face Ordering on its Display pane: Renderer and 60fps
Interpolation were absent. The same run resolved the unsupported framework-native default to GTE and
logged the title's default-wide `320x240 -> 428x240` guest projection. Issue #23 records the resolved
atomic point; issue #24 separately owns the surviving generic Aspect Ratio row's false binding.

### S006 — Widescreen

The complete retail projection-writer census identifies one global setup. The title-owned controller
preserves 4:3 identity and changes only measured OFX and draw-environment width for a 16:9 plan.

Gap: issue #19 proves the title's all-2D 320-wide composition becomes left-anchored. Correct title and
gameplay margins, culling, HUD anchoring, and central scale remain visually unverified. Issue #24
also records that the shared player Aspect Ratio row changes host-native `Mods::aspect`, not X4's
title-authored guest projection policy, so it is not yet a truthful X4 widescreen control. The exact
live menu made the disagreement observable: its readout reported a 428-wide render while the generic
Aspect Ratio row still said Vanilla.

### S007 — Loading removal

The two measured direct/archive issuers can complete through their untouched setup and callback
mechanics without entering their retail loading waits. A bounded product run advanced through several
requests.

Gap: exact destination-byte comparison and captured absence of loading presentation remain open;
unrelated scripted waits and fades are not classified as loading.

### S008 — Drop-in co-op

Missing capability: the retail executable decodes two pads and the player/camera/spawn pillars are
mapped, but no second player object, independent P2 route, shared-camera policy, mid-stage join, or
co-op correctness gate exists.

### S009 — Verified representative gameplay

Missing capability: no current exact-build session demonstrates and visually inspects representative
stage gameplay with input, audio, saves, loading removal, and widescreen operating together.
