# RE Frontier — the ordered RE dependency chain toward a faithful port

Tracked by `tools/re_frontier.py` (a shim onto `external/psxport/tools/port/re_frontier.py` — consult
it FIRST; update it in the SAME commit that changes a step). This is the fine-grained companion to
`docs/codemap.md`: the codemap says *what subsystem exists*, this says *which ordered RE step is real
reverse-engineering vs a hack that jumped ahead*.

**Hard rule (no hacks / no fallbacks):** a `⛔ hack` status is DEBT, never an acceptable resting
state. It marks a shortcut standing in for absent RE and MUST be removed as its real mechanism lands.
`re_frontier.py hacks` is the debt list; `re_frontier.py next` tells you the next RE-ready step.

**`re-verified` MEANS FAITHFUL to the real target — not "the mechanism runs."** A step is
`re-verified` only when its OUTPUT matches the real game/binary on real data. An internal trace is a
mechanism check, NOT faithfulness.

**Fail fast & loud:** a failure must surface loudly, never silently fall back — unless the fallback IS
intended behaviour of the real target being reproduced.

Statuses: ✅ re-verified · 🟡 re-partial (honest gap) · 🔬 in-progress · ⛔ hack (debt, must remove) ·
⬜ todo · ➖ skip-by-design · ⏸ blocked (computed).

## THE STATE OF THIS PORT: verified binary/native facts awaiting dynamic execution

RE-01 owns the measured and wired crt0 group. RE-06 owns the two measured InitPAD buffers. The
recorded pre-migration execution reached a resident bootstrap with 6,193 discovered binary roots,
7,534 functions, InitHeap, and `gameMain`; HookEntryInt continuation `0x800E5194` was reached live.
Those facts bound RE-02. RE-11 owns a finite boot prefix, one-step
title frame driver, retail-derived VBlank producer, and full-entry VSync trap. Recorded framework pin 124b85c8
uses a neutral presenter, creates no temporal product, and separates temporal-only helper translation
units. Direct `GameRuntime` inheritance removes the concrete Fps60 implementation; full Clang CTest
11/11 includes strict source and shipping-binary dependency gates. RE-04 owns the separate CD
interrupt boundary: the VBlank-only SysEnq element correctly declines IRQ2, the shared BIOS restores
HookEntryInt, and retail trapIntr dispatches libcd's slot-2 callback. Live PID 2710117 proves the
corrected stream path publishes per-channel table `0x8011DC5C`, writes callback `0x800E8188` to DMA3
slot `0x8011DC68`, fills the seven-chunk frame, arms the final DMA3 transfer, and dispatches that
callback at field 15. Narrow ring-watch PID 2717335 proves the resulting frame is consumed correctly:
slot zero changes 3 -> 2 -> 4, then `StFreeRing` clears all seven chunk headers to zero. The title
frame driver now keeps that blocking movie transaction suspended at `UpdateTasks` across host fields
and does not restart the gameplay draw/clear prefix until the stream releases. Real-disc PID 3087406
completed 90/90 fields without guest VSync; presents 30/60/90 are coherent, and the frame-30 dump has
live pixels across columns 0..479 in both 24-bit buffers. That directly falsifies the former
right-third image: the missing area was the gameplay clear erasing the first 320 words of the active
movie buffer, not missing MDEC slices or DMA callbacks. `X4Runtime` supplies the retail BIOS
OpenTh/CloseTh/ChangeTh contract and the untouched scheduler transfers into task entry 0x8001D064. The
recorded field-aware CD time crosses `0x800128B8`, logo decode, task `0x8001DAF8`, and a coherent title
screen. The former capture overflow is resolved as a missing
frame commit, not a malformed OT or CD failure.

