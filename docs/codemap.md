# Codemap — what's where, what's done, what's missing

The orientation map: consult it at the START of a task to avoid re-deriving structure, and update it in
the SAME commit that lands or changes a subsystem. A stale map is worse than none — a subsystem is
marked done only when VERIFIED on real data, never to look better.

Companions: `docs/re-frontier.md` (the ordered RE steps: real vs hack), `docs/behavior-map.md` (every
intentional divergence, tool-generated), `docs/references.md` (the AGPL decomp and exactly what it does
and does not buy), `docs/config.md` (this port's own knobs), `docs/plans/enhancements.md` (the design of
the three deliverables), `docs/info/` (claims + instruments), `docs/issues/` (what has been tried and
ruled out).

**Status vocabulary:** ✅ verified on real data · 🟡 partial (gap named) · 🔬 in progress ·
⬜ not started · ❓ unresolved question · ➖ not applicable to this game · 🔴 regressed.

## Read this before anything else: the honest state, 2026-08-12

**This repo is scaffolding. The port does not run and nothing about the game is reverse-engineered.**
What exists is provisioning, the framework seam (compiling, all-zero), the three enhancement CVars, the
registries, and a vendored AGPL matching decomp whose declared build target is the same SHA-1 as the
image extracted from this disc. There is no recompiled substrate, no `megamanx4_port` binary, and no
native body. Every ⬜ below is real.

**The defining structural fact, measured:** **X4 has NO code overlays. The boot executable IS the whole
engine.** That is the opposite of Vagrant Story (21 `.PRG` modules) and it removes a whole class of work
from this port. Evidence, denominators and blind spots are in `docs/info/claims/002-*` — in summary: all
163 disc files enumerated (515,298,768 B), all 138 `.ARC` files read in full (25.2 MiB), and **0 of 138
contain even one `jr $ra`**; the calibrated code-window filter reads median 2.5% / mean 3.5% on ARCs
against 99.4% over 16,367 windows at the header-declared entry region; ≤9.1% of `j`/`jal` targets land
inside `.text` in any ARC against 85.0% of 20,428 in the boot exe; and the decomp's splat config declares
exactly ONE code segment and not one overlay. One file lied on a single signal (`MOJIPAT.ARC`, 60.1%
code-plausible glyph bitmaps, 0 epilogues) which is why three were needed. **BLIND SPOT: this asserts "no
PLAIN R3000A code outside the boot exe", not "no code" — packed or compressed code inside an `.ARC` would
read as a texture.** ~430 MB of `.STR`/`.XA` was classified by container format and the boot exe's own
path table, sampled rather than read whole; that is the largest unscanned mass on the disc.

**Consequence for the port:** `GameConfig` needs no overlay load bases and the RAM map is fully static
(.text `0x80010000..0x8012F800`; the decomp claims .bss `0x8012F418 + 0x46B20`, which is the reference's
claim, not our measurement; stack `0x801FFF00` per SYSTEM.CNF / `0x801FFFF0` per the header). Note that
`PL00_U.ARC` (796,672 B) does not fit the remaining free RAM, so `.ARC` files are presumably parsed or
streamed in pieces rather than loaded whole — **that last clause is a HYPOTHESIS from arithmetic, not a
measurement**, and RE-04 is where it gets confirmed or killed.

## The two halves (plus the reference)

| | |
|---|---|
| `external/psxport/` | the PSX-generic framework (submodule, pinned `7dc380c5`): MIPS→C recompiler, runtime substrate, GTE/SPU/MDEC/CD/GPU backends, SDK HLE, SBS differential harness, SDL_GPU renderer. **Not ours** — fix framework bugs upstream in the workspace dev clone, never in this submodule. |
| `game/`, `tools/`, `generated/` | this port: the seam, the enhancement gates, the RE, the provisioning, and (eventually) the recompiled substrate. |
| `external/mmx4/` | an **AGPL-3.0 matching decompilation** of this exact executable (pinned `1922fcd3`, dormant since 2025-08-25) — a read-only REFERENCE, never built or linked here, and **never copied into psxport**. See `docs/references.md` and `LICENSING.md`. |

