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

## THE STATE OF THIS PORT: two verified RE facts plus a booting resident substrate

RE-01 owns the measured and wired crt0 group. RE-06 owns the two measured InitPAD buffers. RE-02 now
owns a measured resident bootstrap: 6,193 binary roots → 7,534 functions, real generated registry,
resident range, and runtime dispatch through InitHeap into `gameMain`. Its one explicit seed is the
retail/live-proven HookEntryInt continuation at 0x800E5194. RE-11 owns a retail-derived VBlank producer
at libetc's exact counter-wait helper and its one-field frame commit. Recorded framework pin 9c2e3f1c
uses a neutral presenter, creates no temporal product, and separates temporal-only helper translation
units. Direct `GameRuntime` inheritance removes the concrete Fps60 implementation; full Clang CTest
11/11 includes strict source and shipping-binary dependency gates. RE-04 owns the separate CD
interrupt boundary: the VBlank-only SysEnq element correctly declines IRQ2, the shared BIOS restores
HookEntryInt, and retail trapIntr dispatches libcd's slot-2 callback. The current RE-04 gap is earlier
than the archive loader on the recorded pin: `X4Runtime` supplies the retail BIOS
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

**THE FRONTIER'S NEXT REAL TARGET IS `RE-07`, THE PLAYER-OBJECT SYSTEM** — not the renderer. This is an
enhancement port (USER decision, `CLAUDE.md`), so the whole native-producer / interpolation /
native-depth apparatus is `➖ skip-by-design` below and the deliverables are three `pc_enh` guest-state
changes. RE-01/RE-02 are the mechanical prerequisites that give RE-07 something to work on; nothing
downstream of RE-07 should be attempted before it.

## boot

### RE-01 — crt0 / boot layout: the GameConfig boot group for SLUS_005.61
- status: re-verified
- deps:
- evidence: Retail SLUS_005.61 (SHA-1 213733031136d095ca275d6957695aa25011cfa5): `tools/verify_crt0.py --check` symbolically executes the 43-instruction entry function, compares the shipping group and resident range, and locates 15/15 required mechanisms in psxport; `--selftest` is 26/26 and the Tomba!2 cross-control is 29/29. The group is bss [0x8012F418,0x80175F38), stackTopBase 0x800DAF3C with bias 0, stackTopBase2 0x8011CB74, heapBase 0x80175F38, gp 0x8012F418, libcInit 0x800EDCDC, gameMain 0x80012024, crt0 0x800DAE8C. heapSizePtr/heapBasePtr are measured absent: the function has one absolute store and it saves ra.
- where: game/core/game_config.cpp (bssZeroLo/Hi, stackTopBase/2, heapBase, heapSizePtr, heapBasePtr, gp, libcInit, gameMain, crt0)
- gap: The group is runtime-confirmed through InitHeap and guest-main dispatch. CD initialization now advances through its measured IRQ2 callback path; remaining loader work is RE-04, not an RE-01 field.
- notes: psxport 726d10c9 made the boot mechanism generic; issue #5 and falsified claim C006 preserve the root cause. The cross-control re-derives all 12 independently recorded Tomba!2 values.

