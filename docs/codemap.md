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

## Read this before anything else: the honest state, 2026-08-21

The crt0 group, two pad buffers, resident substrate bootstrap, generated registry, and main text range
are measured. `megamanx4_port` builds with Clang and boots through InitHeap into guest `gameMain`; it
currently stalls in stock CD init's VSync/hardware polling because RE-04/RE-11 remain unwired. The
three enhancements still have no implementation.

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
| `external/psxport/` | the PSX-generic framework (shared checkout; verified pin `2b5ef7b5`): MIPS→C recompiler, runtime substrate, GTE/SPU/MDEC/CD/GPU backends, SDK HLE, SBS differential harness, SDL_GPU renderer. Framework fixes land in the workspace dev clone, never as per-game copies. |
| `game/`, `tools/`, `generated/` | this port: the seam, enhancement gates, RE, provisioning, and gitignored recompiled substrate. |
| `external/mmx4/` | an **AGPL-3.0 matching decompilation** of this exact executable (pinned `1922fcd3`, dormant since 2025-08-25) — a read-only REFERENCE, never built or linked here, and **never copied into psxport**. See `docs/references.md` and `LICENSING.md`. |

## Subsystems

| subsystem | where | status | notes |
|---|---|---|---|
| Disc resolution | `tools/resolve_disc.py` | ✅ | One implementation of CLI arg > `$PSXPORT_X4_DISC` > `.env` > a `*.chd` in the repo root; refuses (exit 2) naming all four sources rather than returning empty, and refuses when a configured path does not exist instead of falling through to a different disc. `run.sh`, `extract_exe.py`, `discdump.py` and `verify_decomp_targets.py` all go through it. |
| Disc listing | `tools/discdump.py` | ✅ | Thin wrapper over the framework's own `discdump`, resolved through `$PSXPORT_DIR`. `list` mode added here, because the module inventory had to be enumerated before anything could be said about overlay shape. Refuses (exit 2) when `discdump` is missing, the disc is unresolvable, or a read yields zero entries. |
| Disc → executable provisioning | `tools/extract_exe.py` | ✅ | Extracts `SLUS_005.61` (1,179,648 B) with psxport's own `discdump`, prints the PS-EXE header, and checks the SHA-1 against the value read AT RUN TIME out of `external/mmx4/check.us.txt`. Says explicitly when it CANNOT check (decomp submodule absent) rather than passing quietly. |
| Code / overlay census | `tools/code_scan.py` | ✅ | The three-signal detector behind the overlay finding. Imports the code/data discriminator from `external/psxport/tools/exe_similarity.py` so there is ONE calibrated copy. `--selftest` gates BOTH classes (POSITIVE = 64 KiB at the header entry, ≥95%; NEGATIVE = a media file, ≤2%); `--census` refuses on a zero-match glob. |
| crt0 / boot-group derivation | `tools/verify_crt0.py` | ✅ | Derives the complete group and resident recomp range from the retail header/entry function. The framework-source verdict locates 15/15 mechanisms. `--selftest` is 26/26 locally and 29/29 with the independent Tomba!2 control, including zero-range, binary/config, framework-mechanism, and malformed-input refusals. Runtime boot confirms the plan through InitHeap. |
| Pad-buffer derivation | `tools/verify_pad.py` | ✅ | Uses the matching decomp only to identify the stripped InitPAD target, then scans all 294,400 loaded retail words. It requires exactly one call, evaluates `a0..a3` through the delay slot, and diffs all four arguments plus the actual `GameConfig` bindings: `0x80166D68, 0x22, 0x8012F46C, 0x22`. `--selftest` is 4/4 across a real positive, a mutated immediate, an unwired config, and a removed call. Blind spot: static arguments, not runtime mutation. |
| Decomp-target verification | `tools/verify_decomp_targets.py` | ✅ | Reads mmx4's `target_path:` from its splat config and its expected hash from `check.<variant>.txt` (mmx4 states no `sha1:` in the yaml, unlike the sibling tree this was adapted from). Prints denominators and blind spots every run; refuses on a missing submodule or zero configs; `--selftest` proves it can report a MISMATCH. |
| Licence containment | `tools/check_license_containment.py` | ✅ | Has AGPL material from mmx4 reached `psxport`? Four detection classes with the Sony-SDK vocabulary and the TRACKED generic-vocabulary list (`docs/info/containment-baseline.txt`, 25 names, `--write-baseline` regenerates) subtracted; `--selftest` gates 19 checks in both directions and was proven non-vacuous by reintroducing a real past bug. **It reported clean over ZERO files until 2026-08-12** — an uninitialised submodule directory and a fully git-ignored tree both read as `PASS`, and the baseline came from directories outside this repo so a bare clone FAILED with 27 false hits; both fixed, both now gated, full write-up in `docs/info/instruments/005-*` under "Known failure modes". Blind spot printed on every run: it cannot see paraphrase, renamed identifiers, or struct layouts carried in a head, nor a leak of one of the 25 excluded names. |
| Static recompilation | `game/recomp_seeds.json`, `tools/ensure_recomp.py`, `tools/verify_recomp_bootstrap.py` → `generated/` | 🟡 | Retail emission: 6,192 binary roots → 7,533 functions, `crt0`/`gameMain` present, zero overlays, version 2026-08-12.1. The 2/2 verifier uses the real emitter for a positive and proves an out-of-text seed refusal. Runtime reaches `gameMain` with no recomp miss; future indirect-only paths can still grow the empty explicit seed list empirically. |
| Framework seam — config | `game/core/game_config.cpp` | 🟡 | Compiles. RE-01's crt0 group and RE-06's pad buffers are measured and wired; both shipping bindings are independently diffed against the retail executable. The remaining address groups stay `0` with their frontier step named. |
| Framework seam — hooks | `game/core/game_hooks.cpp` | ⬜ | Compiles. Neutral bodies where "nothing is owned" is the correct semantic; fail-fast `abort()` bodies for every framework path this port has not stood up. `bootInit` refuses rather than dispatching `gameMain == 0`. `frameUpdate`/`drawOTag` are fail-fast **permanently** — see the ➖ rows below. |
| Framework seam — recomp registry | `game/core/recomp_register.cpp` | ✅ | Installs the measured resident generated interface (`main_dispatch`, `rec_func_index`, `g_rec_overlays`, `shard_set_override`); the clean-clone seam retains a loud no-substrate branch. Clang built and linked the real substrate branch. |
| **Enhancement gates** | `game/core/enhancements.{h,cpp}` | 🟡 | **The thing that makes this port what it is.** Three `pc_enh` CVars (`PSXPORT_X4_WIDESCREEN` / `_COOP` / `_FASTWAIT`) on the framework's CVar ladder, and ONE chokepoint `x4::enh()` that force-suppresses all of them under `PSXPORT_ORACLE` / `PSXPORT_SBS` / `PSXPORT_SBS_MODE`. 🟡 because the gates exist and compile while **nothing is gated behind them yet** — the features need RE-07/RE-08/RE-09. X4 is the workspace's first real consumer of `pc_enh`. |
| Process entry | `game/core/main.cpp` | 🟡 | Executes framework bring-up and native CRT0, then dispatches guest `gameMain`. The current runtime frontier is the stock CD-init/VSync hardware wait. |
| Build and C++ verifier | `CMakeLists.txt`, `cmake/megamanx4_port.cmake`, `external/psxport/tools/check_cpp_style.py` | ✅ | Clang builds and links the real port; CTest runs the shared first-party clang-format/1,200-line/clang-tidy gate through `build/compile_commands.json`. Generated and vendored sources remain excluded. |
| Play launcher | `run.sh`, `tools/run.py`, `tools/test_run.py` | ✅ | `run.sh` is a two-line exec wrapper. Python owns sync, provisioning, hash-checked emission, Clang build, CTest, asset path, and native launch. Six injected-host tests cover the full path and tool/provision/emission refusals. Agents do not invoke the user launcher. |
| Registries | `tools/re_frontier.py` (shim), `tools/info.py`, `tools/catalog.py`, `tools/behavior.py` | ✅ | The RE-frontier tracker is a SHIM onto the shared engine at `external/psxport/tools/port/re_frontier.py` — this repo grows no fork of it. The other three are copies (no hoisted engine exists for them yet); that divergence is a known cost, see below. |
| Behaviour map | `docs/behavior-map.md`, `tools/behavior.py` | ✅ | Generated by the tool, three `planned` `pc_enh`/`affect: full` entries with suppression-citing guards. `behavior.py check` is the ONLY automated gate that this port's canon-affecting enhancements stay ORACLE/SBS-suppressed, which is why the copy was FIXED here before use (three fixes — see `docs/info/instruments/003-*` and `docs/issues/0002-*`). |
| Publication audit | `tools/go_public.py` | 🟡 | Copied from `../vagrant/tools/` (the fixed copy: it used to print "RESULT: clean ✓ — ready to publish" over zero blobs scanned). CONFIG tuned here for PSX: `*.chd`/`*.cue`/`*.ecm`/`*.pbp` and `SLUS_005.61` added to the copyright PATH patterns — which is safe there and deliberately NOT in `.gitignore`, where check C would turn them into prose search tokens. |
| Gate on a built binary | — | 🟡 | A bounded software-Vulkan diagnostic proves native CRT0 → InitHeap → guest `gameMain`, then the current CD/VSync stall. A reusable advancement/end-state gate is still absent and is required before claiming a boot milestone beyond that exact trace. |
| Everything about the game itself | — | 🟡 | Boot layout and both InitPAD buffers are measured. CD/HLE now has an observed boot chain and VSync-poll stall but no verified handler contract. The player-object system and wait-state timers are not started. Widescreen has one static source lead — boot `func_8001213C` sets GTE OFX/OFY/H to 160/120/512 — but its later write census and runtime verification are absent. |

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
| Drop-in co-op (P2 spawns as the other hunter) | `pc_enh`, `affect: full` | 🟡 | **RE-07 — the PLAYER-OBJECT SYSTEM**, and this is the step the whole port turns on. RE-06 landed the INPUT half: the retail buffers are measured and bound to psxport's existing two-slot packet writer. No second player object, camera ownership, game-side input route or spawn path exists yet, so this is plumbing rather than playable co-op. **With co-op ON the run is not byte-comparable to the oracle by design**, so the SBS gate runs with it OFF and co-op needs its own evidence — what that evidence is remains ❓ open. |

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
  vagrant): `external/psxport/cmake/psxport.cmake:237` names `external/psxport/tools/smoke/psxport_smoke.cpp`
  relatively, so with `-DPSXPORT_BUILD_SMOKE=ON` CMake looks for it under THIS repo. The agnosticism
  proof is therefore only runnable from inside the framework repo. One-line fix upstream
  (`${PSXPORT_ROOT}/…`); not made here, because a game repo may not edit the framework.
  `docs/issues/0001-*`.
- **`PSXPORT_ENH` / `cfg_enh()` is off the CVar ladder**, so this port's `x4::enh()` duplicates the
  framework's suppression rule instead of calling it. Deliberate and commented as such in
  `game/core/enhancements.cpp`; the proper fix is upstream (migrate `PSXPORT_ENH` onto the ladder,
  keeping the suppression as an explicit resolve-time hook per the framework's
  `external/psxport/docs/config-migration.md` "Qualification 2") and a game repo may not make it. Hand it to the
  operator.