**The one thing that IS measured is the SUPPLY, not the port** — see `docs/references.md`. An AGPL-3.0
matching decompilation (`external/mmx4`) declares a byte-exact build target whose SHA-1 equals the SHA-1
of the image this repo extracts, so its symbol addresses are OUR addresses with no translation. That
changes where RE labour comes from; **it does not fill a single field**, because a borrowed address is a
REFERENCE until this repo measures it against this executable. Its own matched-code figure (18.5% upper
bound, on the `objdiff` object-identity axis) is a fact about the supply and must never be quoted as this
port's progress — this port's axis is SBS byte-exact RAM parity, and neither implies the other.

**THE CURRENT OWNERSHIP FRONTIER IS `RE-10`'S FIRST SELECTED BODY.** The title state-0 white-logo quad
initializer at `0x800D6F94` is measured, imported readably, retained-super wired, and hermetically
gated. An exact-pin serialized real-disc run proves live reach and equality, but its sampled presents
were a stable dark title field and therefore do not prove visible composition. It remains
`in-progress` until a deliberate native perturbation proves the live gate can report the other
answer. RE-07/08/09 remain
the three enhancement fronts. The native-producer / interpolation / native-depth apparatus stays
`➖ skip-by-design`; this title-object ownership does not create or imply any of it.

RE-08 now also owns the first exact title-layout prerequisite without taking more native ownership:
retail mode 0 publishes a 320x240 edge quad through title-only variant `0x0A`, while mode 12 publishes
nine measured menu/logo positions through a separate title-only table. The runtime is unchanged; this
narrows issue #19's future widescreen correction to the real coordinate sources.

## Execution migration gate

The product execution owner is native psxport code plus a pinned Lightrec integration. The
authenticated `SLUS_005.61` image is loaded as runtime data; Lightrec executes every guest body not
selected by the image-and-address-keyed native override table. An override's original call returns
to that address through the dynarec while suppressing only the current override. The gameplay binary
has no selectable interpreter engine. Lightrec may automatically interpret only bounded blocks the
JIT refuses; the shipping run must report those blocks by reason and instruction count and enforce a
release threshold. Forced interpretation and interpreter-oracle execution remain test-only.

The first implementation discriminator is the existing 4,000-field front-end/movie frontier with
nonzero Lightrec execution and movie VSync intercepted at the authenticated runtime address. Movie
bodies remain original guest code; they are not rewritten to manufacture suspension or progress.
The shipping dispatcher must also prove a native override and its scoped original call, relevant
invalidation, bounded exits, and timing/interrupt/device synchronization with a positive and
controlled negative. This checkpoint is followed by representative interactive gameplay with
correct input, audio, rendering, timing, and declared host-architecture performance. The retired
offline source-generation path has already been removed under the break-first migration rule and is
not evidence for this gate.

## boot

### RE-01 — crt0 / boot layout: the GameConfig boot group for SLUS_005.61
- status: re-verified
- deps:
- evidence: Claim C005 retains the retail SLUS_005.61 derivation (SHA-1 213733031136d095ca275d6957695aa25011cfa5). The group is bss [0x8012F418,0x80175F38), stackTopBase 0x800DAF3C with bias 0, stackTopBase2 0x8011CB74, heapBase 0x80175F38, gp 0x8012F418, libcInit 0x800EDCDC, gameMain 0x80012024, crt0 0x800DAE8C. heapSizePtr/heapBasePtr are measured absent: the function has one absolute store and it saves ra. Current conformance must be demonstrated at the native/Lightrec boot boundary.
- where: game/core/game_config.cpp (bssZeroLo/Hi, stackTopBase/2, heapBase, heapSizePtr, heapBasePtr, gp, libcInit, gameMain, crt0)
- gap: The group is runtime-confirmed through InitHeap and guest-main dispatch. CD initialization now advances through its measured IRQ2 callback path; remaining loader work is RE-04, not an RE-01 field.
- notes: psxport 726d10c9 made the boot mechanism generic; issue #5 preserves the root cause. The cross-control re-derives all 12 independently recorded Tomba!2 values.

