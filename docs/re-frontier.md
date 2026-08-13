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

## THE STATE OF THIS PORT, 2026-08-12: ONE step is RE'd. Everything else is scaffolding

**Zero entries are `re-verified`. Exactly one — `RE-01`, the crt0 boot group — is `re-partial`,** and
the honest reading of that is: its reverse engineering is COMPLETE and gated by a tool, but its output
still cannot be written into `GameConfig` because psxport's `crt0_setup` transcribes Tomba!2's crt0 and
two of the eleven fields have no correct value for this game. See RE-01's gap, `docs/issues/0005-*`, and
claims C005 (what X4's crt0 does) / C006 (why the framework cannot run it). The framework fix is the
operator's — `external/psxport` here is a read-only pinned consumer.

Everything else below is `todo`, `blocked` or `skip-by-design`. There is still no recompiled substrate,
no native producer (and none planned), and no native body. `game/core/game_config.cpp` holds no guest
address in its struct: the eleven measured crt0 values sit beside it as `kCrt0*` constants with the
disassembly line behind each one, which is the honest shape while the plumbing is missing. A
plausible-looking wrong address breaks boot in a way that reads as a framework bug; six-of-eleven
written with the rest zeroed would be the same failure wearing a citation.

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
- status: re-partial
- deps:
- evidence: MEASURED 2026-08-12 from the extracted SLUS_005.61 (sha1 213733031136d095ca275d6957695aa25011cfa5) by disassembling and symbolically executing the PS-EXE entry function at pc0=0x800DAE8C straight through to its terminating break (43 instructions). Reproduce with per-field citations: `python3 tools/verify_crt0.py --check` (exit 0, 'CHECK PASSED: 17 shipped-vs-measured comparisons agree ... There is no second copy of these values' — the tool PARSES game/core/game_config.cpp and diffs the kCrt0*/kPsExe* constants it SHIPS against what it measures from the bytes in the same run, so a hand-edit of either side is red; it holds no expectation table of its own any more); `--selftest [--cross <other game exe>]` gates both classes 14/14 (16/16 with --cross), sabotaging BOTH sides of that comparison — a flipped immediate in the binary, three hand-edited constants in a copy of the shipping file, a hand-edited CITED SHA1, a HALF-filled GameConfig group, and three malformed-corpus shapes (missing / 0-byte / garbage) that must all refuse. THE GROUP: bssZeroLo 0x8012F418, bssZeroHi 0x80175F38 (size 0x46B20 = 289,568 B), stackTopBase 0x800DAF3C (word 0x00200000) with NO bias so sp=fp=0x80200000, stackTopBase2 0x8011CB74 (word 0x00008000), heapBase 0x80175F38 (== bss end; heap size 0x820C8 = 532,680 B), gp 0x8012F418, libcInit 0x800EDCDC (= 'addiu t2,0xA0; jr t2; addiu t1,0x39' i.e. BIOS A(39h) InitHeap(ptr,size); external/mmx4's symbols.us.txt independently names 0x800EDCDC InitHeap), gameMain 0x80012024, crt0 0x800DAE8C. heapSizePtr/heapBasePtr DO NOT EXIST in this crt0 — it passes base/size in a0/a1 and the function's ONE absolute store is 'sw ra' to 0x8012F418. mmx4's splat hypothesis (.bss 0x8012F418 size 0x46B20) is CONFIRMED, derived not pasted. Corroboration: the 0x3E8-byte overlap of .bss into the sector-padded text tail is all zero, so the clear loop destroys nothing.
- where: game/core/game_config.cpp (bssZeroLo/Hi, stackTopBase/2, heapBase, heapSizePtr, heapBasePtr, gp, libcInit, gameMain, crt0)
- gap: THE RE IS DONE; the GameConfig write is blocked on a FRAMEWORK fix, so the struct's boot group stays zero and this step is re-partial rather than re-verified. psxport's crt0_setup (external/psxport/runtime/recomp/native_boot.cpp:218) is a faithful transcription of TOMBA!2's crt0: 6 of 10 steps match X4 exactly, 4 contradict it. (1) line 221 hardcodes 'mem_r32(stackTopBase) - 8'; X4 has no bias instruction, so sp would be 0x801FFFF8, 8 bytes low. (2) line 226 stores heapsz to heapSizePtr unconditionally; X4 stores it nowhere, so field 0 writes to guest 0x00000000. (3) line 228 same for heapBasePtr. (4) only c->r[4] is set before rec_dispatch(libcInit), but BOTH games' libcInit is the BIOS A(39h) InitHeap thunk taking the size in a1, so c->r[5] is missing entirely — a latent framework bug affecting Tomba!2 too, not just X4. (2) and (3) are decisive: no address exists that is not a lie, because the correct answer is 'this game has no such global'. Generic upstream fix (no X4 literal, no AGPL line, safe for psxport): add int32_t stackTopBias to GameConfig (Tomba!2 = -8, X4 = 0); treat heapSizePtr/heapBasePtr == 0 as 'kept in registers only, do not store'; set c->r[5] = heapsz unconditionally. Framework edits are NOT this agent's to make (external/psxport is a read-only pinned consumer) — handed to the operator.
- notes: Cross-checked two ways. (a) The extractor was run on Tomba!2's MAIN.EXE and re-derived all 12 of the boot-group values Tomba2Engine/game/core/game_config.cpp recorded independently by hand (bssZeroLo 0x800BE0D8, bssZeroHi 0x80106228, stackTopBase 0x800A3F88, bias -8, stackTopBase2 0x800A3F8C, heapBase 0x80106228, heapSizePtr 0x800ABEF8, heapBasePtr 0x800ABEF4, gp 0x800BE0D4, libcInit 0x80089860, gameMain 0x80050B08, crt0 0x800896E0) — that is the positive control proving the tool reads binaries rather than echoing constants, and it is what turned 'the framework hardcodes -8' from a suspicion into a measurement. (b) 0x800EDCDC decodes as a BIOS A-table thunk for function 0x39 and external/mmx4 independently names that address InitHeap. RE-02 (recompiler seeds) is unblocked by this step: gameMain 0x80012024 and crt0 0x800DAE8C are now real seed candidates with a justification.

### RE-02 — recompiler seed set for SLUS_005.61
- status: todo
- deps: RE-01
- evidence:
- where: game/recomp_seeds.json
- gap: Seeds are grown EMPIRICALLY from `[recomp-MISS] 0x800xxxxx` fail-fasts on a booting port, each with the rationale for how the address is reached. There is no booting port yet, so the file holds no addresses. Never copy another game's seeds, and never paste one out of external/mmx4 without the disassembly line that justifies it — a foreign seed landing inside real text SPLITS a function at an arbitrary offset, the emit SUCCEEDS, and the recomp is silently corrupt.
- notes: The overlay half of the usual seed problem does not exist here — see RE-03.

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
- evidence: The boot exe holds a 161-entry literal path table at file offset 0xDED4E — 138 `E:\ROCKX4\USA\ARC\*.ARC` + 11 STR + 11 XA + the build's own `E:\ROCKX4\0801US\PROG\ROCKX4.EXE`. The 138 ARC names match the 138 ARC files on disc EXACTLY (set difference empty in both directions), so the table is the complete asset manifest and a ready-made index for a prefetch design. The executable links PSY-Q sys.c 1.129 / intr.c 1.74 / bios.c 1.81, so the framework's stock-libcd chokepoint set is the likely SHAPE.
- where: game/core/game_config.cpp (cdInit, cdCommand, cdSync, cdReadPrim, cdFileLoad, cdAsyncRead, …)
- gap: No address located, and the loader MECHANISM is not confirmed — nobody has opened Ghidra on it. The RAM-budget premise is now MEASURED rather than estimated (RE-01, 2026-08-12): crt0 calls BIOS InitHeap with base 0x80175F3C and size 0x820C8 = 532,680 bytes, that being (stack top 0x00200000 - reserve 0x00008000 - heap base 0x00175F38). PL00_U.ARC is 796,672 B, so it CANNOT be loaded whole into the heap — 264 KB too big. `.ARC` files are therefore presumably parsed or streamed in pieces (most likely straight to VRAM/SPU-RAM). **The budget is measured; the streaming CONCLUSION is still a HYPOTHESIS** — nothing has been observed doing it, and a loader could also target the 0x8000 reserve or a static .bss buffer. This step is where it gets confirmed or killed.
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
- status: todo
- deps: RE-01
- evidence:
- where: game/core/game_config.cpp (padSlot0Buf, padSlot1Buf, padDriverFn, padSlotPtrTable, padSlotPtrStride)
- gap: Nothing located. The PSY-Q cohort says libpad rather than a custom SIO driver is the likely shape, which says what to look for, not where.
- notes: `padSlot1Buf` is drop-in co-op's INPUT half, and the framework already reads two slots — runtime/recomp/pad_input.cpp:550 `uint32_t bufs[2] = { c->cfg->padSlot0Buf, c->cfg->padSlot1Buf };`. Do NOT read a working second pad as co-op being close: the player-object half (RE-07) is supported by nothing.

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
  SOURCE LEAD, not a runtime observation from this port. The next measurement must establish whether
  later game modes overwrite CR24/25/26 and which writes are world projection versus 2D/HUD setup.
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
- gap: Blocked on there being a substrate to byte-match AGAINST. psxport's override registry wants (addr, native, gen) triples whose native body byte-matches the substrate body, and a matching decomp is a supply of exactly that — but nothing may be imported before there is a substrate and a byte gate. **An imported body with no byte-gate is a hack with a citation attached.** mmx4 is a PARTIAL supply (18.5% upper bound) and dormant since 2025-08-25.
- notes: Anything imported here is AGPL-derived and stays in THIS repo forever — never lifted into psxport, which five ports share. Mark such files with `// SPDX-License-Identifier: AGPL-3.0-or-later` + `// derived from external/mmx4` (LICENSING.md), and keep `tools/check_license_containment.py` green.
