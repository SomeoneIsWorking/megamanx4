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

## Read this before anything else: the honest state, 2026-08-24

The crt0 group, two pad buffers, resident substrate bootstrap, generated registry, and main text range
are measured. `megamanx4_port` builds with Clang and boots through InitHeap into guest `gameMain`.
RE-11 has a retail-derived VBlank route, and CD interrupt delivery reaches its measured callback. The
live boundary has moved through the retail task handoff: task entry `0x8001D064` runs through
X4Runtime's per-Core BIOS thread service beneath the untouched retail scheduler. The discarded local
task bypass never crossed that boundary and remains removed. The executable defaults to the only honest shipping picture for
this enhancement port — guest `gte` — and refuses the empty native-producer path. RE-08's complete
projection-writer census is measured. A title-owned projection controller now consumes the typed
guest-wide candidate at the two measured retail publications; widescreen pixels remain unverified.
The direct derived runtime now also treats X4 as an already-60fps, widescreen-only rendering target: it
rejects the framework's synthetic interpolation tier after persisted settings load, while leaving the
retail game's own cadence untouched while driving the typed widescreen policy.
Against the recorded neutral presentation service, the VBlank route uses the neutral
capture/present/pace fence, `X4Runtime` constructs no temporal decorator, and
`tools/verify_no_temporal_dependency.py` rejects operational Fps60 products/calls/includes from the
shipping title sources and checks the linked binary. Direct inheritance removed the complete Fps60
implementation, and recorded pin 9c2e3f1c includes the split of the remaining temporal-only helper translation units;
full Clang CTest proves the shipping link is clean. The matched-frame 4:3/16:9 gate remains open.
RE-10 now has its first selected AGPL-decomp-seeded native body: the title state-0 white-logo quad
initializer at `0x800D6F94`. Retail-byte and hermetic gates are complete, and Clang links the
retained-super ownership triple. An exact-pin serialized real-disc run reports mirror equality. Its
sampled presents were a stable dark title field, so visible composition is not claimed. A deliberate
live mismatch discriminator remains mandatory.

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
| `external/psxport/` | the PSX-generic framework (shared checkout; recorded pin `75456947`): MIPS→C recompiler, runtime substrate, GTE/SPU/MDEC/CD/GPU backends, SDK HLE, SBS differential harness, SDL_GPU renderer. Framework fixes land in the workspace dev clone, never as per-game copies. |
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
| CD interrupt derivation | `tools/verify_cd_irq.py`, `game/recomp_seeds.json` | ✅ | Six retail groups prove the priority-1 element at `0x8013BBF8` is pad/VBlank-only, HookEntryInt resumes `0x800E5194`, trapIntr scans 11 sources from table `0x8011CB98`, and CD uses slot 2 / callback `0x800E7944` with ready/sync buffers `0x8013BA80` / `0x8013BA78`. The 6/6 selftest rejects wrong verifier polarity, a missing control-flow edge, missing or duplicated re-entry ownership, and the wrong callback slot. Live FNTRACE reaches the callback with zero ABI violations and I_STAT is acknowledged. Blind spot: the verifier does not execute delivery; the bounded runtime is separate evidence. |
| Decomp-target verification | `tools/verify_decomp_targets.py` | ✅ | Reads mmx4's `target_path:` from its splat config and its expected hash from `check.<variant>.txt` (mmx4 states no `sha1:` in the yaml, unlike the sibling tree this was adapted from). Prints denominators and blind spots every run; refuses on a missing submodule or zero configs; `--selftest` proves it can report a MISMATCH. |
| Licence containment | `tools/check_license_containment.py` | ✅ | Has AGPL material from mmx4 reached `psxport`? Four detection classes with the Sony-SDK vocabulary and the TRACKED generic-vocabulary list (`docs/info/containment-baseline.txt`, 25 names, `--write-baseline` regenerates) subtracted; `--selftest` gates 19 checks in both directions and was proven non-vacuous by reintroducing a real past bug. **It reported clean over ZERO files until 2026-08-12** — an uninitialised submodule directory and a fully git-ignored tree both read as `PASS`, and the baseline came from directories outside this repo so a bare clone FAILED with 27 false hits; both fixed, both now gated, full write-up in `docs/info/instruments/005-*` under "Known failure modes". Blind spot printed on every run: it cannot see paraphrase, renamed identifiers, or struct layouts carried in a head, nor a leak of one of the 25 excluded names. |
| Static recompilation | `game/recomp_seeds.json`, `tools/ensure_recomp.py`, `tools/verify_recomp_bootstrap.py` → `generated/` | 🟡 | Retail emission: 6,193 binary roots → 7,534 functions, `crt0`/`gameMain` plus measured mid-function continuation `0x800E5194` present, zero overlays, version 2026-08-12.1. The bootstrap verifier still proves real emission and out-of-text refusal; the CD verifier requires `0x800E5194` exactly once in `main_reentry` and refuses redundant `main` ownership. Runtime dispatches that continuation through HookEntryInt. Future indirect targets remain empirical. |
| Framework seam — measured legacy facts | `game/core/game_config.cpp`, `game/core/legacy_game_interface.h` | 🟡 | Explicit compatibility debt behind `X4Runtime`, not the title API. RE-01's crt0 group and RE-06's pad buffers are measured and wired; both shipping bindings are independently diffed against the retail executable. Exact PlatformHle windows admit RE-11's VBlank wait and RE-04's contiguous OpenTh/CloseTh/ChangeTh thunks only. Generic synchronous-CD HLE entries remain zero because the retail route is verified. Next: delete groups as psxport adds narrow typed fact interfaces. |
| Framework seam — legacy callbacks | `game/core/game_hooks.cpp`, `game/core/legacy_game_interface.h` | 🟡 | Only unmigrated neutral/fail-fast compatibility callbacks remain. Boot and override slots are null and gated by `mmx4_runtime_test`; new behavior belongs on `X4Runtime`. `frameUpdate`/`drawOTag` remain fail-fast permanently — see the ➖ rows below. |
| Framework seam — recomp registry | `game/core/recomp_register.cpp` | ✅ | Installs the measured resident generated interface (`main_dispatch`, `rec_func_index`, `g_rec_overlays`, `shard_set_override`); the clean-clone seam retains a loud no-substrate branch. This remains the one adapter allowed to name generated symbols and now registers reversible super-call wrappers at retail SetGeomOffset `0x800E90C8` and SetDefDrawEnv `0x800E9354`. Clang built and linked the real substrate branch. |
| Direct title runtime | `game/core/x4_runtime.{h,cpp}`, `game/core/x4_context.{h,cpp}` → `x4::X4Runtime` | 🟡 | Process-lifetime `GameRuntime` authority plus one per-Core title context. It owns typed executable-image facts, render-path policy, measured guest-main dispatch, override installation, BIOS threads, and the guest-wide policy/controller. It explicitly answers `guestVramIsPicture=false`: X4 claims its GTE primitive stream, while psxport `75456947` separately preserves the initialized PC composite across the title's alternating framebuffer pages. Exact frame 180 changed from 0/691200 to 29921/691200 non-black and visibly renders the Mega Man X logo. It uses the neutral temporal default, defaults widescreen to 16:9 through the suppression chokepoint, defaults to `gte`, permits diagnostic `psx`, and refuses `native` or synthetic FPS60. Legacy config/hooks remain compatibility views only; the adapter and its Fps60 factory are not linked. Full Clang CTest 11/11 includes clean source and shipping-binary temporal dependency gates. |
| BIOS cooperative threads | `game/core/bios_threads.{h,cpp}` | ✅ | Per-Core service beneath untouched retail func_80012600. OpenTh owns the four SYSTEM.CNF TCBs and captures entry/SP/GP; ChangeTh uses strict-ping-pong fibers to preserve task and main C stacks; CloseTh releases/reuses a TCB. `tools/verify_threads.py` proves the retail ABI/record graph with 6/6 controls, `mmx4_runtime_test` proves both context-switch answers, and a real-disc trace reaches 0x8001D064 through handle 0xFF000001. |
| **Enhancement gates** | `game/core/enhancements.{h,cpp}` | 🟡 | Three `pc_enh` CVars (`PSXPORT_X4_WIDESCREEN` / `_COOP` / `_FASTWAIT`) on the framework CVar ladder, and one `x4::enh()` chokepoint that suppresses all under ORACLE/SBS. Widescreen and fast loading have real consumers and default on; co-op remains declared but unimplemented. Pixel and real-disc loading verification keep the overall row partial. |
| Widescreen projection controller | `game/core/widescreen_controller.{h,cpp}`, `game/core/recomp_register.cpp` | 🔬 | Per-Core controller latches the typed framework plan at the sole retail SetGeomOffset and changes only OFX before the untouched body; after the untouched SetDefDrawEnv it changes only RECT.w. The focused falsifier proves 4:3 identity 160/320, 16:9 OFX/width 214/428, unchanged OFY/H/x/y/h/UV/color/order, and oracle suppression. Full Clang link passes; real-disc startup A/B reaches the wrapper and logs the same 160/320 vs 214/428 plans. Integrated title-screen pixels remain the completion gate. |
| VBlank synchronization | `game/core/vsync_sync.{h,cpp}`, `tools/verify_vsync.py` | 🔬 | Retail bytes prove VSync's two calls to exact helper [0x800E4EF8,0x800E4F94), counter 0x8011DC50, IRQ-0 handler 0x800E56FC, and its eight-slot callback table at 0x8011DC30. The title owns only the helper, dispatches the current class-0 handler so the libsnd chain remains live, services pad and SPU once per field, and calls the recorded neutral presenter. The verifier is 6 groups / selftest 8/8, including raw-present, hardcoded-handler, missing-pad, and missing-SPU negatives. |
| Process entry | `game/core/main.cpp` | 🟡 | Installs one process-lifetime `X4Runtime`, executes framework bring-up and native CRT0, then dispatches guest `gameMain` through the derived owner. Recorded pin 9c2e3f1c reaches the task/archive path without FNTRACE: a bounded 20-second real-disc run completed requests 64, 65, 113, and 51 and remained live until timeout. Issue #14 is falsified for the current build; its older attribution remains historically unknown. |
| Title-quad native ownership (RE-10) | `game/core/title_quad.{h,cpp}`, `tools/re_title_quad.py`, `tests/test_x4_title_quad.cpp` | 🔬 | The first selected matching-decomp C body is the title state-0 initializer `0x800D6F94`. The verifier reuses the measured title-composition path, proves dispatch `0x8010FDD0[0]`, matches all 49 retail instructions, diffs 17 shipping facts, and rejects three mutations; the hermetic test pins 23 object/register results. `X4Runtime` installs `{native, gen_func_800D6F94}` through the retained-super registry and Clang links it. An exact-`dbdb2baf` real-disc run reaches it and reports `[mirror-verify] 0x800D6F94 OK (pass #1)`. Its frames 120, 600, 1000, and 1100..1600 all sampled the same dark title field, so visible composition is not claimed. Still required: a deliberate live native mismatch control. This owns one initializer only and does not create a native renderer, interpolation or depth. |
| Player-object system (RE-07) | `docs/re-player-object.md`, `game/core/player_object.h`, `tests/test_x4_player_object.cpp` | 🔬 | MEASURED 2026-08-24 against both sources: player struct g_Player 0x801418C8 (0xE4, offsets pinned incl. position halves +0xA/+0xE, character +2), camera = 3 layer structs @ 0x801419B0 stride 0x54 with scroll x/y +0xA/+0xE and mode-table follow via func_80027850/table 0x800F3134, input route func_80012328 → P1 held/prev/edge 0x80166C08/C0A/C0C plus a decoded-but-unconsumed P2 trio 0x80166D50/D52/D54, spawn path func_80035240 from engine character byte 0x80172203 with init/reset/update pool management. The lens is READ-ONLY — no guest write, no override; ctest `x4_player_object` pins it hermetically with planted-state positives and non-aliasing negatives. Remaining UNKNOWNs live in the doc; co-op evidence question unchanged. |
| Audio path | `game/core/vsync_sync.cpp` (field seam), `game/core/main.cpp` (spu_init + sink) | 🔬 | MEASURED 2026-08-24, two stacked causes fixed: (1) `spu_update()` had ZERO call sites on the guest-driven path — the Beetle mixer never advanced (WAV instrument: 0 bytes written); the field seam now advances `spu_audio.frame()` once per delivered field (Tomba!2 does the same from its PC-driven frame hook). (2) The mixer then rendered 26.4M silent stereo frames: libsnd's SS tick never ran. RE chain: `SsInit` registers tick handler 0x800DB544 via `InterruptCallback(4,…)` and `SsStart` replaces the SetInterrupt class-0 slot (table `0x8011CB98`, FUN_800E53F0) with 0x800DD7FC, which chains the previous VBlank walk AND the sequencer tick; tick mode is SS_TICKVSYNC at runtime (rate global 0x80173C88 = 0x3C). The seam now delivers the class-0 slot's CURRENT occupant instead of the hardcoded boot handler. Result: 269,452 KON writes; WAV peak 24574, 42.78% non-zero, RMS 2233 over 15.7M analyzed frames — headless, no audio device opened. Verified by sample production only; audible playback awaits the user's ears. |
| Input bindings | framework `pad_input.cpp` via the field seam | 🔬 | MEASURED 2026-08-24: `Pad::serviceFrame()` (host keyboard/gamepad → packet → both InitPAD buffers) lived only in Tomba!2's PC-driven frame loop, so the guest-driven X4 path never ran it and no binding reached the game. The field seam now services the pad once per delivered field — the hardware per-VBlank SIO cadence. End-to-end proof: forced START → router FUN_80012328 stores held/prev/edge 0x0800 (PADstart, PSY-Q convention) at P1 0x80166C08/C0A/C0C. A diagnostic opt-in proved the measured P2 trio can decode slot 1, but shipping leaves slot 1 absent because the host currently owns only one finalized mask; mirroring P1 would not be real second-controller support. Keyboard map = the framework's standard (WASD/arrows, K/J/I/L, Q/E, 1/3 + SDL gamepads). Distinct per-slot host masks remain future co-op work. |
| Loading-screen removal (RE-09 job B) | `game/core/fast_wait.{h,cpp}`, `game/core/recomp_register.cpp` | 🔬 | Retail direct/archive issuers 0x80013890/0x80013AD8 and callbacks 0x80013A20/0x80013E68 are measured from generated SLUS_005.61. With fast loading enabled, each issuer runs its generated setup once, then a per-Core owner reads the table-derived LBA/length, feeds raw sectors from FIFO offset 12 through the generated callback, pumps archive consumer 0x80014780 after each callback, and returns only at state 2. The pump ordering is required: producers 0x800142BC/0x80014514 reject seven outstanding records, retail drains once per main loop, and the queue is a measured 16-slot ring. The untouched waits execute zero yield/draw iterations and loading-presentation wait 0x80013530 is omitted. PsyQ's nested VSync(-1) GPU-timeout query super-calls the pure retail counter branch; every other unexpected scoped mode fails closed (#21). Clang build/lint and focused production-leaf tests pass. A bounded uninstrumented real-disc run against clean psxport 9c2e3f1c completed archive requests 64/113/51 (49/154/3 sectors) and direct requests 65/80 (6/4 sectors), then remained live until the deliberate timeout; exact destination-byte comparison and a presented-frame capture remain open. C025 records why the discarded presentation-withholding evidence is invalid. |
| Build and C++ verifier | `CMakeLists.txt`, `cmake/megamanx4_port.cmake`, `external/psxport/tools/check_cpp_style.py`, `tools/verify_no_temporal_dependency.py` | ✅ | Clang builds and links the real port; full CTest passes 13/13 with clang-format/structure/clang-tidy. The dependency gate rejects source-level temporal use and linked Fps60/helper products, with both synthetic controls and the pre-migration binary as its opposite answer. Its source half remains available to clean clones without `generated/`; the binary half is registered only when the shipping target exists (issue #20). Generated and vendored sources remain excluded. |
| Focused C++ tests | `tests/test_x4_runtime.cpp`, `tests/test_x4_player_object.cpp`, `tests/test_x4_title_quad.cpp` | ✅ | Hermetically proves derived runtime/context ownership, exact BIOS-thread behavior, no temporal product, widescreen policy suppression, production projection/draw-environment transformations, and fast-loading leaf scope/return/cursor/presentation semantics with opposite controls. The player-object test gates RE-07's typed lens; the title-quad test gates RE-10's first selected native body's object and register contract. CTest builds them with Clang against the real substrate closure. Hermetic tests do not replace real-disc end-to-end load or mirror gates. |
| Play launcher | `run.sh`, `bootstrap.py`, `tools/run.py`, `tools/test_run.py` | ✅ | `run.sh` is a slim frozen-uv exec wrapper. Python owns sync, provisioning, hash-checked emission, an isolated `scratch/build/player` tree with `BUILD_TESTING=OFF`, asset path, and native launch; it has no CTest path or option and cannot perturb the maintainer build tree. Thirteen injected-host tests cover the full path and tool/provision/emission refusals, including the no-CTest contract; the default opens a window, while `PSXPORT_NOWINDOW=1` selects only the headless final sink. Agents do not invoke the user launcher. |
| Registries | `tools/re_frontier.py` (shim), `tools/info.py`, `tools/catalog.py`, `tools/behavior.py` | ✅ | The RE-frontier tracker is a SHIM onto the shared engine at `external/psxport/tools/port/re_frontier.py` — this repo grows no fork of it. The other three are copies (no hoisted engine exists for them yet); that divergence is a known cost, see below. |
| Behaviour map | `docs/behavior-map.md`, `tools/behavior.py` | ✅ | Generated by the tool, three `planned` `pc_enh`/`affect: full` entries with suppression-citing guards. `behavior.py check` is the ONLY automated gate that this port's canon-affecting enhancements stay ORACLE/SBS-suppressed, which is why the copy was FIXED here before use (three fixes — see `docs/info/instruments/003-*` and `docs/issues/0002-*`). |
| Publication audit | `tools/go_public.py` | 🟡 | Copied from `../vagrant/tools/` (the fixed copy: it used to print "RESULT: clean ✓ — ready to publish" over zero blobs scanned). CONFIG tuned here for PSX: `*.chd`/`*.cue`/`*.ecm`/`*.pbp` and `SLUS_005.61` added to the copyright PATH patterns — which is safe there and deliberately NOT in `.gitignore`, where check C would turn them into prose search tokens. |
| Gate on a built binary | — | 🟡 | A bounded headless Vulkan diagnostic proves native CRT0 → InitHeap → guest `gameMain`, CD IRQ result state, OpenTh 0xFF000001, untouched retail scheduler selection, entry 0x8001D064, and the first archive request with zero traced ABI violations. A RAM/disc comparison proves all 2048 LBA223 payload bytes. On recorded pin 9c2e3f1c, an uninstrumented 20-second run completes synchronous requests 64, 65, 113, and 51 and remains live until the intentional timeout; issue #14 is resolved for the current build. An explicit `native` selection refuses with exit 2. |
| Everything about the game itself | — | 🟡 | Boot layout, both InitPAD buffers, VBlank wait/IRQ/frame fence, CD interrupt/callback/result state, BIOS cooperative threads, required guest render path, the first front-end archive request, and the complete GTE projection-writer census are measured. RE-07's player struct/camera/input/spawn pillars are measured (`docs/re-player-object.md`, claim C022). The shared CD elapsed-time cause and the Gte two-page composite clear are resolved in recorded pin `75456947`; issue #22 and claim C030 carry the pixel evidence. Runtime pixel/culling/2D-layout classification remains downstream; issue #19 owns the measured fixed-320 title composition failure. |

## What this port deliberately does NOT build — ➖, with the USER decision cited

USER, 2026-08-12: *"Mega Man doesn't need native producers or lerp or native depth, it's already 60fps."*
USER, 2026-08-22: X4 is one of the already-60fps titles that needs widescreen only; it does not need
lerp or anything lerp needs.
These rows are ➖ **not-applicable**, not ⬜ not-started. Marking them ⬜ would put four steps on the
roadmap the USER has ruled out of scope; marking them ➖ without the citation would read as an
unexplained gap.

| subsystem | status | why |
|---|---|---|
| Native producers / `ProducerScope` | ➖ | There is no native renderer here, so nothing produces a picture from game state. The guest draws. |
| Frame interpolation (`fps60`, lerp) | ➖ | The behavior is out of scope because the game already runs at 60fps. X4 constructs no temporal product and uses the neutral frame fence; direct runtime inheritance removes the concrete Fps60 implementation. The binary gate still rejects two linked temporal helper groups until psxport splits their translation-unit ownership (#18). |
| Native depth / obj_depth compositing | ➖ | Same: no native renderer to composite. |
| Native frame loop / `PcScheduler` | ➖ | The guest's own loop runs on the substrate. `GameHooks::frameUpdate` and `drawOTag` are fail-fast permanently, and `GameConfig`'s OT/packet-pool and scheduler groups have no reader by design. |
| Overlay load bases / router slots | ➖ | **Measured:** this disc has no code overlays. See the structural fact above, and its blind spot. |

## What this port DOES build — the actual work, all ⬜, with its RE dependency

| deliverable | class | status | blocked on |
|---|---|---|---|
| Widescreen | `pc_enh`, `affect: full` | 🔬 | **RE-08** — the retail writer census is complete and the typed title consumer is implemented without stretch/native/depth/lerp. Static/unit gates prove its exact guest-state changes. Fresh matched-frame 4:3 and 16:9 title/gameplay captures must prove newly composed margins and unchanged central scale; the known translated title image is not acceptable, and no blanket 2D offset may mask it. |
| Scripted-wait / fade collapse | `pc_enh`, `affect: full` | 🔬 | **RE-09** — measured direct/archive load issuers now own one synchronous operation, so the retail CD waits observe terminal state without yielding and the loading-presentation task is omitted. This deliberately is not byte-exact. Still open: a real-disc end-to-end load gate and the game's OTHER scripted waits/fade ramps beyond CD loading. |
| Drop-in co-op (P2 spawns as the other hunter) | `pc_enh`, `affect: full` | 🟡 | **RE-07 — the PLAYER-OBJECT SYSTEM**, and this is the step the whole port turns on. RE-06 landed the INPUT half: the retail buffers are measured and bound to psxport's existing two-slot packet writer. No second player object, camera ownership, game-side input route or spawn path exists yet, so this is plumbing rather than playable co-op. **With co-op ON the run is not byte-comparable to the oracle by design**, so the SBS gate runs with it OFF and co-op needs its own evidence — what that evidence is remains ❓ open. |

## Known local costs, recorded rather than hidden

- **The direct runtime is only the next migration slice.** `X4Runtime` owns behavior and the typed
  program image, but generic
  crt0, overlay/range, pad, platform-HLE, disc, and render-memory algorithms still read the bounded
  legacy facts. `GuestProgramImage` has moved; the next shared slices are the remaining
  consumer-owned groups. Delete corresponding `GameConfig` fields with each extraction. Do not add
  another bag, one virtual getter per field, or a second render-path authority.
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