### RE-02 — authenticated native/Lightrec execution for SLUS_005.61
- status: re-partial
- deps: RE-01
- evidence: Retail SLUS_005.61 has SHA-1 `213733031136d095ca275d6957695aa25011cfa5`, resident range `[0x80010000,0x80130000)`, crt0 `0x800DAE8C`, gameMain `0x80012024`, and no code overlays. A recorded pre-migration measurement found 6,193 binary roots and 7,534 functions, including live HookEntryInt continuation `0x800E5194`; FNTRACE reached it through shared BIOS delivery and then CD callback `0x800E7944`. `tools/verify_cd_irq.py` independently proves from retail bytes that setjmp saves this mid-function continuation. These are retained binary/runtime facts.
- where: target shared psxport per-Core Lightrec executor and authenticated `GuestProgramImage`; target title image-and-address-keyed override/original-call registry; retained identity and control-flow verifiers under `tools/`
- gap: The native/Lightrec product has not executed a guest block from the real title input. Exercise
  the wired executor and authenticated image through the 4,000-field front-end/movie discriminator
  above. The low BIOS/ROM address `0x8000E884` observed during pad setup remains to classify before
  that path is called fully owned.
- notes: `0x800E5194` is not guessed: live HookEntryInt recorded it in jmp_buf `0x8011CBCC`, and retail startIntr proves it is the non-zero setjmp continuation into trapIntr. Dynamic execution discovers runtime targets directly; no seed list is part of the target product.

## overlays

### RE-03 — overlay / module load bases
- status: skip-by-design
- deps:
- evidence: MEASURED 2026-08-12, three independent signals over the whole disc with a control, plus corroboration from a source that could have said otherwise. All 163 disc files enumerated (138 ARC + 11 STR + 11 XA + SLUS_005.61 + SYSTEM.CNF + ZNULL.DAT, 515,298,768 B); all 138 .ARC read IN FULL (25.2 MiB) and **0 of 138 contain even one `jr $ra` at any byte alignment**; the calibrated code-window filter (external/psxport/tools/exe_similarity.py, recalibrated + selftested 2026-08-12) reads median 2.5% / mean 3.5% / max 60.1% on ARCs against 99.4% of 16,367 windows in the 64 KiB at the header-declared entry; ≤9.1% of j/jal targets land inside .text in any ARC against 85.0% of 20,428 in the boot exe. mmx4's splat config declares exactly ONE code segment (`main`, vram 0x80010000) and NOT ONE overlay. Reproduce: `python3 tools/code_scan.py --census <arcdir> --glob '*.ARC' --ctrl-exe <exe>`.
- where: retained disc census evidence above; runtime image policy admits only authenticated
  SLUS_005.61 resident text unless a title loader explicitly activates another image identity
- gap: BLIND SPOT, stated because the method cannot see past it: three signals detect PLAIN R3000A code, so this asserts "no plain code on the disc outside SLUS_005.61", NOT "no code". Packed or compressed code inside an .ARC would read as a texture and be indistinguishable from one. Two things make that implausible rather than merely unmeasured, and neither is proof: the decomp would have needed overlay segments to match 18.5% of the binary, and a packed-overlay loader would still need a decompressor plus a fixed load base in the boot exe — and there is no j/jal cluster at any base above .text end (the 3,073 out-of-.text targets scatter over 386 different 64K pages including impossible addresses, i.e. they are misdecoded data words). Also invisible: code fragments under 64 bytes, and anything inside the ~430 MB of .STR/.XA that was classified by container format and the boot exe's own path table rather than scanned whole. One file lied on a single signal — MOJIPAT.ARC reads 60.1% code-plausible glyph bitmaps with 0 epilogues — which is why one signal was never enough.
- notes: skip-by-design, NOT todo: the answer was measured and it is "there are none". If a decompressor and a fixed load base ever turn up in the boot exe, that is the finding that reopens this step, and it should be reopened rather than argued with.

## cd