### RE-02 — recompiler seed set for SLUS_005.61
- status: re-partial
- deps: RE-01
- evidence: Retail SLUS_005.61 (SHA-1 213733031136d095ca275d6957695aa25011cfa5) through psxport's real emit.py: 6,193 binary-rooted seeds -> 7,534 recompiled functions, including crt0 0x800DAE8C, gameMain 0x80012024, and the measured HookEntryInt continuation 0x800E5194; one computed jr ra of 5,534 sites; zero overlays; version 2026-08-12.1. tools/verify_recomp_bootstrap.py --selftest remains 2/2. tools/verify_cd_irq.py proves from retail bytes that setjmp saves the mid-function continuation and checks it exists exactly once in main_reentry and is not duplicated in main; the shared emitter includes main_reentry in its seed union. Clang links the generated registry. Live FNTRACE reaches 0x800E5194 through shared BIOS delivery and then CD callback 0x800E7944.
- where: game/recomp_seeds.json; tools/ensure_recomp.py; tools/verify_recomp_bootstrap.py; tools/verify_cd_irq.py; game/core/recomp_register.cpp; game/core/game_config.cpp (recMainLo/Hi)
- gap: Runtime-computed targets on paths beyond the now-cleared CD initialization boundary remain unobserved. Grow the explicit list only from a runtime miss plus retail control-flow evidence. The low BIOS/ROM address 0x8000E884 is still reported during pad setup but does not stop current execution; classify it before claiming that path fully owned.
- notes: 0x800E5194 is not a guessed miss: live HookEntryInt recorded it in jmp_buf 0x8011CBCC and retail startIntr proves it is the non-zero setjmp continuation into trapIntr. It belongs in main_reentry only; putting it in main too would duplicate the same fact. The earlier 0x800EDCDC apparent miss was a separate zero-resident-range router defect and remains documented in issue 8.

## overlays

### RE-03 — overlay / module load bases
- status: skip-by-design
- deps:
- evidence: MEASURED 2026-08-12, three independent signals over the whole disc with a control, plus corroboration from a source that could have said otherwise. All 163 disc files enumerated (138 ARC + 11 STR + 11 XA + SLUS_005.61 + SYSTEM.CNF + ZNULL.DAT, 515,298,768 B); all 138 .ARC read IN FULL (25.2 MiB) and **0 of 138 contain even one `jr $ra` at any byte alignment**; the calibrated code-window filter (external/psxport/tools/exe_similarity.py, recalibrated + selftested 2026-08-12) reads median 2.5% / mean 3.5% / max 60.1% on ARCs against 99.4% of 16,367 windows in the 64 KiB at the header-declared entry; ≤9.1% of j/jal targets land inside .text in any ARC against 85.0% of 20,428 in the boot exe. mmx4's splat config declares exactly ONE code segment (`main`, vram 0x80010000) and NOT ONE overlay. Reproduce: `python3 tools/code_scan.py --census <arcdir> --glob '*.ARC' --ctrl-exe <exe>`.
- where: game/recomp_seeds.json (overlay_bases / overlay_base_patterns — expected to stay EMPTY)
- gap: BLIND SPOT, stated because the method cannot see past it: three signals detect PLAIN R3000A code, so this asserts "no plain code on the disc outside SLUS_005.61", NOT "no code". Packed or compressed code inside an .ARC would read as a texture and be indistinguishable from one. Two things make that implausible rather than merely unmeasured, and neither is proof: the decomp would have needed overlay segments to match 18.5% of the binary, and a packed-overlay loader would still need a decompressor plus a fixed load base in the boot exe — and there is no j/jal cluster at any base above .text end (the 3,073 out-of-.text targets scatter over 386 different 64K pages including impossible addresses, i.e. they are misdecoded data words). Also invisible: code fragments under 64 bytes, and anything inside the ~430 MB of .STR/.XA that was classified by container format and the boot exe's own path table rather than scanned whole. One file lied on a single signal — MOJIPAT.ARC reads 60.1% code-plausible glyph bitmaps with 0 epilogues — which is why one signal was never enough.
- notes: skip-by-design, NOT todo: the answer was measured and it is "there are none". If a decompressor and a fixed load base ever turn up in the boot exe, that is the finding that reopens this step, and it should be reopened rather than argued with.

## cd

