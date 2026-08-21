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
owns a measured resident bootstrap: 6,192 binary roots → 7,533 functions, real generated registry,
resident range, and runtime dispatch through InitHeap into `gameMain`. Explicit indirect seeds remain
empty because no runtime `recomp-MISS` has justified one. RE-11 now owns a retail-derived VBlank
producer at libetc's exact counter-wait helper, but the boot path never calls that blocking helper:
focused CD/IRQ logging proves the former VSync watchdog stack was a hot-loop sample from a
`VSync(-1)` deadline query. The current stop is RE-04's unclaimed CD IRQ2 contract.

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
- gap: The group is runtime-confirmed through InitHeap and guest-main dispatch. Later boot progress is blocked by the unclassified CD IRQ2 callback contract, not by an RE-01 field.
- notes: psxport 726d10c9 made the boot mechanism generic; issue #5 and falsified claim C006 preserve the root cause. The cross-control re-derives all 12 independently recorded Tomba!2 values.

### RE-02 — recompiler seed set for SLUS_005.61
- status: re-partial
- deps: RE-01
- evidence: Retail SLUS_005.61 (SHA-1 213733031136d095ca275d6957695aa25011cfa5) through psxport's real emit.py: 6,192 binary-rooted seeds → 7,533 recompiled functions, including crt0 0x800DAE8C and gameMain 0x80012024; one computed `jr ra` of 5,534 sites; zero overlays; version 2026-08-12.1. `tools/verify_recomp_bootstrap.py --selftest` is 2/2: real positive emission plus emitter refusal of an out-of-text explicit seed. Clang links the generated registry. A software-Vulkan bounded boot runs InitHeap and dispatches guest main with no recomp miss before the stock CD-init IRQ2 retry loop.
- where: game/recomp_seeds.json; tools/ensure_recomp.py; tools/verify_recomp_bootstrap.py; game/core/recomp_register.cpp; game/core/game_config.cpp (recMainLo/Hi)
- gap: Runtime-computed targets on paths beyond the current CD IRQ2 stall remain unobserved. Grow the explicit list only from future `[recomp-MISS]` fail-fasts. The first apparent miss at 0x800EDCDC was NOT a missing seed: rec_func_index already contained it; zero recMainLo/Hi made the router bypass main_dispatch. That root cause is now mechanically gated by verify_crt0.py.
- notes: The overlay half does not exist here (RE-03). Never copy another game's seeds or paste a decomp address without a runtime miss/disassembly rationale; a foreign in-range seed can split a real function while emission still succeeds.

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
- status: todo
- deps: RE-01
- evidence: The boot exe holds a 161-entry literal path table at file offset 0xDED4E — 138 `E:\ROCKX4\USA\ARC\*.ARC` + 11 STR + 11 XA + the build's own executable. The 138 ARC names exactly match the disc set. `tools/verify_vsync.py` independently checks the observed retail call edges 0x800E5ACC → 0x800E5C14 → 0x800E74DC → 0x800E6E14 → 0x800E4DB0, including 0x800E74DC's own `CD_init:` literal and the final `VSync(-1)` argument; no matching-decomp label is used as proof. A focused runtime shows the native controller repeatedly accepting commands 0x01/0x0A and raising IRQ2 (`I_STAT=0x004`, `I_MASK=0x00D`), while the one registered BIOS interrupt element reports that it claimed no source.
- where: game/core/game_config.cpp (cdInit, cdCommand, cdSync, cdReadPrim, cdFileLoad, cdAsyncRead, …); scratch/logs/recomp-range-fixed-lvp.log (untracked runtime evidence)
- gap: Classify the registered interrupt element at 0x8013BBF8 and the libcd IRQ callback/result-state contract before selecting any ownership boundary. The controller already produces responses, so forcing CdInit success would bypass an active guest path rather than repair the missing delivery. The loader mechanism remains unconfirmed. The measured heap is 532,680 bytes while PL00_U.ARC is 796,672 bytes, so it cannot fit whole in the heap; parsing/streaming is still a hypothesis because the loader could target the reserve or static BSS.
- notes: This is also the step that separates enhancement job A from job B. psxport converts CD/file I/O to PC-native SYNCHRONOUS under the FAIL-FAST rule, so raw seek/read latency is largely gone BY CONSTRUCTION; what remains is RE-09's scripted waits. Measure them apart before quoting a load-time number.

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
- gap: The two fixed buffers are complete. The substrate now boots, but execution has not passed CD initialization, so runtime injection remains a separate gate.
- notes: padDriverFn/padSlotPtrTable/padSlotPtrStride remain zero deliberately: the retail InitPAD call passes the two buffers directly, and psxport falls back to those fixed buffers when no table is declared. This lands drop-in co-op input plumbing only; RE-07 still has no player-object, camera, routing or spawn implementation.

## enhancements