### RE-04 — CD load chokepoints and the loader's contract
- status: re-partial
- deps: RE-01
- evidence: Retail SLUS_005.61 (SHA-1 213733031136d095ca275d6957695aa25011cfa5): tools/verify_cd_irq.py checks six interrupt/result-state groups. tools/verify_threads.py independently derives all three B0 service thunks, the 128-byte task records at 0x801F8100, current-task pointer 0x801F8300, entry/SP/GP/handle fields, three task->main yield helpers, shipping runtime constants, and the exact HLE window; its positive plus five mutations pass 6/6. mmx4_runtime_test proves three distinct non-main handles, task SP/GP and register persistence across yield/resume, intact main registers, capacity refusal, invalid-handle refusal, deferred self-close while the task fiber is live, and TCB reuse only after returning to the main stack. scratch/logs/re04-bios-thread-runtime-final-ad5cf802.log is the clean-pin real-disc positive: untouched func_80012740 creates entry 0x8001D064, X4Runtime OpenTh returns 0xFF000001, untouched func_80012600 selects it, and FNTRACE reaches 0x8001D064 once with zero ABI violations before 418 scheduler calls in the bounded run. No synchronous-success override, direct entry dispatch, or polling bypass exists.
- where: game/core/bios_threads.{h,cpp}; game/core/x4_context.{h,cpp}; game/core/x4_runtime.cpp; tools/verify_cd_irq.py; tools/verify_threads.py; scratch/logs/re04-bios-thread-runtime-final-ad5cf802.log (untracked runtime evidence)
- gap: The IRQ/callback/result-state and retail scheduler->BIOS-thread transfer are complete. Issue #13 identifies the older cause exactly: request `0x40` is LBA 222 / `0x18800`, but the former shared CDC applied physical 2x deadlines to sparse `guestInstructionTicks` while the loader yielded each field. Retail `func_80014C70` consequently exhausted its 601-iteration wait, wrote `D_801406AC=0xC0`, and rearmed. Recorded pin 9c2e3f1c plus the title-owned synchronous operation completes real-disc requests 64, 65, 113, and 51 without FNTRACE. Exact destination-byte comparison across the current synchronous route remains before this step can become re-verified. A fresh true-oracle state capture is unavailable because no true-oracle executable is installed.
- notes: This separates enhancement job A from job B. Raw CD IRQ delivery is faithful and shared; do not replace it with synchronous CdInit success or a title-local fast-CD override. The title service implements the BIOS execution contract underneath the retail scheduler; it does not replace func_80012600 or direct-call a task entry. Historical FNTRACE runs that covered the three HLE thunk addresses displaced PlatformHle's handler, so only the unshadowed observations are retained. Issue #10 records the separate frame-fence cause and fix; issue #12 records why that non-temporal fence must leave Fps60.

## frame

### RE-05 — per-frame OT / packet-pool layout
- status: skip-by-design
- deps:
- evidence: USER decision, 2026-08-12, verbatim: "Mega Man doesn't need native producers or lerp or native depth, it's already 60fps." Quoted in full in CLAUDE.md and recorded as a claim in docs/info/claims/ so a later session cannot 'discover' this as a missing subsystem and start building it.
- where: game/core/game_config.cpp (otRegionBase/Stride, packetPoolBase/Stride, otBasePtr, poolPtrCur/Last, clearOtagR, putDrawEnv, drawSync) — zero, with no reader
- gap: The host now owns loop repetition through `X4FrameDriver`, but that driver still calls the retail GTE/OT leaves and needs none of the framework's native-producer packet-pool configuration. `GameHooks::frameUpdate` and `drawOTag` remain fail-fast because they are a different native-renderer path. This skip is about picture production, not frame-loop ownership.
- notes: If native picture production is ever authorized, this is where that separate work starts.

