# Mega Man X4 — working rules for THIS repo

A PC-native **enhancement port** of **Mega Man X4 (PS1, USA, `SLUS_005.61` / SLUS-00561)** built on the
[psxport](https://github.com/SomeoneIsWorking/psxport) static-recompilation framework
(`external/psxport`). psxport recompiles the game's MIPS code to C and supplies the PSX platform layer;
this repo supplies the game — the seam, the RE, and the three deliberate enhancements.

**The framework rules are NOT restated here. Read `external/psxport/CLAUDE.md`** — it is the authority
for how a game consumes psxport: the CVar ladder, the seam, `generated/` being sacrosanct, RE-first,
diagnostics through `lucent`, the registries, never editing `external/psxport`, and the standing USER
directive that **`./run.sh` is the user's and agents must never invoke it**. The workspace map is
`external/psxport/docs/workspace/WORKSPACE.md`; the multi-agent protocol is `…/PROTOCOL.md`; the
methodology is `…/docs/porting-a-new-psx-game.md`.

## THE STATE OF THIS PORT: resident substrate boots to the retail task handoff

Created 2026-08-12. RE-01 and RE-06 are verified; RE-02 is a measured static/runtime bootstrap with an
honest remaining gap for future indirect-only targets. The retail executable emits 6,192 binary roots
to 7,533 functions, links `megamanx4_port`, and boots through InitHeap into guest `gameMain`. CD IRQ2
delivery now reaches the measured callback. The current stall is the retail task handoff: task entry
`0x8001D064` is created but never scheduled because psxport's BIOS `ChangeThread` is a no-op (issue
#11). The rejected local synchronous-task bypass did not cross that boundary and has been removed;
the proper fix is shared runtime scheduling. X4 now defaults to the guest `gte` picture path and refuses `native`, because this
enhancement-class port deliberately has no PC-native producers; selecting them produced guaranteed
black independently of the scheduler.
**The framework seam is inherited now:** process-lifetime `x4::X4Runtime` owns title render-path
selection, measured boot dispatch, and override registration. It derives
`LegacyGameRuntimeAdapter` only while generic framework algorithms still consume measured
`GameConfig` facts; `game/core/legacy_game_interface.h` names that debt, and no new behavior or
per-field virtual getter belongs there.
**RE-01, the crt0 boot group, is verified and wired:** `tools/verify_crt0.py --check` derives the
group from `SLUS_005.61`, compares 21 shipping/range facts, and confirms the current framework implements
all 15 required mechanisms. Its 26-case selftest proves both answers; claim C006 and issue #5 record
the now-fixed framework defect that originally blocked this step.
**RE-06 is verified from the retail InitPAD call:** slot 0 is `0x80166D68`, slot 1 is `0x8012F46C`,
and both capacities are `0x22`; `tools/verify_pad.py --check` scans all 294,400 loaded words and diffs
the unique call's four arguments against the `GameConfig` that ships. Every other guest-address group
remains zero with its open step named in `docs/re-frontier.md`.
**RE-08 is static-complete but runtime-partial:** `tools/verify_projection.py --check` scans the same
294,400 words and proves the only OFX/OFY/H writes are the one boot setup chain (160/120/512). A real
widescreen consumer and pixel gate wait on task scheduling and an explicit framework contract for
wide presentation on X4's required guest-render path.

The direct development build/gate is:

```sh
python3 tools/psxport_sync.py --auto                                    # resolve external/psxport (symlink to the shared clone, or a private clone at psxport.pin)
git submodule update --init external/mmx4                              # once (the AGPL reference decomp, not needed to build)
python3 tools/extract_exe.py
python3 tools/ensure_recomp.py
cmake -S . -B build -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build build --target megamanx4_port -j$(nproc)
ctest --test-dir build --output-on-failure
```

The normal CTest gate calls psxport's shared C++ policy checker: every tracked first-party C/C++ file
is checked with this repository's `.clang-format`, the 1,200-line ownership cap is enforced, and
`.clang-tidy` runs against `build/compile_commands.json`. It excludes `external/` and `generated/`;
there is no copied checker and no pre-commit hook. CTest also runs `tools/test_run.py`: the shipping
launcher orchestration lives in executable `tools/run.py`, while `run.sh` is only its stable exec
wrapper. The user launcher opens the window by default; `PSXPORT_NOWINDOW=1` changes only the final
sink to headless and never enables a diagnostic server implicitly.

**`external/psxport` is NOT a submodule any more (2026-08-16)** — it is a symlink to the workspace's
shared framework clone when one exists, or a private clone at this repo's `psxport.pin` on a fresh
machine; `tools/psxport_sync.py --auto` establishes whichever applies. The framework's own nested
vendors (`vendor/lucent`, `vendor/beetle-psx/deps/libchdr`) are the SHARED clone's concern — initialized
once there, never per-port (`--recursive` aborts on beetle-psx's url-less `deps/lightning/gnulib`, and
`sync-submodules.sh` prints "all at recorded gitlinks" over vendors it never reached —
`external/psxport/docs/workspace/KNOWN-DEFECT-sync-submodules.md`). `CMakeLists.txt` fails with a clear
message if they are missing in the shared clone, and `tools/discdump.py` says the same when its build
fails.

`megamanx4_seam` remains the clean-clone compile database for every first-party `game/core/*.cpp` TU.
`tools/ensure_recomp.py` hashes the retail executable, game seed file, and real recompiler sources,
then emits `generated/`; CMake configures `megamanx4_port` only when that manifest exists.

## Start here, every task

```sh
python3 tools/re_frontier.py next            # which RE step is actually ready to work
python3 tools/info.py brief <words>          # what's already proven — and does it still hold?
python3 tools/catalog.py search <symptom>    # has this been hit (or ruled out) before?
python3 tools/behavior.py check              # X4-SPECIFIC: are the pc_enh gates still ORACLE/SBS-suppressed?
```

Believe these over your instinct about what is known. End the task by writing back what you proved,
what you disproved, and any tool you caught lying. `tools/re_frontier.py` is a SHIM onto the shared
engine in `external/psxport/tools/port/`; do not grow a local copy of it.

## THIS PORT IS AN ENHANCEMENT PORT, NOT A NATIVE-ENGINE REBUILD

USER decision, 2026-08-12, verbatim:

> "Mega Man doesn't need native producers or lerp or native depth, it's already 60fps. It just needs
> widescreen patches (still hard work) and loading removals (again hard work). And I want to add co-op
> to it, drop-in, if I'm playing with X for example then second player can spawn as Zero."

The consequence, in framework vocabulary:

- The whole **native-producer / `ProducerScope` / frame-interpolation (`fps60`, lerp) / native-depth**
  apparatus is **➖ not-applicable** here, not ⬜ todo. psxport's hardest constraint — the picture must
  come from game state, and lerp is native too — exists to serve interpolation of a 30fps guest. X4
  already runs at 60. There is no native producer to drive and no native frame loop to stand up;
  the legacy `GameHooks::frameUpdate` is fail-fast and stays that way. Marking these ⬜ would put four steps on
  the roadmap the USER has ruled out.
- All three deliverables are the **`pc_enh` behaviour class with `affect: full`** — they deliberately
  change canon guest state. So the RE target of this port is the **PLAYER-OBJECT SYSTEM**, not the
  renderer, and every one of them must be **force-suppressed under `PSXPORT_ORACLE` / `PSXPORT_SBS` /
  `PSXPORT_SBS_MODE`** so byte-compares stay enhancement-free *by construction*.
- **The SBS oracle is only meaningful with co-op OFF.** A clean compare with co-op ON means the
  suppression fired, not that co-op is correct. Co-op needs its own evidence, and what that evidence
  is remains an open question — see `docs/plans/enhancements.md`, which says so rather than inventing
  a gate.

X4 is the **first real consumer of `pc_enh` in the workspace** (`cfg_enh()` has zero call sites
anywhere), and `cfg_enh` is env-only and off the CVar ladder. This port therefore declares its own
CVars and routes **every read through one chokepoint**, `x4::enh()` in `game/core/enhancements.cpp`.
Calling `.get()` at a feature call site is the bug that chokepoint exists to prevent. Knob registry:
`docs/config.md`. Divergence ledger: `docs/behavior-map.md`, gated by `tools/behavior.py check`.

## Loading removals are TWO different jobs. Do not conflate them, and do not quote one number for both

- **Job A — raw I/O latency: already largely gone BY CONSTRUCTION.** psxport converts CD/file I/O to
  PC-native SYNCHRONOUS under the FAIL-FAST rule. There is nothing to *build* here; there is something
  to *measure*.
- **Job B — the game's OWN scripted wait states, fade ramps and frame-count timers.** No amount of I/O
  speed touches these. This is a guest-state change (`pc_enh`, `affect: full`) and it needs `RE-09`.

A single "load time" figure that mixes the two is unusable. Estimate them separately.

## The AGPL firewall — the highest-cost mistake available in this tree

`external/mmx4` ([sozud/mmx4](https://github.com/sozud/mmx4), **AGPL-3.0**) is a matching decomp of
this exact executable. Licensing is not a constraint on THIS repo (USER, 2026-08-12) — it may be used
for code **and** ideas, and this repo is AGPL-3.0-or-later (`LICENSE`, `LICENSING.md`) because of it.

**AGPL-derived code stays inside THIS repo and NEVER enters `psxport`.** The framework is vendored by
five ports, so copyleft landing there pulls Tomba!2, Spyro, Spider-Man and Vagrant Story in with it. A
framework-shaped insight discovered while reading mmx4 must be **re-derived and described, not
transplanted**; if a co-op change needs a framework hook, add a *generic* seam upstream and keep the
X4-specific body here. `tools/check_license_containment.py` is the automated half of that rule.

Two more facts about the supply, not about this port:

- `external/mmx4/include/psy-q-4.0/` is **Sony's SDK, © Sony, All Rights Reserved** — not the decomp's
  to relicense and not ours to copy. Read it like a PDF of the manual. psxport has no PSY-Q header
  story by design (address-keyed HLE instead), so there is never a legitimate reason to lift one.
- mmx4 appears **DORMANT** (last push 2025-08-25, pin `1922fcd3`) with an **18.5% upper bound on
  matched code**. It is a partial supply. Its percentage is `objdiff` object identity; this port's axis
  is SBS byte-exact RAM parity. Neither implies the other, and quoting one as evidence about the other
  is how a port looks finished while nothing is gated.

Do not `--recurse-submodules` this tree: mmx4 declares three nested submodules of its own
(`tools/{maspsx,psximager,asm-differ}`) that are its *build* toolchain, and we never build it.
`git submodule update --init external/mmx4` is the correct fetch.

## A borrowed address is a HYPOTHESIS until measured against these bytes

Where a reference and a measurement disagree, **the measurement wins.** Nothing in `game_config.cpp`
is filled in from the decomp, and nothing should be without the disassembly line that justifies it
pasted alongside (the shape `spider1/game/core/game_config.cpp` uses). This repo has a *tempting*
supply of addresses sitting in `external/mmx4`, which is precisely why the rule is stated twice.

## Measured X4 facts (this repo, 2026-08-12). Anything not here is unknown

- **Extracted `SLUS_005.61`**: 1,179,648 bytes, SHA-1
  `213733031136d095ca275d6957695aa25011cfa5` — the same hash mmx4's `check.us.txt` declares for its
  own byte-exact build target, so its symbol addresses are OUR addresses with no translation.
- **`SYSTEM.CNF`**: `BOOT = cdrom:\SLUS_005.61;1`, `TCB = 4`, `EVENT = 16`, `STACK = 801FFF00`. One
  boot executable, no boot stub — psxport's stub stage is unused.
- **The crt0 at `pc0 = 0x800DAE8C`, disassembled and symbolically executed to its `break`** (RE-01,
  claim C005, `tools/verify_crt0.py`): `.bss` clear `[0x8012F418, 0x80175F38)` = `0x46B20`; `sp = fp =
  0x80200000` from `mem[0x800DAF3C]` with **no bias**; heap `0x80175F3C` size `0x820C8` (532,680 B) from
  `stackTop - mem[0x8011CB74] - maskedBase`, handed to **BIOS `A(39h) InitHeap`** at `0x800EDCDC` in
  `a0`/`a1`; `gp = 0x8012F418`; game-main `0x80012024`. **This crt0 stores the heap base/size in NO
  global** — the function's only absolute store is `sw ra` to `0x8012F418`. The 532 KB heap is the
  measured premise under RE-04: `PL00_U.ARC` (796,672 B) cannot be loaded whole.
- **NO CODE OVERLAYS. The boot executable IS the whole engine.** Measured three independent ways over
  all 163 disc files, with a control, plus corroboration from the decomp's overlay-free splat config.
  X4 is structurally the OPPOSITE of Vagrant Story. `GameConfig` needs no overlay load bases and the
  RAM map is static. Full evidence, denominators and blind spots: `docs/codemap.md` and
  `docs/info/claims/`. **The blind spot is stated and it matters: the method sees PLAIN R3000A code, so
  it can assert "no plain code outside the boot exe", NOT "no code".**
- **Per-character data is already split per file** (`PL00_U`/`PL01_U`/`PL02_U.ARC`, and `_X`/`_Z` stage
  and collision variants). That is a lead for co-op, not a finding: it was not verified in code.
- **The two libpad buffers are measured and wired** (RE-06): the retail executable's unique InitPAD
  call at `0x80012194` passes `0x80166D68, 0x22, 0x8012F46C, 0x22`. This completes only the host's
  second-controller packet destination; it says nothing about a second player object.

Everything else about this game — the loader, the player-object system, the projection site and the
wait-state timers — is **unknown**. Do not let a plausible-sounding sentence elsewhere stand in for it.

## The rules that bite hardest here

**Never guess a guest address.** While the compatibility adapter exists, an un-RE'd `GameConfig`
field stays `0` with a TODO naming the frontier step. Zero is honest and psxport fails fast on it; a plausible wrong value breaks boot in a
way that reads as a framework bug. Never copy another game's recompiler seeds — a foreign seed landing
inside your text SPLITS a real function at an arbitrary offset, the emit SUCCEEDS, and the recomp is
silently corrupt.

**`X4Runtime` is the title authority.** `main.cpp` constructs and installs one process-lifetime
instance; runtime behavior moves there through virtual overrides, not new `GameHooks` callbacks.
`GameConfig`/`GameHooks` remain private measurement compatibility tables referenced only by
`x4::legacy::{measuredConfig,compatibilityHooks}`. Delete their fields as psxport gains narrow typed fact groups; do not
replace the bag with one virtual getter per integer.

**Work the step `re_frontier.py next` names, not a downstream one.** The cardinal sin on a port is
faking a step's output before its RE is done; it makes a broken port look finished.

**Provision from your own disc; commit nothing derived from it.** Resolution order (one
implementation, `tools/resolve_disc.py`): CLI arg > `$PSXPORT_X4_DISC` > `.env` > a `*.chd` in the repo
root. `.env` is gitignored because the path is machine-specific; `.env.example` is the template.
`python3 tools/extract_exe.py` extracts and identity-checks. `tools/go_public.py` audits the full
history for disc images, extracted executables and `/home/<user>` paths — run it before this repo is
ever published.

**Everything transient goes in the gitignored `scratch/`, split by kind** (`scratch/bin/megamanx4/`,
`scratch/raw/`, `scratch/logs/`, `scratch/saves/`). **Never `/tmp`** — a small RAM-backed tmpfs on this
machine; diagnose "disk quota exceeded" with `quota -s`, not `df`.

**A diagnostic that can print nothing is lying.** Before writing a check, write what its NEGATIVE
prints: it carries its denominator and its blind spots. Refuse (non-zero) rather than return empty on
a missing corpus. Every tool here ships a `--selftest` that feeds one case which MUST pass and one
which MUST fail.

## Where the framework source comes from — `external/psxport` is the shared tree

`external/psxport` is **not a submodule** (2026-08-16): it is a SYMLINK to the workspace's shared
framework clone (`$PSX/psxport`) when one exists, or a private clone at this repo's `psxport.pin` on a
fresh machine. `tools/psxport_sync.py --auto` (called by `run.sh`) establishes whichever applies. A
framework edit made through either path is the SAME directory, live in every port at once — commit and
push framework work in `psxport/`, never here. `psxport.pin` records the framework commit this game
was built and VERIFIED against; `tools/psxport_sync.py --bump` updates it, and the gate's `--check`
fails when the framework you built against is not the recorded one.

Build against in-progress framework work:

```sh
cmake -S . -B build -DPSXPORT_DIR=/path/to/psxport      # or just ./run.sh — it resolves external/psxport
```

`PSXPORT_DIR` defaults to `external/psxport`, so a bare clone of this repo builds standalone — keep it
that way, and never re-spell `external/psxport` at a call site in cmake or in a tool.