### RE-04 — CD load chokepoints and the loader's contract
- status: re-partial
- deps: RE-01
- evidence: Retail SLUS_005.61 (SHA-1 213733031136d095ca275d6957695aa25011cfa5): tools/verify_cd_irq.py checks six interrupt/result-state groups. tools/verify_threads.py independently derives all three B0 service thunks, the 128-byte task records at 0x801F8100, current-task pointer 0x801F8300, entry/SP/GP/handle fields, three task->main yield helpers, shipping runtime constants, and the exact HLE window; its positive plus five mutations pass 6/6. mmx4_runtime_test proves three distinct non-main handles, task SP/GP and register persistence across yield/resume, intact main registers, capacity refusal, invalid-handle refusal, deferred self-close while the task fiber is live, and TCB reuse only after returning to the main stack. scratch/logs/re04-bios-thread-runtime-final-ad5cf802.log is the clean-pin real-disc positive: untouched func_80012740 creates entry 0x8001D064, X4Runtime OpenTh returns 0xFF000001, untouched func_80012600 selects it, and FNTRACE reaches 0x8001D064 once with zero ABI violations before 418 scheduler calls in the bounded run. No synchronous-success override, direct entry dispatch, or polling bypass exists.
- where: game/core/bios_threads.{h,cpp}; game/core/x4_context.{h,cpp}; game/core/x4_runtime.cpp; tools/verify_cd_irq.py; tools/verify_threads.py; scratch/logs/re04-bios-thread-runtime-final-ad5cf802.log (untracked runtime evidence)
- gap: The IRQ/callback/result-state and retail scheduler->BIOS-thread transfer are complete. Issue #13 identifies the older cause exactly: request `0x40` is LBA 222 / `0x18800`, but the former shared CDC applied physical 2x deadlines to sparse `guestInstructionTicks` while the loader yielded each field. Retail `func_80014C70` consequently exhausted its 601-iteration wait, wrote `D_801406AC=0xC0`, and rearmed. Recorded pin 9c2e3f1c plus the title-owned synchronous operation completes real-disc requests 64, 65, 113, and 51 without FNTRACE. Exact destination-byte comparison across the current synchronous route remains before this step can become re-verified. A fresh true-oracle state capture is unavailable because no true-oracle executable is installed.
- notes: This separates enhancement job A from job B. Raw CD IRQ delivery is faithful and shared; do not replace it with synchronous CdInit success or a title-local fast-CD override. The title service implements the BIOS execution contract underneath the retail scheduler; it does not replace func_80012600 or direct-call a task entry. FNTRACE must not include the three HLE thunk addresses in this gate because its raw generated-wrapper probe displaces PlatformHle's handler; issue #11 and instrument I011 record that negative control. Issue #10 records the separate frame-fence cause and fix; issue #12 records why that non-temporal fence must leave Fps60.

## frame

### RE-05 — per-frame OT / packet-pool layout
- status: skip-by-design
- deps:
- evidence: USER decision, 2026-08-12, verbatim: "Mega Man doesn't need native producers or lerp or native depth, it's already 60fps." Quoted in full in CLAUDE.md and recorded as a claim in docs/info/claims/ so a later session cannot 'discover' this as a missing subsystem and start building it.
- where: game/core/game_config.cpp (otRegionBase/Stride, packetPoolBase/Stride, otBasePtr, poolPtrCur/Last, clearOtagR, putDrawEnv, drawSync) — zero, with no reader
- gap: This group only has a reader if the port stands up the framework's NATIVE frame loop, and this port does not: there is no interpolation to serve and no native producer to drive, so the guest's own loop runs on the substrate and owns its OT. GameHooks::frameUpdate and drawOTag are fail-fast permanently. This is a SCOPE decision, not a measurement — it is falsified only by the USER changing it, or by a measurement showing X4 does NOT run at 60fps in the modes we care about, which has NOT been measured in this repo.
- notes: If the decision is ever reversed, this is where that work starts.