### RE-06 — pad driver buffers
- status: re-verified
- deps: RE-01
- evidence: Retail SLUS_005.61 (SHA-1 213733031136d095ca275d6957695aa25011cfa5): a whole-text scan of 294,400 loaded words finds exactly one jal to the matching-decomp-identified InitPAD target 0x800EE0D0, at 0x80012194; immediate dataflow gives (a0,a1,a2,a3)=(0x80166D68,0x22,0x8012F46C,0x22). tools/verify_pad.py --check compares all four arguments to the typed GuestPadBufferLayout, its direct-runtime publication, and the legacy compatibility bindings; --selftest proves both answers, 4/4.
- where: game/core/pad_layout.h (single typed fact authority); game/core/x4_runtime.cpp and game/core/game_config.cpp (direct and compatibility consumers); tools/verify_pad.py
- gap: The two fixed buffers are complete and execution now passes CD initialization. Runtime input injection remains a separate gate because the observed boot path has not yet consumed a host-injected pad state.
- notes: padDriverFn/padSlotPtrTable/padSlotPtrStride remain zero deliberately: the retail InitPAD call passes the two buffers directly. Native frame service now reaches the same typed layout without dereferencing a null legacy config. This lands drop-in co-op input plumbing only; RE-07 still has no player-object, camera, routing or spawn implementation.

## enhancements

### RE-07 — THE PLAYER-OBJECT SYSTEM: one player struct, camera ownership, input routing, spawn path
- status: re-partial
- deps: RE-01, RE-02
- evidence: MEASURED 2026-08-24 against BOTH sources (AGPL mmx4 decomp + our own binary: instruction scans of the extracted SLUS_005.61 and Ghidra decompiles of resident RAM, scratch/decomp/x4_*.c). Player struct `g_Player = 0x801418C8`, PlayerObj 0xE4 (123-xref scan floor), with measured offsets active/+0, id/+1, character/+2 (X=0 table 0x80119DF0 vs Zero 0x8011AFF0), on_screen/+3, state/+4, x/y s16.16 with integer halves at +0xA/+0xE, bg_slot/+0x14, anim_table/+0x30, cur_anim/+0x47, hp/+0x5C; a second PlayerObj `g_Entity = 0x80175D58`. Camera = 3 layer structs @ 0x801419B0 stride 0x54; scroll x/y at +0xA/+0xE; mode-dispatched follow via table 0x800F3134 driven by func_80027850 reading the player's +0xA/+0xE halves with dead-zones (+0x30/+0x32), capped steps (+0x47..49), bound clamps (+0x1C..+0x22) that push the player back. Input route measured end-to-end: libpad buffers 0x80166D68 / 0x8012F46C → router func_80012328 (validity byte 0xFF/'A', ~buttons with opposite-direction cancellation) → P1 held/prev/edge 0x80166C08/C0A/C0C (edge == mmx4's controller_state) AND P2 trio 0x80166D50/D52/D54 decoded every frame but consumed by NOTHING outside the router. Spawn path: func_80035240 sets active=1 from engine character byte 0x80172203 and seeds from stage scratch; init_objects func_80023DB8 resets all pools with measured strides (main 48×0x9C @0x8013BED0..DC10); update_main_objects func_80021234 dispatches table 0x800F24A4 by id. Full per-item evidence, denominators and blind spots: docs/re-player-object.md. Typed read-only lens shipped game-side (`game/core/player_object.h`), pinned hermetically by ctest `x4_player_object` (positive planted-state reads plus non-aliasing negatives).
- where: docs/re-player-object.md; game/core/player_object.h; tests/test_x4_player_object.cpp; scratch/decomp/x4_*.c
- gap: The four pillars are located and named, but this is a MAP, not ownership — no native body exists and no guest write ships. Remaining UNKNOWNs are listed in docs/re-player-object.md §1–§4: most PlayerObj bytes beyond the measured ones, which UI state writes the character byte (writers seen at 0x8001C224/0x8001C310/0x80021E54 unattributed to screens), the stage-load caller of init_objects, checkpoint/respawn writer, parallax math in FUN_80028690, per-stage camera-bound population. Co-op remains force-suppressed in typed comparison roles and its evidence question is still OPEN. Drop-in co-op is a pc_enh with `affect: full` — it changes canon guest state.
- notes: The most invasive pc_enh in the workspace. Expect single-player assumptions everywhere: one player struct, one camera, one input route. The retail P2 button decode is the co-op seam candidate, not co-op itself.

