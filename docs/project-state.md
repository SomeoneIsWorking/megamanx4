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

**Reading the fault's own numbers (issue 0036, corrected).** The stop is a **dispatch to a non-guest
word**: the guest computed `0x0113D7D0` and called it, and the framework's
`ambiguous code-image identity` is its honest name for "not a guest address at all". Two halves of the
old frontier needed correcting, and both were checked rather than assumed:

* **The call site is now decoded correctly** and the fault's numbers are self-consistent: the override
  entry `0x80012600` has exactly one static `jal` caller at `0x800120E4`, and a MIPS `jal` sets
  `$ra = PC + 8 = 0x800120EC`, which is precisely the reported `returnPc`/`ra`. An earlier draft called
  that a discrepancy; the discrepancy was the note's own misapplied calling convention.
* **The word is never seen at rest.** `tools/probe_class0_table.py` measured it absent at **0 of 97**
  spot observations over 14,297 frames and **0 of 41,984** word-reads over frames 15–13,426, while
  `0x8011CB98` held a stable, plausible `0x800DD7FC` at every observation including the fault, and
  `0 of 294,912` static image words hold it. So the recorded claim that the table entry "holds"
  `0x0113D7D0` is wrong, and **the frontier is now "what computes it" rather than "where is it"** —
  a value never observed in memory was produced transiently, and `0x0113` as a top half is the
  signature of a packed pair read as an address.

**Issue 0007 records the three decoding traps this session hit in this title** (a PS-X EXE's text
loads from file offset `0x800`, a J-type target is not PC-relative, and `jal` links to PC+8), each of
which produced a *plausible* wrong answer, and corrects the workspace map's false claim that
`llvm-objdump` "misdecodes" this image when in fact it refuses it — a false claim that had pushed a
call-site listing to be hand-decoded, and 5 of its 7 targets were wrong.

## Hosted verification and host gaps

