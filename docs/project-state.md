# Project state

Factual capability coverage for the Mega Man X4 enhancement port. Epic intent lives in
`docs/project-goals.md`, atomic work in `docs/issues/`, ownership in `docs/codemap.md`, and ordered
binary evidence in `docs/re-frontier.md`.

| ID | Capability / observable outcome | State | Dependencies | Goals |
|---|---|---|---|---|
| S001 | USA executable and disc inputs are reproducibly identified and provisioned | verified | — | G001 |
| S002 | The authenticated resident image runs through the native/Lightrec gameplay product | missing | S001 | G001 |
| S003 | Guest field service delivers retail timing, input, and audio work | partial | S001 | G001, G004 |
| S004 | The native/Lightrec product boots and presents the retail front end through guest GTE rendering | missing | S002, S003 | G001, G002 |
| S005 | Player-visible renderer and cadence choices match the title's actual capabilities | verified | S004 | G001 |
| S006 | Title-owned widescreen composes correct 16:9 title and gameplay pictures | partial | S004 | G002 |
| S007 | Measured loading operations complete without loading-only waits or presentation | partial | S004 | G003 |
| S008 | A second player can join as the other hunter | missing | S003, S004 | G004 |
| S009 | Representative gameplay is verified playable end to end | missing | S003, S004 | G001 |
| S010 | Asset-free hosted verification builds and checks the real supported host product boundary | verified | S002 | G001 |

## Current focus

S002 is the current focus. The first discriminator is the native/Lightrec product reaching the
existing 4,000-field front-end/movie frontier while executing nonzero Lightrec blocks and replacing
movie-body rewriting with runtime-authenticated VSync interception. The same shipping dispatcher
must exercise a native override and its scoped original call. Product inspection must prove that
Lightrec remains the default and no interpreter gameplay selector exists; runtime evidence must
report every bounded JIT-refusal fallback and satisfy its release threshold. That checkpoint is
followed by representative interactive gameplay.

## Hosted verification and host gaps

Linux x86_64 is the only currently supported host product boundary. The tracked GitHub Actions job
uses full history, disables persisted credentials and caches, installs pinned Python tooling, builds
the actual asset-free `megamanx4_port`, runs every asset-free title contract plus clang-format and
clang-tidy, and inspects the linked execution boundary. The consumer pins PSXPort
`eb5f23a8b3506f8853b3cfadcedc024cd90818a0`; CI checks out Lightrec
`b1457137c31cedff5f440d59da29401d021ba2da`. It contains no disc, executable, BIOS, or runtime
translation cache and therefore claims no gameplay evidence. The same canonical Python gate passes
locally and in the hosted run recorded in S010.

Windows x86_64 is an applicable future PC host but currently unsupported: psxport still exports GNU
linker `--wrap` options and has no MSVC/clang-cl product contract. macOS arm64 is likewise unsupported
while that GNU linker contract remains and no AppleClang package/runtime gate exists. Android arm64
is unsupported because this title has no Activity/JNI/package owner and does not yet consume the
shared Android build contract. Successful no-op jobs for those platforms would be false evidence, so
they remain explicit gaps rather than green matrix entries.

## Capability details

### S001 — Reproducible retail inputs

Evidence: `tools/extract_exe.py`, `tools/resolve_disc.py`, and `tools/verify_decomp_targets.py` identify
`SLUS_005.61` as 1,179,648 bytes with SHA-1 `213733031136d095ca275d6957695aa25011cfa5`, matching the
pinned decomp target. No game bytes are tracked.

### S002 — native/Lightrec gameplay product

Target: `megamanx4_port` loads the identity-checked executable as runtime data, installs
image-and-address-keyed native overrides, and enters it through psxport's per-Core Lightrec executor.
Lightrec owns translated-code memory and its cache. psxport owns CPU/machine synchronization,
HLE/device callbacks, bounded executor exits, override-aware original calls, and
executable-memory invalidation.

Missing capability: verified native/Lightrec gameplay. The target is wired to psxport's per-Core
Lightrec execution boundary, including shared
per-reason fallback telemetry and the bounded fallback threshold. Historical product runs establish
the 4,000-field native/device frontier but predate this executor and do not satisfy the current
execution contract. The next product evidence must contain nonzero Lightrec execution, a complete
fallback report, and a passing threshold.

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

The separate BGM path now has a binary-grounded finite owner for its first broken transition:
`0x80016E84` preserves `CdlSetmode(0x0E, 0xC8, 0x80139554)` and parks the retained
`BeforeObjectsB` call stack for the exact three native fields formerly delegated to guest VSync.
Focused command/result and frame-resumption contracts pass with the full VSync trap unchanged.

The CAPCOM intro release is also grounded: retail exits on authored frame 146, whose final video
chunk is LBA 14043. PID 3809268 reached cleanup `0x80018E50` at field 745, then the full trap caught
the next guest clock at `CdControlB(Pause) -> CdSync -> VSync(-1)`. The title-local
`cd_control_boundary` now routes only Pause through the synchronous CD owner, preserving success,
result, and stream-release state while leaving every other blocking command on its existing policy.
Its focused contract and the Clang shipping build pass. PID 3837919 crosses that exact Pause call in
the product without reaching guest CdSync/VSync; the next trap is the distinct direct `VSync(0)` at
cleanup return `0x80018E84`.

The complete `0x80018E50` caller is implemented as a retained-super FSM across all three authored fences:
1 field at `0x80018E84`, 3 after reset at `0x80018EBC`, and 3 after Setmode at `0x80018EDC`.
Hermetic tests prove exact call/RA/stack/result order, synchronous reset/mode state, zero guest VSync,
final-STR picture ownership after Pause, seven blocked `UpdateTasks` resumes, and one outer frame-tail
return. The native movie-cleanup and frame-driver contracts prove the measured direct caller return
`0x800184C4`, all seven authored field fences, and the final outer-frame continuation.