### RE-08 — the projection / FOV setup site widescreen must drive from game state
- status: re-partial
- deps: RE-01, RE-02
- evidence: Retail SLUS_005.61 SHA-1 213733031136d095ca275d6957695aa25011cfa5: tools/verify_projection.py --check scans all 294,400 loaded words and finds exactly six CTC2 writes to CR24/25/26, all inside InitGeom/SetGeomOffset/SetGeomScreen; exactly one call to each, all in func_8001213C, with OFX=160, OFY=120, H=512. Its 4/4 selftest rejects a changed OFX, removed call, and extra raw writer. The title wraps the untouched SetGeomOffset `0x800E90C8` and SetDefDrawEnv `0x800E9354` bodies through image-scoped native overrides and scoped calls to the original guest bodies. `mmx4_runtime_test` drives those production transformations with an injected framework plan and proves exact 4:3 identity, 16:9 OFX/width 214/428, and unchanged OFY/H/x/y/h/UV/color/order; Clang links the native/Lightrec product. Real-disc startup A/B reaches that retail wrapper and logs 320x240 -> 428x240, OFX 214, draw width 428 with the knob on (`scratch/logs/re08-typed-wide-boot.log`) and exact 320/160 identity off (`re08-typed-4x3-boot.log`). Against the separate shared-time candidate, normally paced PRESENT captures at frames 800/1000 prove a coherent 4:3 title-screen control. `tools/verify_title_composition.py --check --selftest` now follows title mode 0 to quad ID 0x0B variant 0x0A and its exact 320x240 edge row, plus mode 12 to nine exact title-only logo/menu x/y records; its 10/10 positive/negative matrix rejects mutations in either coordinate chain. Wide pixels are not yet verified.
- notes: Do not attach a local present stretch or force native. X4 owns guest CR24 and RECT.w only; the typed framework plan owns host clip, renderer margin coverage, and presentation sampling. `RenderMode::enhancementsAllowed()` remains Native-only, so no interpolation/native-depth/internal-resolution apparatus enters the Gte title path. Both typed comparison roles resolve exact 4:3.
- gap: The framework is recorded at 9c2e3f1c; direct runtime inheritance removes the concrete Fps60 link and that pin includes the temporal-only helper split from neutral services. The full-screen edge quad and nine logo/menu positions now have exact title-owned source seams, but their widescreen policies are not implemented or visually proven. Capture matched title/gameplay fields with widescreen off/on and verify newly composed margins, unchanged central scale, and 4:3 identity; continue classifying title primitives before changing coordinates.
- where: tools/verify_projection.py; tools/verify_title_composition.py; tools/verify_no_temporal_dependency.py; game/core/widescreen_controller.{h,cpp}; game/core/native_overrides.cpp; game/core/x4_runtime.{h,cpp}; tests/test_x4_runtime.cpp

### RE-09 — the game's OWN scripted wait states, fade ramps and frame-count timers
- status: re-partial
- deps: RE-01, RE-02
- evidence: JOB A's stock-path timing fault remains resolved by recorded framework pin 9c2e3f1c (issue #13). JOB B implements synchronous direct/archive owners and retains its measured callbacks, request table, ring drain, terminal-state checks, and loading-presentation omission. Native owners now replace the complete direct/archive CD setup bodies and the set_alarm counter query without dispatching guest VSync. Focused production-leaf tests pass, and full-trap real-disc runs complete request 64 (49 sectors) and request 65 (6 sectors) before reaching the separate XA startup frontier.
- where: game/core/fast_wait.{h,cpp}; game/core/native_overrides.cpp; game/core/x4_context.h; tests/test_x4_runtime.cpp; docs/behavior-map.md (fastwait row)
- gap: Re-run destination-byte and presentation-absence comparisons on the current full-trap build after XA startup advances far enough to exercise later requests. The game's OTHER scripted waits/fades remain separately unclassified.
- notes: Depends on RE-04 in practice — you cannot say what is a wait state until you know where the loads are.

## ownership