### RE-07 — THE PLAYER-OBJECT SYSTEM: one player struct, camera ownership, input routing, spawn path
- status: todo
- deps: RE-01, RE-02
- evidence: The only thing pointing anywhere is a LEAD, not a finding: per-character data is already split per file on the disc — PL00_U / PL01_U / PL02_U.ARC (796,672 / 741,376 / 796,672 B) for the three playable characters, and `_X` / `_Z` variants of the per-stage collision and stage archives (COL0B_0X vs COL0B_0Z, ST0B_0X vs ST0B_0Z). That is a hint the engine already parameterises by character. **It was NOT verified in code.**
- where: game/ (no native body exists yet); the co-op feature will hang off game/core/enhancements.cpp's cv_coop
- gap: THE RE TARGET THIS WHOLE PORT TURNS ON, and the design stops here on purpose: the player-object LAYOUT IS UNKNOWN. Nobody has located the player struct, the camera's owner, the input route, or the spawn path, and `docs/plans/enhancements.md` therefore stops where the layout stops rather than naming an offset. A plan that names a fake offset is worse than a plan that says "unknown". Drop-in co-op is a pc_enh with `affect: full` — it changes canon guest state — so it is force-suppressed under ORACLE/SBS, which means the SBS oracle is only meaningful with co-op OFF and the co-op path needs its own evidence. What that evidence is, is an OPEN QUESTION.
- notes: The most invasive pc_enh in the workspace. Expect single-player assumptions everywhere: one player struct, one camera, one input route.

### RE-08 — the projection / FOV setup site widescreen must drive from game state
- status: todo
- deps: RE-01, RE-02
- evidence: STATIC REFERENCE LEAD, 2026-08-13: the matching `external/mmx4` decomp's fully written
  `func_8001213C` (`src/main/2824.c`) calls `SetGeomOffset(0xA0, 0x78)` then
  `SetGeomScreen(0x200)`. Its caller `func_80012024` is the measured `gameMain` (RE-01), so this is
  the game's boot-time GTE projection initialisation: OFX=160, OFY=120, H=512. C001 establishes that
  the decomp's addresses need no region translation for our retail target; nevertheless this is a
  SOURCE LEAD, not a runtime observation from this port. A source census on 2026-08-13 found no other
  `SetGeomOffset`, `SetGeomScreen`, inline `gte_SetGeom*`, or source-assembly `ctc2` CR24/25/26 writer
  in `external/mmx4/src`; this narrows the remaining work to raw COP2 writers in the retail binary and
  a runtime classification of their use as world projection versus 2D/HUD setup.
- where: game/ (the widescreen feature will hang off cv_widescreen)
- gap: The boot setup site is now located, but it does not yet justify a patch: X4 may write a
  different projection per scene, camera, or 2D pass after boot. Find and classify every subsequent
  CR24/CR25/CR26 writer before changing the guest state. The structural point that matters more than
  the address: psxport's own widescreen is `affect: none` — a host-side read-only overlay driven by a
  native renderer, shifting the projection centre OFX rather than stretching the present. X4 has NO
  native renderer, so a widescreen change here reaches the GUEST's own projection setup and is
  therefore `affect: full`. That reclassification is why it is a suppressed `pc_enh` and not a render
  overlay, and misfiling it as `affect: none` would skip both the suppression requirement and
  behavior.py check's only real assertion.
- notes: The target behavior is still a wider FOV, not a stretched display: a 16:9 path must set the
  appropriate world-projection state through `x4::enh(x4::cv_widescreen)` while leaving it unchanged
  when disabled or in oracle/SBS runs. Do not attach the CVar until the write census distinguishes
  world from HUD.

### RE-09 — the game's OWN scripted wait states, fade ramps and frame-count timers
- status: todo
- deps: RE-01, RE-02
- evidence:
- where: game/ (the fast-wait feature will hang off cv_fastwait)
- gap: Nothing located, and the FIRST thing this step must do is separate itself from I/O latency. psxport already converts CD/file I/O to PC-native SYNCHRONOUS under the FAIL-FAST rule, so raw seek/read time is largely gone by construction (job A: measure it, do not build it). What remains is the game's own timers, which no amount of I/O speed touches (job B: a guest-state change, pc_enh, affect: full). A single "load time" figure that mixes the two is unusable.
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
- evidence: `tools/verify_vsync.py` derives six contract groups from retail SLUS_005.61 without consulting matching-decomp labels. VSync 0x800E4DB0 calls helper 0x800E4EF8 twice and retains its own query/hblank/GPU/last-sync logic. The helper occupies exactly [0x800E4EF8,0x800E4F94), spins on counter 0x8011DC50 reaching a0, and carries the retail `VSync: timeout` literal. Init 0x800E56A4 zeroes that counter, clears 8 callbacks at 0x8011DC30, and registers 0x800E56FC for IRQ 0; the handler increments once and walks exactly those 8 callbacks. The shipping route owns only the helper, paces from the guest-programmed display standard, dispatches the retail handler with the interrupted registers preserved, and presents the guest-owned VRAM. Selftest is 4/4 and produces the other answer for a broken call edge, a 7-slot handler, and a collapsed executable window. A real Clang runtime installs the route at the exact window.
- where: game/core/vsync_sync.{h,cpp}; game/core/game_config.cpp (hle window); tools/verify_vsync.py
- gap: The observed boot path calls VSync only with mode -1 from the CD command deadline and therefore never reaches the blocking helper; runtime behavior of the helper and registered callbacks remains unverified. The new focused trace moves the live stop to RE-04: CD IRQ2 is raised and unmasked, but the registered BIOS element does not claim it. Every other HLE entry remains zero/unmeasured.
- notes: `vsyncTrap` remains zero by design: X4's guest owns its frame loop. The former watchdog stack was a sample inside a repeating deadline query, not proof that VBlank waiting caused the loop; issue #9 records the corrected diagnosis.