## Subsystems

| subsystem | where | status | notes |
|---|---|---|---|
| Disc resolution | `tools/resolve_disc.py` | ✅ | One implementation of CLI arg > `$PSXPORT_X4_DISC` > `.env` > a `*.chd` in the repo root; refuses (exit 2) naming all four sources rather than returning empty, and refuses when a configured path does not exist instead of falling through to a different disc. `run.sh`, `extract_exe.py`, `discdump.py` and `verify_decomp_targets.py` all go through it. |
| Disc listing | `tools/discdump.py` | ✅ | Thin wrapper over the framework's own `discdump`, resolved through `$PSXPORT_DIR`. `list` mode added here, because the module inventory had to be enumerated before anything could be said about overlay shape. Refuses (exit 2) when `discdump` is missing, the disc is unresolvable, or a read yields zero entries. |
| Disc → executable provisioning | `tools/extract_exe.py` | ✅ | Extracts `SLUS_005.61` (1,179,648 B) with psxport's own `discdump`, prints the PS-EXE header, and checks the SHA-1 against the value read AT RUN TIME out of `external/mmx4/check.us.txt`. Says explicitly when it CANNOT check (decomp submodule absent) rather than passing quietly. |
| Code / overlay census | `tools/code_scan.py` | ✅ | The three-signal detector behind the overlay finding. Imports the code/data discriminator from `external/psxport/tools/exe_similarity.py` so there is ONE calibrated copy. `--selftest` gates BOTH classes (POSITIVE = 64 KiB at the header entry, ≥95%; NEGATIVE = a media file, ≤2%); `--census` refuses on a zero-match glob. |
| crt0 / boot-group derivation | `tools/verify_crt0.py` | ✅ | Symbolically executes a PS-X EXE's entry function to its terminating `break` and prints every boot-group field with the instruction address that produced it, plus a per-step MATCHES/CONTRADICTS verdict against psxport's `crt0_setup`. `stackTopBase2` is identified by DATAFLOW (the operands of the heap-size `subu`), not by elimination — the elimination version printed `AMBIGUOUS: 2 absolute loads` rather than guessing, which is why it was replaced. **`--check` parses `game/core/game_config.cpp` and diffs the `kCrt0*`/`kPsExe*` constants it SHIPS against what it measured from the bytes in the same run (17 comparisons) — it holds NO expectation table of its own, because it used to and the shipped value was then ungated (`kCrt0GameMain = 0x80999999` passed every gate; see I006's known failure modes).** `--selftest [--cross <other exe>]` gates both classes 14/14 (16/16 with `--cross`) THROUGH that same shipping-path comparison: the strongest positive is that over Tomba!2's `MAIN.EXE` it reproduces all 12 boot-group values that repo recorded by hand; the negatives sabotage both sides — a flipped-immediate mutation in the binary, three hand-edited constants in a copy of the shipping file, a hand-edited CITED SHA1, a HALF-filled `GameConfig` crt0 group, `main()` being REFUSED as not-a-crt0 with its denominator, and three malformed-corpus shapes (missing path, 0-byte, garbage) that all exit 2 saying they SCANNED NOTHING. States its blind spots every run (immediate-only tracking, straight-line walk, static image so it says nothing about runtime). |
| Decomp-target verification | `tools/verify_decomp_targets.py` | ✅ | Reads mmx4's `target_path:` from its splat config and its expected hash from `check.<variant>.txt` (mmx4 states no `sha1:` in the yaml, unlike the sibling tree this was adapted from). Prints denominators and blind spots every run; refuses on a missing submodule or zero configs; `--selftest` proves it can report a MISMATCH. |
| Licence containment | `tools/check_license_containment.py` | ✅ | Has AGPL material from mmx4 reached `psxport`? Four detection classes with the Sony-SDK vocabulary and the TRACKED generic-vocabulary list (`docs/info/containment-baseline.txt`, 25 names, `--write-baseline` regenerates) subtracted; `--selftest` gates 19 checks in both directions and was proven non-vacuous by reintroducing a real past bug. **It reported clean over ZERO files until 2026-08-12** — an uninitialised submodule directory and a fully git-ignored tree both read as `PASS`, and the baseline came from directories outside this repo so a bare clone FAILED with 27 false hits; both fixed, both now gated, full write-up in `docs/info/instruments/005-*` under "Known failure modes". Blind spot printed on every run: it cannot see paraphrase, renamed identifiers, or struct layouts carried in a head, nor a leak of one of the 25 excluded names. |
| Static recompilation | `game/recomp_seeds.json` → `generated/` | ⬜ | **Not started.** The seed file is empty (RE-02). RE-01 no longer blocks it: `crt0 = 0x800DAE8C` and `gameMain = 0x80012024` are now measured, so there are two justified seed candidates. The overlay half of the usual problem does not exist here — see the structural fact above. |
| Framework seam — config | `game/core/game_config.cpp` | 🟡 | Compiles. **The crt0 boot group is now MEASURED but deliberately still zero, and that gap is a FRAMEWORK defect, not missing RE** (RE-01 `re-partial`, issue #5, claims C005/C006). Every one of the eleven values is a `kCrt0*` `static constexpr` with the disassembly line behind it and four `static_assert`s tying them together; **`tools/verify_crt0.py --check` READS THIS FILE and diffs those constants against the bytes**, so the shipped value is gated by something that runs rather than by the `static_assert`s (which check relations only — `hi - lo == 0x46B20` holds when both are wrong). It also asserts the struct's crt0 group is all-zero or all-filled; a partial fill is red. They are not in the struct because psxport's `crt0_setup` transcribes Tomba!2's crt0: 6 of its 10 steps match X4, 4 do not, and two of those (`heapSizePtr`/`heapBasePtr`) have NO correct value here because X4's crt0 has no such globals. Every other guest address is still `0` with its frontier step named. Non-zero port facts, not RE: `discEnvVar`, `cardEnvVar`/`cardDefaultPath`, `paceQuota = 1`, `windowTitle`, `preserveVramBackdrop = 1`. |
| Framework seam — hooks | `game/core/game_hooks.cpp` | ⬜ | Compiles. Neutral bodies where "nothing is owned" is the correct semantic; fail-fast `abort()` bodies for every framework path this port has not stood up. `bootInit` refuses rather than dispatching `gameMain == 0`. `frameUpdate`/`drawOTag` are fail-fast **permanently** — see the ➖ rows below. |
| Framework seam — recomp registry | `game/core/recomp_register.cpp` | ⬜ | Deliberately UNWRITTEN and excluded from the compiling target — it is the one TU that names `generated/` symbols. It `#error`s under `MMX4_HAVE_SUBSTRATE` (which the port target defines) so a substrate cannot appear without someone writing the real registry. |
| **Enhancement gates** | `game/core/enhancements.{h,cpp}` | 🟡 | **The thing that makes this port what it is.** Three `pc_enh` CVars (`PSXPORT_X4_WIDESCREEN` / `_COOP` / `_FASTWAIT`) on the framework's CVar ladder, and ONE chokepoint `x4::enh()` that force-suppresses all of them under `PSXPORT_ORACLE` / `PSXPORT_SBS` / `PSXPORT_SBS_MODE`. 🟡 because the gates exist and compile while **nothing is gated behind them yet** — the features need RE-07/RE-08/RE-09. X4 is the workspace's first real consumer of `pc_enh`. |
| Process entry | `game/core/main.cpp` | 🟡 | Compiles. Framework bring-up in the standard order (GTE/MDEC/SPU/GPU/CD/HLE/pad), then `native_boot_run`. Never executed: there is no binary to run yet. |
| Build | `CMakeLists.txt`, `cmake/megamanx4_port.cmake` | 🟡 | `psxport` (framework lib) and `megamanx4_seam` (OBJECT lib over the seam TUs including `enhancements.cpp` — the gate that runs today) configure from a bare clone. `megamanx4_port` is configured ONLY when `generated/rec_sources.cmake` exists, with a loud configure-time STATUS saying why it does not. `PSXPORT_DIR` defaults to the submodule and is spelled exactly once. |
| Play launcher | `run.sh` | 🟡 | The USER's; agents must never run it. Does every step that is real today and then STOPS with exit 3, naming RE-01/RE-02 as what blocks the recompile. |
| Registries | `tools/re_frontier.py` (shim), `tools/info.py`, `tools/catalog.py`, `tools/behavior.py` | ✅ | The RE-frontier tracker is a SHIM onto the shared engine at `external/psxport/tools/port/re_frontier.py` — this repo grows no fork of it. The other three are copies (no hoisted engine exists for them yet); that divergence is a known cost, see below. |
| Behaviour map | `docs/behavior-map.md`, `tools/behavior.py` | ✅ | Generated by the tool, three `planned` `pc_enh`/`affect: full` entries with suppression-citing guards. `behavior.py check` is the ONLY automated gate that this port's canon-affecting enhancements stay ORACLE/SBS-suppressed, which is why the copy was FIXED here before use (three fixes — see `docs/info/instruments/003-*` and `docs/issues/0002-*`). |
| Publication audit | `tools/go_public.py` | 🟡 | Copied from `vagrant/tools/` (the fixed copy: it used to print "RESULT: clean ✓ — ready to publish" over zero blobs scanned). CONFIG tuned here for PSX: `*.chd`/`*.cue`/`*.ecm`/`*.pbp` and `SLUS_005.61` added to the copyright PATH patterns — which is safe there and deliberately NOT in `.gitignore`, where check C would turn them into prose search tokens. |
| Gate on a built binary | — | ⬜ | **Deliberately absent.** A gate drives an ALREADY-BUILT binary and there is none. When it is written, on `Tomba2Engine/tools/gate.py`'s shape: it neither builds nor extracts, it drives the binary, it prints its own denominator every run, its refusals exit 2 rather than 0, and it asserts the ADVANCE past the prologue plus the END STATE — never an absolute frame number (a hardcoded expected frame fails for reasons unrelated to your change; measured 27 on one build where an older note said 39). No boot measurement may be quoted before this exists. |
| Everything about the game itself | — | ⬜ | Boot, CD, the player-object system, wait-state timers and pad: **not started.** Widescreen has one static source lead — boot `func_8001213C` sets GTE OFX/OFY/H to 160/120/512 — but its later write census and runtime verification are still absent. `docs/re-frontier.md` is the ordered list. |

## What this port deliberately does NOT build — ➖, with the USER decision cited

USER, 2026-08-12: *"Mega Man doesn't need native producers or lerp or native depth, it's already 60fps."*
These rows are ➖ **not-applicable**, not ⬜ not-started. Marking them ⬜ would put four steps on the
roadmap the USER has ruled out of scope; marking them ➖ without the citation would read as an
unexplained gap.

| subsystem | status | why |
|---|---|---|
| Native producers / `ProducerScope` | ➖ | There is no native renderer here, so nothing produces a picture from game state. The guest draws. |
| Frame interpolation (`fps60`, lerp) | ➖ | The game already runs at 60fps. psxport's hardest constraint — the picture must come from game state, and lerp is native too — exists to serve interpolating a 30fps guest. |
| Native depth / obj_depth compositing | ➖ | Same: no native renderer to composite. |
| Native frame loop / `PcScheduler` | ➖ | The guest's own loop runs on the substrate. `GameHooks::frameUpdate` and `drawOTag` are fail-fast permanently, and `GameConfig`'s OT/packet-pool and scheduler groups have no reader by design. |
| Overlay load bases / router slots | ➖ | **Measured:** this disc has no code overlays. See the structural fact above, and its blind spot. |

## What this port DOES build — the actual work, all ⬜, with its RE dependency

| deliverable | class | status | blocked on |
|---|---|---|---|
| Widescreen | `pc_enh`, `affect: full` | ⬜ | **RE-08** — boot projection setup is located in the matching decomp (`func_8001213C`: GTE OFX/OFY/H = 160/120/512), but every later projection writer still needs a census and runtime verification before a patch can distinguish world from HUD. Note the reclassification: psxport's own widescreen is `affect: none` (a host-side read-only overlay driven by a native renderer), but X4 has no native renderer, so a widescreen change here reaches the GUEST's own projection setup. That is why it is a suppressed `pc_enh` and not a render overlay. |
| Scripted-wait / fade collapse | `pc_enh`, `affect: full` | ⬜ | **RE-09** — the game's OWN wait states, fade ramps and frame-count timers. **Raw I/O latency is a different job and is already largely gone by construction**, because psxport converts CD/file I/O to PC-native SYNCHRONOUS under the FAIL-FAST rule. Do not quote one number for both. |
| Drop-in co-op (P2 spawns as the other hunter) | `pc_enh`, `affect: full` | ⬜ | **RE-07 — the PLAYER-OBJECT SYSTEM**, and this is the step the whole port turns on. The most invasive `pc_enh` in the workspace: it breaks one-player-struct / one-camera / one-input-route assumptions. The INPUT half is already framework-supported (`runtime/recomp/pad_input.cpp:550` reads `uint32_t bufs[2] = { c->cfg->padSlot0Buf, c->cfg->padSlot1Buf };`) once RE-06 lands; the player-object half is supported by nothing. **With co-op ON the run is not byte-comparable to the oracle by design**, so the SBS gate runs with it OFF and co-op needs its own evidence — what that evidence is remains ❓ open (`docs/plans/enhancements.md` says so rather than inventing a gate). |

## Known local costs, recorded rather than hidden

- **`tools/info.py`, `tools/catalog.py`, `tools/behavior.py` and `tools/go_public.py` are COPIES**,
  because no hoisted engine exists for them in `external/psxport/tools/port/` yet (only
  `re_frontier.py` is hoisted). This is a fifth/sixth copy of each, which is exactly the divergence
  that produced `re_frontier.py`'s four-times-fixed green-over-nothing bug. **Switch them to shims as
  soon as the engines are hoisted.** `behavior.py` arrived with that bug still unfixed anywhere and was
  fixed HERE (`docs/issues/0002-*`); `catalog.py` and `go_public.py` were taken from `vagrant/`, the
  copies where those two were already fixed, so the fixes are carried forward rather than re-imported
  broken.
- **`psxport_smoke` cannot be built from a consumer tree** (framework defect, carried forward from
  vagrant): `external/psxport/cmake/psxport.cmake:237` names `tools/smoke/psxport_smoke.cpp`
  relatively, so with `-DPSXPORT_BUILD_SMOKE=ON` CMake looks for it under THIS repo. The agnosticism
  proof is therefore only runnable from inside the framework repo. One-line fix upstream
  (`${PSXPORT_ROOT}/…`); not made here, because a game repo may not edit the framework.
  `docs/issues/0001-*`.
- **`PSXPORT_ENH` / `cfg_enh()` is off the CVar ladder**, so this port's `x4::enh()` duplicates the
  framework's suppression rule instead of calling it. Deliberate and commented as such in
  `game/core/enhancements.cpp`; the proper fix is upstream (migrate `PSXPORT_ENH` onto the ladder,
  keeping the suppression as an explicit resolve-time hook per the framework's
  `docs/config-migration.md` "Qualification 2") and a game repo may not make it. Hand it to the
  operator.