Linux x86_64 is the only currently supported host product boundary. The tracked GitHub Actions job
uses full history, disables persisted credentials and caches, installs pinned Python tooling, builds
the actual asset-free `megamanx4_port`, runs every asset-free title contract plus clang-format and
clang-tidy, and inspects the linked execution boundary. The consumer pins PSXPort
`9e104d9fe7d04043d98fe451732596d68e45022c`; CI checks out Lightrec
`b1457137c31cedff5f440d59da29401d021ba2da`. It contains no disc, executable, BIOS, or runtime
translation cache and therefore claims no gameplay evidence. The same canonical Python gate passes
locally and in the historical hosted run recorded in S010. The loader/GTE header migration was
compiled and linted locally against the corrected pin. The previous hosted run
[34222192563](https://github.com/SomeoneIsWorking/megamanx4/actions/runs/34222192563) instead fetched
the stale `eb5f23a8` pin and failed because that revision lacks the authoritative declarations.
The immediately preceding run
[34684883795](https://github.com/SomeoneIsWorking/megamanx4/actions/runs/34684883795) used the
consumer's then-recorded `a5a79652` pin and failed in framework `runtime/psx/repl.cpp`: the callback
had migrated to `std::span<char>` but the pinned source still passed a raw `char*`. Framework commit
`9e104d9f` constructs the span at that boundary; this repo now records that commit. A hosted rerun
is required before S010 can be re-verified at this pin; focused local checks do not establish
whole-product verification at this revision.

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
execution contract. A bounded retail run against the shared BIOS/pad correction that became
`b3fbe300` crossed the former `0x8000E884` fault, completed the boot prefix and two CD requests,
then aborted before field one when an existing libetc VSync `FrameBoundary` at `0x800E4DB0`
reached a required-return guest call (issue #25). That abort bypassed shutdown telemetry;
translated-block and fallback counts are still unknown. The next product evidence must classify
the VSync caller, complete a field, report nonzero translated Lightrec execution and every fallback
reason, and pass the threshold.

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
title-authored guest projection policy, so it is not yet a truthful X4 widescreen control. A live menu
made the disagreement observable: its readout reported a 428-wide render while the generic Aspect
Ratio row still said Vanilla.

**MEASURED 2026-09-27 (superseding the note below, which was measured on a shorter horizon).** The wide
plan IS latched and IS reachable, and it now **STAYS** at `render_width=428` after the movies
complete — because the movie does complete. `0x80018E50` is entered at display field 974
(`ra=0x800184C4`, entry-one driver) and field 13,153 (`ra=0x800181DC`, indexed driver),
`movieCleanup.completedFields()` is 7/7 at both, `cd.stream_active` reaches 0 between fields 13,000
and 13,500, the guest's own field counter `0x80141BD8` leaves its movie-frozen 7 and reaches 351,
archive CD requests 113 and 51 complete, and the display-mode init's own `GP1(08)` 15-bit 320x240
switch and its `VSync(-1)` at `0x800E68F4` are both passed. The `[wide]` change log's last line is
`render_width=428` (printed on change only, so the tail IS the steady state).

**And the post-movie picture is still not a gameplay picture, so the pair still cannot be judged —
but the reason is now a different, measured one, and the previous reason was wrong.** Issue 0028's
earlier reading ("the guest waits at `0x80021858`, which writes DPCR and walks a 6,144-byte DMA chain
at `0x80173CA0` polling the flag byte `0x801721D7`") is **retired as factually wrong**:
`0x80021858` is the decomp's `update_misc_objects`, its walk cursor is **scratchpad `0x1F800064`**
(`lui $1,0x1f80` is 0x1F800000, not 0x1F801000), `0x80173CA0` is `misc_objects` — 96 records of 0x60
bytes, `size:0x1800` in the decomp — and `0x801721D7` is `engine_obj_17`, a guest struct field with
four guest store sites and no product writer.

What is measured instead: the guest **parks**, and it parks in its own state machine at game state 1 /
sub-state 2 (`game_info` `0x80173C70` = `0x00000201`, byte-identical at presents 15,006 / 20,023 /
23,218). Sub-state 2 is `0x8001DDB0`, which returns immediately unless `[0x80173C84] == 2`, and that
byte is raised in exactly one place (`0x80016BB8`) behind a `CdControl(0x1B, 0, $16)` that must be
**accepted** while the CD stream from `0x800127C8`'s per-iteration `CD_cw(0x1B, 0x7F, 0xFF000000)` is
still running. The CD path is alive (129,513 register accesses in 14,000 presents, `CdSync` status
0x19, data-ready `0x800E7944`, CD IRQ `0xE0`/`0xE1`) and never completes. **The host must complete the
guest's streaming `CD_cw(0x1B)` read**, which is a modelling gap in the CD owner, not a flag to raise.

Motion, measured on CONSECUTIVE presents with denominators by the new
`tools/probe_post_movie_motion.py`: every post-movie frame is **2 distinct colours** (`#080810`,
`#000000`), and every consecutive pair **DIFFERS** by 2,394/924,480 pixels (0.259% wide) inside a
**798×3 band at y=717**, mean |delta| 10.67/255. So the earlier "byte-identical across four
checkpoints" reading is falsified — the picture is not frozen — but the guest still **does not animate
a scene**: it submits 2 prims per frame (a full-screen black `GP0(0x60)` rect and a full-screen
`GP0(0x28)` Gouraud triangle), and `misc_objects` is 1/96 populated. `widescreen_pair.py` therefore
still REFUSES with the same two `NOT SCENE` margins. Steady-state `render_width` is **428** on the 16:9
leg and **320** on the 4:3 leg, and on the wide leg every `render_width` transition is 1:1 correlated
(within 1–13 ms) with the guest's own `GP1(08)` display-depth switch — the guest's last act in the run
is to leave 24-bit mode, so the tail is 428 and the plan is a re-latch from the guest's display mode,
not a half-duty latch.

One further defect was found and is recorded in issue 0028: **the guest's display-field clock runs at
2× the presented cadence** (8/8 `step 1` calls advanced `0x8011DC50` by exactly 2; a 200-present run
emits exactly 200 `deliverField` calls, so the extra increment arrives from the framework's
`Timing::raiseVBlank` path, which X4 does not opt out of). It is not established as the cause of the
empty object list and is reported rather than guessed at.

**MEASURED 2026-09-28 (issue 0035) — THE STAGE-LOAD FAULT IS GONE AT ROOT CAUSE, and the game goes
1,652 display fields further.** The fatal `0x26010006` dispatch is **absent**: it does not appear
once in a run that previously ended on it. The guest now reaches display field **31,166** against
the fault's **29,514**, and the reason it stops is a **different, already-guarded** condition —
`vsync_sync.cpp`'s own `guest::call(c, vblankHandler)` refusing a **non-guest** entry word,
`0x0113D7D0`, read from the guest's class-0 interrupt table at `0x8011CB98`. A first run of the
owner, built with the twenty-bit stream mask the gate later caught as wrong, stopped earlier and
differently — on `kMaxTurnFields = 512` budget exhaustions without a field boundary, at
`0x800312B4`, inside the later stage-load stage whose per-entity loop is `0x80094F74` — so
**31,166 display fields is the SUPERSEDED number and is not claimed here.** Both stops are reached,
not caused: the queue owner provably stores only inside `[0x801659D0, 0x80165A30)`, and its bound is
a membership test over that range, so it cannot have written `0x0113D7D0`.

**MEASURED 2026-09-29 (issue 0037) — and the MECHANISM is now named: it is the BIOS-thread budget
resume, found in the shipping debug channel.** `Service::open` already logs every activation's entry,
SP and GP via `lucent::debug("x4-thread", ...)`; turning the channel on with
`PSXPORT_DEBUG=x4-thread` shows the last four events before the fault:

    OpenTh handle=0xFF000001 entry=0x8001DAF8 sp=0x801FEC00 gp=0x00000000
    retail task entry 0x8001DAF8 ... was RESUMED at 0x800EA0F4 after 564486 cycle(s) in that turn.
      Denominator: 1561 of 13420 task turn(s) needed a budget resume, 881179244 guest cycles
    [native-dispatch:error] guest address 0x0113D7D0 resolves to zero or multiple active code images
    [executor:error] execution exited as fault at 0x0113D7D0 after 0 cycles

**The chain is task -> budget resume -> BIOS-range `0x800EA0F4` -> fault**, and the turn consumed **0
guest cycles**, the signature of a jump to a non-code address. `0x800EA0F4` is in the BIOS range and
is **not** an entry the port's BIOS table names. The port-owned seam is
`resumeAddress = result.guestPc` in `game/core/bios_threads.cpp`, whose only guard is
`result.guestPc == 0u` — a non-zero check, one predicate short of "is this a code address". **That
is a missing predicate, not a wrong computation, and it is deliberately NOT tightened yet**: doing so
would convert a diagnosable fault into a refusal without saying where the value came from. Separately,
**all five activations pass `gp=0x00000000`**, and the task's SP descends monotonically
(0x801FEC00 -> 0x801FEB58) without ever retiring. The value is still nowhere at rest: the probe was
re-pointed at the **task stack**, which no earlier scan covered, and found it at **0 of 43,520**
word-reads, so a stale return address off the task's own stack is refuted.

**MEASURED 2026-09-29 (issue 0036) — the model attached to that word was wrong twice, and this
paragraph is the surviving instance of the FIRST correction; the second is stated after it.** A
register dump at the fault boundary in a headless driven run reads
`entry 0x80012600 returnPc 0x800120EC guestPc 0x0113D7D0 detail='ambiguous code-image identity'`. The
faulting address **is the dispatched word**, so the guest computed that value and **called through
it**; the framework's refusal is its honest classification of a target outside every image. The write
census issue 0035 ran — every instruction that can write the word — was answering a question about a
store that is not happening.

**CORRECTED THE SAME DAY — the word was never FOUND in the class-0 table, and the sentence above
used to say it was.** An earlier draft of this paragraph read "is the word that was found in the
class-0 table", which is the claim the wide scan then refuted: `0x0113D7D0` is present at 0 of 97 spot
observations and 0 of 41,984 word-reads, `0x8011CB98` holds a stable `0x800DD7FC` at every one, and
0 of 294,912 static image words contain the value. The dispatch is real; **the table never held it**.
The old sentence also speculated that the slot "is written between the dispatch and the dump" — that
is now unnecessary, because the value is not in the table at any observed moment, so the frontier is
what *computes* it, not which slot carries it. The corrected reading is in issue 0036 and the probe
that settles it is `tools/probe_class0_table.py`.

What changed is a native owner of the guest's eight-entry VRAM rectangle upload queue
(`game/core/vram_rect_queue.{h,cpp}`), which replaces the guest's clearer, uploader and band
appender and supplies the array's real capacity at the **two** stores the guest leaves unbounded: the
record store, and the appender's post-loop terminator store — which lands on `item_objects[0].x_pos`
at the array's own designed occupancy of eight, and needs no ninth append at all. The attribution
that motivated it is measured, with denominators `PSXPORT_WWATCH` structurally cannot produce (its
`pc`/`ra` are the executor segment boundary): in one guest field the appender was entered **184**
times, **9** stored, all **9** from the single call site `0x80022058` for `g_Player`, and **16 of the
17 call sites never executed at all**. The ninth store is what sets `item_objects[0].active` from
`0x00` to `0x40`.

**S009 stays `missing` and this is not a partial credit for it.** No scene with more than 2 submitted
prims is still reached, and the run now ends one stage-load stage later on a CPU-bound guest loop
rather than on a fault. The honest gain is the fault and the extra distance, both measured; the
gameplay capability is unchanged and its blocker has moved, not gone. The next step is named in
issue 0035: the writer of `g_Player+0x47`, which the measurement brackets to the code between two
consecutive executions of the pass function `0x80021F34`, and which decides whether the nine-entry
count is the guest's own (issue 0035's (a)) or something the port paces.

So: the projection owner and the seven widened culling owners are implemented, their 4:3 identity is
pinned, `render_width=428` is the steady state on the wide leg, and the seven owners still have **no
product evidence** — not a negative result, an absent measurement. Their first product evidence
requires a post-movie frame with scene in it, which is issue 0028. The same shape holds for Tomba! 1,
whose only present also lands inside its STR movie.

<details>
<summary>The earlier 600-field reading, kept because it explains the shape of the gap</summary>

    [cfg]      PSXPORT_X4_WIDESCREEN enhancement active in product run
    [x4-wide]  guest projection 320x240 -> 428x240, OFX=214, draw width=428
    [wide]     native picture: aspect=0 wide_engine=0 native_width=320 render_width=428
    [gpu]      display depth -> 24-BIT (GP1(08)=08000011, 320x240)      <- the guest's own Set24BitDisp
    [wide]     native picture: aspect=0 wide_engine=0 native_width=320 render_width=320

At 600 fields it STAYED at 320, and the reading was that the documented carve-out never reverses
because the movie never completes. Both halves of that were horizon artifacts: the carve-out does
reverse, at field 13,000..13,500, and the completion transaction is reached twice. Recording the
superseded reading because the next reader will otherwise re-derive a 30..400-field horizon.

</details>


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

## The tracked `psxport_settings.ini` `aspect` key is INERT for this title — read this before trusting it

Measured 2026-09-27 by reading the title, not by inference: **nothing under `game/` or `titles/`
references the ini's `aspect` key at all.** This title's presentation aspect comes from exactly one
place, `game/core/widescreen_controller.cpp`:

```cpp
PresentationAspect WidescreenPolicy::presentationAspect(const Core &core) {
  ...
  return enh(cv_widescreen) ? PresentationAspect::Wide16x9 : PresentationAspect::Standard4x3;
}
```

and `cv_widescreen` is `PSXPORT_X4_WIDESCREEN`, declared in `game/core/enhancements.cpp` and
**defaulting to `true`**. So Mega Man X4's widescreen is on by default through its own CVar, and the
ini key can neither enable nor disable it.

**This matters because the value looks authoritative and is not.** `aspect=0` is `ASPECT_4_3` and
`aspect=3` is `ASPECT_AUTO`, and `ASPECT_AUTO` resolves to the SINK's aspect — the trap that made
Spyro 1's shipping build silently 4:3 while every measurement said 16:9. A reader who opens this ini,
sees `aspect=0`, and concludes "Mega Man X4 is not widescreen" would be wrong; a reader who changes it to
`1` or `3` would change nothing at all. Both values are inert here, and this file is left at the value
it was verified at rather than edited to look intentional.

The framework side is already correct and needs nothing: `classifyWide` takes BOTH the host `aspect`
and the title's own `guestAspect` from `GuestWidescreenProjection::presentationAspect` (see
`runtime/psx/picture_announce.h`), specifically so that a title which widens through its own projection
is not reported as "nobody asked". Mega Man X4's `[wide]` lines therefore reflect `PSXPORT_X4_WIDESCREEN`,
not the ini — the diagnostic reads the right source even though the ini beside it is inert.

The comparative pair in `tools/probe_post_movie_motion.py` sets the same knob explicitly for this
reason: `LEG_NARROW = ("0", "960x720")`, `LEG_WIDE = ("1", "1284x720")`, and `1284 / 960 = 4/3` exactly.

**STILL OUTSTANDING, and not claimed here:** that Mega Man X4's 16:9 leg renders a wider picture with
real scene content rather than a stretched or cropped one, measured on both legs of that pair. That
needs a product run, and the one product slot was held by the Spyro 1 level-dispatch investigation for
this session, so no leg was run and no widescreen claim is made for this title.