### RE-06 — pad driver buffers
- status: re-verified
- deps: RE-01
- evidence: Retail SLUS_005.61 (SHA-1 213733031136d095ca275d6957695aa25011cfa5): a whole-text scan of 294,400 loaded words finds exactly one jal to the matching-decomp-identified InitPAD target 0x800EE0D0, at 0x80012194; immediate dataflow gives (a0,a1,a2,a3)=(0x80166D68,0x22,0x8012F46C,0x22). tools/verify_pad.py --check compares all four arguments to the shipping GameConfig and --selftest proves both answers, 4/4.
- where: game/core/game_config.cpp (kPadSlot0Buf/kPadSlot1Buf and fixed-buffer bindings); tools/verify_pad.py
- gap: The two fixed buffers are complete and execution now passes CD initialization. Runtime input injection remains a separate gate because the observed boot path has not yet consumed a host-injected pad state.
- notes: padDriverFn/padSlotPtrTable/padSlotPtrStride remain zero deliberately: the retail InitPAD call passes the two buffers directly, and psxport falls back to those fixed buffers when no table is declared. This lands drop-in co-op input plumbing only; RE-07 still has no player-object, camera, routing or spawn implementation.

## enhancements

### RE-07 — THE PLAYER-OBJECT SYSTEM: one player struct, camera ownership, input routing, spawn path
- status: re-partial
- deps: RE-01, RE-02
- evidence: MEASURED 2026-08-24 against BOTH sources (AGPL mmx4 decomp + our own binary: instruction scans of the extracted SLUS_005.61 and Ghidra decompiles of resident RAM, scratch/decomp/x4_*.c). Player struct `g_Player = 0x801418C8`, PlayerObj 0xE4 (123-xref scan floor), with measured offsets active/+0, id/+1, character/+2 (X=0 table 0x80119DF0 vs Zero 0x8011AFF0), on_screen/+3, state/+4, x/y s16.16 with integer halves at +0xA/+0xE, bg_slot/+0x14, anim_table/+0x30, cur_anim/+0x47, hp/+0x5C; a second PlayerObj `g_Entity = 0x80175D58`. Camera = 3 layer structs @ 0x801419B0 stride 0x54; scroll x/y at +0xA/+0xE; mode-dispatched follow via table 0x800F3134 driven by func_80027850 reading the player's +0xA/+0xE halves with dead-zones (+0x30/+0x32), capped steps (+0x47..49), bound clamps (+0x1C..+0x22) that push the player back. Input route measured end-to-end: libpad buffers 0x80166D68 / 0x8012F46C → router func_80012328 (validity byte 0xFF/'A', ~buttons with opposite-direction cancellation) → P1 held/prev/edge 0x80166C08/C0A/C0C (edge == mmx4's controller_state) AND P2 trio 0x80166D50/D52/D54 decoded every frame but consumed by NOTHING outside the router. Spawn path: func_80035240 sets active=1 from engine character byte 0x80172203 and seeds from stage scratch; init_objects func_80023DB8 resets all pools with measured strides (main 48×0x9C @0x8013BED0..DC10); update_main_objects func_80021234 dispatches table 0x800F24A4 by id. Full per-item evidence, denominators and blind spots: docs/re-player-object.md. Typed read-only lens shipped game-side (`game/core/player_object.h`), pinned hermetically by ctest `x4_player_object` (positive planted-state reads plus non-aliasing negatives).
- where: docs/re-player-object.md; game/core/player_object.h; tests/test_x4_player_object.cpp; scratch/decomp/x4_*.c
- gap: The four pillars are located and named, but this is a MAP, not ownership — no native body exists and no guest write ships. Remaining UNKNOWNs are listed in docs/re-player-object.md §1–§4: most PlayerObj bytes beyond the measured ones, which UI state writes the character byte (writers seen at 0x8001C224/0x8001C310/0x80021E54 unattributed to screens), the stage-load caller of init_objects, checkpoint/respawn writer, parallax math in FUN_80028690, per-stage camera-bound population. Co-op remains force-suppressed under ORACLE/SBS and its evidence question is still OPEN. Drop-in co-op is a pc_enh with `affect: full` — it changes canon guest state.
- notes: The most invasive pc_enh in the workspace. Expect single-player assumptions everywhere: one player struct, one camera, one input route. The retail P2 button decode is the co-op seam candidate, not co-op itself.