Corrected product PID 3980040 reaches that native owner at frame 811 with owner-preserving FNTRACE
and exposes the exact nested dependency: cleanup's Setmode call at return `0x80018ECC` reached
`CdControl 0x800E5D90`, whose non-loader policy called the original guest `CdSync -> VSync(-1)`. The title
now owns that exact command/return pair through synchronous `cd_controller::setMode`; every other
`CdControl` caller keeps its prior policy. The linked shipping test uses the actual Pause and Setmode
wrappers, completes all seven fields, publishes XA/CDC mode `0x80`, and dispatches zero guest VSync.
A forced retained-original Setmode negative aborts at the guest-VSync trap, proving the regression
would have caught the PID 3980040 failure. Product PID 4013759 then exits normally at its
4000-field cap with no guest VSync: cleanup enters once at frame 2402 and the field ledger shows the
exact 1+3+3 sequence around synchronous Setmode `0x80` before continuing. Inspected captures remain
CAPCOM through frame 2400 and then show the second authored `OP_U.STR` movie, so its 66.733-second
non-silent WAV is movie XA rather than BGM.

Disc and retail-table evidence ground that continuation. `OP_U.STR` is 27,699,200 bytes at LBA
14148 and contains 1,351 complete frames; general-movie entry 1 at `0x800F1D10` releases at authored
frame `0x542` (1346), whose final chunks are LBA 27613..27622. PID 4031142 crosses that release,
runs cleanup a second time, completes title archive requests 113/51, and writes BGM state 7 at product
field 2834. Its first state-7 `CdSync(1, nullptr)` then reaches retained `CdSync -> VSync(-1)` at
return `0x80016E9C`, before BGM Setmode or state 6.

The state-7 owner now calls the existing synchronous stock-Sony `cd_sync_stock_sync` authority at
that exact boundary and preserves the expected complete result `2`. The linked shipping regression
proves the native owner reaches Setmode and state 6 across its three fields without guest VSync; a
forced retained-original `0x80016E84` negative aborts at the music-CdSync guest-VSync trap. Full
Clang build, clang-tidy, and 25/25 CTests pass. A later diagnostic crossed this status owner and
exposed the next exact boundary: BGM `CdlSetmode(0x0E, 0xC8, 0x80139554)` at return `0x80016EC4`
entered retained `CdSync -> VSync(-1)`. Because its wrapper did not capture the short-lived game PID,
that observation is not accepted product proof.

The title now also owns only that authenticated BGM Setmode return edge through synchronous
`cd_controller::setMode`; the authored three-field fence remains in `music_stream`, and unrelated
CdControl callers keep their existing policy. The linked shipping path reaches state 6 with mode
`0xC8` and zero guest VSync. Its BGM-specific forced retained-original `0x800E5D90` negative aborts at
the CdControl guest-VSync trap. Full Clang build, clang-tidy, and 25/25 CTests pass. Product
proof and the following state 6/5/1 Setfilter/SeekL/ReadS/GetlocP chain remain open.

Exact-PID product run 4086465 exits normally at its 4000-field cap with no guest-VSync abort, but it
does not reach state 7: cleanup occurs once at field 2052 and the run ends in `OP_U.STR` at LBA
14265. The BGM owner and all later state/command traces remain zero. Its inspected captures are
CAPCOM/opening-movie guest VRAM rather than the title/menu or presented-picture evidence, and its
66.733-second non-silent WAV is movie XA. This does not prove or falsify the new BGM owners.

Gap: ground why the current exact-PID run reaches cleanup at field 2052 while the earlier same-tree
diagnostic reached it at 718/state 7 at 1550, then run a bounded product witness with presented-picture
captures around the grounded transition and prove the first later music boundary, title/menu, and
first audible `CdlReadS`; verify `CdlGetlocP`/Sub-Q if reached.
Distinct shipping P2 host state is absent, and representative gameplay timing/input/audio remain
unverified.

### S004 — native/Lightrec guest-rendered front end

The existing migration evidence reaches guest `gameMain`, crosses the BIOS-thread handoff, completes
front-end archive requests, and renders the Mega Man X title image through the GTE path. Native
selection is not a picture source because this title has no native graphics producers.

Missing capability: the front-end frontier reproduced through the native/Lightrec product. Its first bounded
gate is 4,000 fields with runtime-authenticated VSync interception; sampled title state also remains
nondeterministic, representative gameplay has not been reached and inspected, and the open
title-composition defect affects wide output.

### S005 — Truthful player capability surface

Evidence: Mega Man X4's title runtime declares the guest GTE path, no native renderer, and no temporal
interpolation. The tracked settings file no longer carries a synthetic `fps60` value, and unsupported
explicit requests are refused or resolved with a warning rather than silently activating a feature.
The historical exact psxport `99a42aa3` Clang build passes all 13 consumer gates; C032 records the source,
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

Missing capability: no native/Lightrec exact-build session demonstrates and visually inspects
representative stage gameplay with input, audio, saves, loading removal, and widescreen operating
together on each released host architecture.

### S010 — asset-free hosted verification

The Linux workflow and `tools/verify.py` own one reproducible asset-free gate over the shipping
product boundary, title contracts, formatting, lint, and linked execution policy.
Evidence: the Linux x86_64 asset-free product composition gate passed on main commit
`4cbdfd3e75ed87e9166d1a2711d270f3a8a2d320` in
[run 33960101702](https://github.com/SomeoneIsWorking/megamanx4/actions/runs/33960101702).
This verifies composition only; gameplay and unsupported host gaps remain as recorded above.
