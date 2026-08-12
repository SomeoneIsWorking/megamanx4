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

## THE STATE OF THIS PORT: nothing is reverse-engineered. Do not read anything else as progress

Created 2026-08-12. There is **no recompiled substrate, no port binary, and no RE'd guest address.**
`game/core/game_config.cpp` is all zeros with each field pointing at its open step in
`docs/re-frontier.md`. If something here looks like it works, check `docs/codemap.md` — the honest
inventory is provisioning, a compiling seam, and the registries.

What DOES build today, and is the gate for a change to the seam:

```sh
git submodule update --init external/psxport external/mmx4                        # once
git -C external/psxport submodule update --init vendor/lucent vendor/beetle-psx    # once, PER PATH
cmake -S . -B build && cmake --build build --target megamanx4_seam -j$(nproc)
```

**The second line is not optional, and neither `--recurse-submodules` nor `sync-submodules.sh`
replaces it.** Initialising `external/psxport` leaves psxport's own `vendor/lucent` empty and
`vendor/beetle-psx/deps/libchdr` absent, and cmake then dies inside the framework; `--recursive` aborts
on beetle-psx's url-less `deps/lightning/gnulib`, and `sync-submodules.sh` prints "all at recorded
gitlinks" over vendors it never reached (`external/psxport/docs/workspace/KNOWN-DEFECT-sync-submodules.md`).
The per-path form sidesteps the url-less path. `CMakeLists.txt` checks both vendors and fails with that
exact command, and `tools/discdump.py` says the same when its build fails.

`megamanx4_seam` is an OBJECT library over `game/core/{game_config,game_hooks,enhancements,main}.cpp`:
it compiles but does not link, which is the strongest check possible before a substrate exists — it
proves this port's `GameConfig`/`GameHooks` still satisfy the pinned framework's seam, and that the
three enhancement CVars compile against the framework's CVar headers. `megamanx4_port` is not
configured at all until `generated/rec_sources.cmake` exists, and CMake says so loudly at configure
time.

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
  `GameHooks::frameUpdate` is fail-fast and stays that way. Marking these ⬜ would put four steps on
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
- **NO CODE OVERLAYS. The boot executable IS the whole engine.** Measured three independent ways over
  all 163 disc files, with a control, plus corroboration from the decomp's overlay-free splat config.
  X4 is structurally the OPPOSITE of Vagrant Story. `GameConfig` needs no overlay load bases and the
  RAM map is static. Full evidence, denominators and blind spots: `docs/codemap.md` and
  `docs/info/claims/`. **The blind spot is stated and it matters: the method sees PLAIN R3000A code, so
  it can assert "no plain code outside the boot exe", NOT "no code".**
- **Per-character data is already split per file** (`PL00_U`/`PL01_U`/`PL02_U.ARC`, and `_X`/`_Z` stage
  and collision variants). That is a lead for co-op, not a finding: it was not verified in code.

Everything else about this game — crt0 layout, the loader, the player-object system, the projection
site, the pad buffers, the wait-state timers — is **unknown**. Do not let a plausible-sounding sentence
in a doc elsewhere stand in for it.

## The rules that bite hardest here

**Never guess a guest address.** An un-RE'd `GameConfig` field stays `0` with a TODO naming the
frontier step. Zero is honest and psxport fails fast on it; a plausible wrong value breaks boot in a
way that reads as a framework bug. Never copy another game's recompiler seeds — a foreign seed landing
inside your text SPLITS a real function at an arbitrary offset, the emit SUCCEEDS, and the recomp is
silently corrupt.

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

## Where the framework source comes from — NEVER edit `external/psxport`

It is a **read-only pinned consumer**. Framework edits happen in the workspace's framework DEV CLONE
(`../psxport`) and nowhere else; `run.sh` re-syncs this submodule to the recorded gitlink, so an edit
made here is liable to be silently reverted mid-gate. Build against in-progress framework work without
touching the submodule:

```sh
cmake -S . -B build -DPSXPORT_DIR=/path/to/psxport      # or: PSXPORT_DIR=... ./run.sh   (user only)
```

`PSXPORT_DIR` defaults to the submodule, so a bare clone of this repo builds standalone — keep it that
way, and never re-spell `external/psxport` at a call site in cmake or in a tool.