### RE-08 — the projection / FOV setup site widescreen must drive from game state
- status: re-partial
- deps: RE-01, RE-02
- evidence: Retail SLUS_005.61 SHA-1 213733031136d095ca275d6957695aa25011cfa5: tools/verify_projection.py --check scans all 294,400 loaded words and finds exactly six CTC2 writes to CR24/25/26, all inside InitGeom/SetGeomOffset/SetGeomScreen; exactly one call to each, all in func_8001213C, with OFX=160, OFY=120, H=512. Its 4/4 selftest rejects a changed OFX, removed call, and extra raw writer. The title now wraps the untouched SetGeomOffset `0x800E90C8` and SetDefDrawEnv `0x800E9354` bodies through the reversible generated seam. `mmx4_runtime_test` drives those production transformations with an injected framework plan and proves exact 4:3 identity, 16:9 OFX/width 214/428, and unchanged OFY/H/x/y/h/UV/color/order; Clang links the full substrate against the unlanded typed framework candidate. Real-disc startup A/B reaches that retail wrapper and logs 320x240 -> 428x240, OFX 214, draw width 428 with the knob on (`scratch/logs/re08-typed-wide-boot.log`) and exact 320/160 identity off (`re08-typed-4x3-boot.log`). Against the separate shared-time candidate, normally paced PRESENT captures at frames 800/1000 prove a coherent 4:3 title-screen control. Wide pixels are not yet verified.
- notes: Do not attach a local present stretch or force native. X4 owns guest CR24 and RECT.w only; the typed framework plan owns host clip, renderer margin coverage, and presentation sampling. `RenderMode::enhancementsAllowed()` remains Native-only, so no interpolation/native-depth/internal-resolution apparatus enters the Gte title path. Psx/ORACLE/SBS resolve exact 4:3.
- gap: The framework is recorded at 9c2e3f1c; direct runtime inheritance removes the concrete Fps60 link and that pin includes the temporal-only helper split from neutral services. Capture matched title/gameplay fields with widescreen off/on and verify newly composed margins, unchanged central scale, and 4:3 identity; classify any title culling or 2D layout gap from pixels rather than adding offsets.
- where: tools/verify_projection.py; tools/verify_no_temporal_dependency.py; game/core/widescreen_controller.{h,cpp}; game/core/recomp_register.cpp; game/core/x4_runtime.{h,cpp}; tests/test_x4_runtime.cpp

### RE-09 — the game's OWN scripted wait states, fade ramps and frame-count timers
- status: re-partial
- deps: RE-01, RE-02
- evidence: JOB A's stock-path timing fault remains resolved by recorded framework pin 9c2e3f1c (issue #13). JOB B now implements the user's required synchronous operation at the actual owners instead of at presentation: Ghidra/generated-source cross-reading identifies direct issuer 0x80013890, archive issuer 0x80013AD8, ready callbacks 0x80013A20/0x80013E68, request table 0x800F0E18 (12-byte LBA/length entries), callback slot 0x8011DD20, state byte 0x801406AC, archive postprocess 0x80014780, wait bodies 0x80014C70/0x80014A90, and loading-presentation wait 0x80013530. `game/core/fast_wait.cpp` runs each generated issuer setup, feeds consecutive raw sectors from FIFO offset 12 through the generated callback while virtualizing only measured libcd leaves, pumps postprocess after every callback, and requires state 2 before returning. This timing is structural: producer handlers 0x800142BC/0x80014514 increment enqueued count 0x80137CF4 and reject `(enqueued-processed)>=7`; consumer 0x800147AC clears active records, increments processed count 0x80137CF0, advances its index modulo 16, and clears pending 0x8013BD40 when counts meet. Retail calls 0x80014780 once per main loop, so deferring consumption until the entire archive is not equivalent. The unchanged waits consequently execute zero iterations. A decoded-expression static assertion pins callback slot `(32786<<16)-8928 == 0x8011DD20`; focused production-leaf tests pin inactive super-calls, preparing/delivering CdReady, measured controls, raw+12 GetSector copying, setup VSync, and loading-presentation on/off behavior. Clang build and clang-tidy pass.
- where: game/core/fast_wait.{h,cpp}; game/core/recomp_register.cpp; game/core/x4_context.h; tests/test_x4_runtime.cpp; docs/behavior-map.md (fastwait row)
- gap: A bounded uninstrumented real-disc run against clean psxport 9c2e3f1c completed archive requests 64/113/51 (49/154/3 sectors) and direct requests 65/80 (6/4 sectors), including terminal-state checks and the measured PsyQ VSync(-1) GPU-timeout query, then remained live until the deliberate timeout. Exact destination-byte comparison for the current synchronous route and a capture proving no loading frame reaches presentation remain open. C025 is falsified because its equal-field RAM dumps measured the discarded presentation-withholding design. The game's OTHER scripted waits/fade ramps (non-load fades via 0x800129A4/0x800129F0 at 21/34 call sites) are still unclassified and must not be collapsed without separate RE.
- notes: Depends on RE-04 in practice — you cannot say what is a wait state until you know where the loads are.