### RE-10 — native ownership seeded from the AGPL matching decomp
- status: in-progress
- deps: RE-01, RE-02
- evidence: Retail SLUS_005.61 (SHA-1 213733031136d095ca275d6957695aa25011cfa5): tools/re_title_quad.py reuses the complete title-composition path through title quad update 0x800D76F8, proves state-0 dispatch 0x8010FDD0 -> 0x800D6F94, matches all 49 instructions in the selected leaf, diffs 17 shipped facts, and checks image-scoped native registration. game/core/title_quad.cpp is the readable AGPL-derived native body; x4_title_quad hermetically pins 23 output/register checks.
- where: game/core/title_quad.{h,cpp}; tools/re_title_quad.py; tests/test_x4_title_quad.cpp; game/core/x4_runtime.cpp
- gap: Binary/hermetic ownership is complete. Runtime Lightrec-versus-native comparison must prove override reach, scoped-original equality, and a controlled native mismatch through the shipping dispatcher.
- notes: This imports one title-object initializer only. It does not change pixels, fix issue #19, or create native producers/interpolation/depth. The source stays AGPL inside this repo; nothing moved into psxport.

## platform synchronization

### RE-11 — platform-HLE synchronization entry points and executable windows
- status: re-partial
- deps: RE-01
- evidence: `tools/verify_vsync.py` derives the retail VSync/helper/counter/IRQ chain and proves the native field owner dispatches the current class-0 handler, pad and SPU advance once, and presentation commits once. Binary/Ghidra evidence grounds the BGM Setmode edge and the three measured movie-cleanup fences. `music_stream.*`, `cd_control_boundary.*`, and `movie_cleanup.*` preserve their measured call/stack/state contracts without guest VSync. The authenticated libetc VSync address is now an image-scoped native override: measured movie callers request a typed `FrameBoundary`, and the BIOS-thread host explicitly resumes from its reported guest PC. Focused phase/resume/CD-state contracts remain the retained evidence; the deleted static dispatcher is not an oracle.
- where: game/core/cd_control_boundary.{h,cpp}; game/core/cd_controller.{h,cpp}; game/core/movie_cleanup.{h,cpp}; game/core/x4_frame_driver.{h,cpp}; game/core/music_stream.{h,cpp}; game/core/vsync_sync.{h,cpp}; game/core/game_config.cpp; tests/test_x4_cd_control_boundary.cpp; tests/test_x4_movie_cleanup.cpp; tests/test_x4_movie_cleanup_shipping.cpp; tests/test_x4_frame_driver.cpp; tests/test_x4_music_stream.cpp; tools/verify_vsync.py
- gap: PID 4013759 proves the complete seven-field cleanup in product with no guest VSync. Retail table/disc evidence grounds `OP_U.STR` release at authored frame 1346 (final chunks LBA 27613..27622), and PID 4031142 crosses it, runs cleanup again, completes archive requests 113/51, and reaches BGM state 7 at field 2834. Its retained `CdSync(1)` then aborts through guest VSync at return `0x80016E9C`; that status check now uses `cd_sync_stock_sync`. A later diagnostic crossed it and exposed BGM `CdlSetmode(0x0E, 0xC8, 0x80139554)` at return `0x80016EC4`, whose generic policy reached retained `CdSync -> VSync(-1)`. The title now owns only that authenticated Setmode edge through `cd_controller::setMode`, preserving the authored three-field fence and every unrelated caller. Linked shipping positives and controlled negatives prove both ownership answers; full Clang build/tidy and 25/25 CTests pass. Exact-PID run 4086465 exits normally at 4000 fields without guest VSync but reaches only cleanup field 2052 and OP_U LBA 14265, so it never exercises state 7 and is not BGM proof. The native/Lightrec discriminator must ground that field-progression difference, reach state 6/5/1 and first `CdlReadS`, and verify later `CdlGetlocP`/Sub-Q absolute BCD MSF with presented-picture/audio evidence. Later memory-card callers remain separately open under issue #25.
- notes: Native frame-loop ownership is independent of native rendering or temporal interpolation. X4 remains guest-GTE, widescreen-only.
