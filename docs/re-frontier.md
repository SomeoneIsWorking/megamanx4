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

## THE STATE OF THIS PORT, 2026-08-12: NOTHING IS RE'd. The repo is scaffolding

Every entry below is `todo`, `blocked` or `skip-by-design`. **Zero are `re-verified`.** That is not
modesty — it is the whole state of the port. There is no recompiled substrate, no native producer (and
none planned), no `GameConfig` value except this port's own env-var names, and no native body.
`game/core/game_config.cpp` is all zeros with TODOs pointing back here, and that is the honest value: a
plausible-looking wrong address breaks boot in a way that reads as a framework bug.

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
- status: todo
- deps:
- evidence: PS-EXE header, read by `tools/extract_exe.py` from the extracted 1,179,648-byte image (sha1 213733031136d095ca275d6957695aa25011cfa5): entry pc0 = 0x800DAE8C, text 0x80010000 + 0x11F800, initial sp 0x801FFFF0, and d_size/b_size both 0 — so the game clears its own BSS in crt0. SYSTEM.CNF: `BOOT = cdrom:\SLUS_005.61;1`, `TCB = 4`, `EVENT = 16`, `STACK = 801FFF00` — a small, single-threaded runtime, and no boot stub.
- where: game/core/game_config.cpp (bssZeroLo/Hi, stackTopBase/2, heapBase, heapSizePtr, heapBasePtr, gp, libcInit, gameMain, crt0)
- gap: The entry PC and the text range are the only values MEASURED, and they are not written into GameConfig because the framework's crt0_setup consumes the whole group — a lone entry PC with a zeroed BSS range would run a wrong crt0 rather than refusing. Needs the entry disassembled (Ghidra via external/psxport/tools/decomp.sh). mmx4's splat config claims .bss at 0x8012F418 size 0x46B20; that is a HYPOTHESIS to confirm, not a value to paste.
- notes: mmx4 names OUR addresses with no translation (its check.us.txt declares our sha1), so use it to LOCATE and then confirm against the bytes here. Reading it puts you under the AGPL firewall — what you learn stays in this repo, never in psxport.

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
- gap: No address located, and the loader MECHANISM is not confirmed — nobody has opened Ghidra on it. The arithmetic says PL00_U.ARC (796,672 B) does not fit the ~565 KB of RAM left after .text+.bss, so `.ARC` files are presumably parsed or streamed in pieces (most likely straight to VRAM/SPU-RAM) rather than loaded whole. **That is a HYPOTHESIS from arithmetic and must not be recorded as measured.** This step is where it gets confirmed or killed.
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
- evidence:
- where: game/ (the widescreen feature will hang off cv_widescreen)
- gap: Nothing located. The structural point that matters more than the address: psxport's own widescreen is `affect: none` — a host-side read-only overlay driven by a native renderer, shifting the projection centre OFX rather than stretching the present. X4 has NO native renderer, so a widescreen change here reaches the GUEST's own projection setup and is therefore `affect: full`. That reclassification is why it is a suppressed pc_enh and not a render overlay, and misfiling it as `affect: none` would skip both the suppression requirement and behavior.py check's only real assertion.
- notes:

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