## ownership

### RE-10 — native ownership seeded from the AGPL matching decomp
- status: todo
- deps: RE-01, RE-02
- evidence:
- where: game/ (no native body exists yet)
- gap: The substrate now exists, removing the mechanical blocker. The next prerequisite is a byte-match gate over one selected matching-decomp body and its generated body before importing any native implementation. **An imported body with no byte-gate is a hack with a citation attached.** mmx4 is a partial supply (18.5% upper bound) and dormant since 2025-08-25.
- notes: Anything imported here is AGPL-derived and stays in THIS repo forever — never lifted into psxport, which five ports share. Mark such files with `// SPDX-License-Identifier: AGPL-3.0-or-later` + `// derived from external/mmx4` (LICENSING.md), and keep `tools/check_license_containment.py` green.

## platform synchronization

### RE-11 — platform-HLE synchronization entry points and executable windows
- status: re-partial
- deps: RE-01
- evidence: `tools/verify_vsync.py` derives six contract groups from retail SLUS_005.61 without consulting matching-decomp labels. VSync 0x800E4DB0 calls helper 0x800E4EF8 twice and retains its own query/hblank/GPU/last-sync logic. The helper occupies exactly [0x800E4EF8,0x800E4F94), spins on counter 0x8011DC50 reaching a0, and carries the retail `VSync: timeout` literal. Init 0x800E56A4 zeroes that counter, clears 8 callbacks at 0x8011DC30, and registers 0x800E56FC for IRQ 0; the handler increments once and walks exactly those 8 callbacks. The title owns only the helper, dispatches the current class-0 handler with interrupted registers preserved, services pad and SPU once per field, then commits through the recorded neutral presenter. Selftest is 8/8, including raw-present, hardcoded-handler, missing-pad, and missing-SPU refusals. `tools/verify_no_temporal_dependency.py` scans shipping sources with one positive plus five source mutations and four binary-symbol mutations.
- where: game/core/vsync_sync.{h,cpp}; game/core/game_config.cpp (hle window); tools/verify_vsync.py; tools/verify_no_temporal_dependency.py
- gap: VBlank behavior and the title-side dependency boundary are implemented. Pin 9c2e3f1c supplies the neutral presenter, exact field-rate SPU cadence, temporal helper split, and explicit slot-presence policy; X4 deliberately leaves slot 1 absent until distinct P2 host state exists. The stronger no-fps60 binary control and a real-disc run must reconfirm presentation/capture/pacing. Every other unmeasured platform-HLE entry remains zero.
- notes: `vsyncTrap` remains zero by design: X4's guest owns its frame loop. The former watchdog stack was a sample inside a repeating deadline query, not proof that VBlank waiting caused the loop; issue #9 records the corrected diagnosis.
