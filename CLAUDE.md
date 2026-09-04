# Mega Man X4 — working rules for THIS repo

A PC-native **enhancement port** of **Mega Man X4 (PS1, USA, `SLUS_005.61` / SLUS-00561)** built on the
[psxport](https://github.com/SomeoneIsWorking/psxport) native/Lightrec runtime framework
(`external/psxport`). The authenticated executable remains runtime data: native overrides own
selected verified functions, Lightrec dynamically executes every other guest instruction, and
psxport supplies the PSX platform layer. This repo supplies the title seam, RE, native ownership,
and the three deliberate enhancements.

**The framework rules are NOT restated here. Read `external/psxport/CLAUDE.md`** — it is the authority
for how a game consumes psxport: the CVar ladder, the seam, RE-first, diagnostics through `lucent`,
the registries, never editing `external/psxport`, and the standing USER
directive that **`./run.sh` is the user's and agents must never invoke it**. The workspace map is
`external/psxport/docs/workspace/WORKSPACE.md`; the multi-agent protocol is `…/PROTOCOL.md`.

## Product execution contract

The gameplay product contains a per-Core pinned Lightrec executor and image-and-address-keyed native
overrides. A native override's original call suppresses only that override for one call and executes
the original guest body through Lightrec. psxport owns machine-state synchronization, HLE/device
callbacks, executable-memory and override invalidation, and bounded exits; Lightrec owns its code
cache and executable memory.

Guest execution always enters through the Lightrec owner and the dynarec is the gameplay default.
Lightrec may automatically interpret only a bounded block that it refuses to compile because the
block is unsupported, unsafe to fetch, self-modifying, or failed compilation. That fallback is a
backend detail, never a player mode: every reason and instruction is counted, a release threshold
must fail loudly, and forced interpretation remains diagnostic/test-only. Provisioning validates
runtime data and never emits executable code.

The first implementation discriminator is the existing 4,000-field front-end/movie frontier with
nonzero Lightrec execution and runtime-authenticated VSync interception. Movie bodies remain original
guest code; they are not rewritten to manufacture suspension or progress. The same shipping
dispatcher must prove a native override plus its scoped original call, and product inspection must
prove there is no selectable interpreter gameplay engine. Next, drive representative interactive gameplay and verify rendering,
input, audio, timing, relevant invalidation, and released-host performance.

## Measured native evidence baseline: the prior product reached the retail task handoff

Created 2026-08-12. RE-01 and RE-06 are verified; a historical product run provides a measured
bootstrap baseline. It booted through InitHeap into guest `gameMain`. CD IRQ2
delivery reaches the measured callback, and the retail scheduler now transfers through distinct BIOS
TCB handles into task entry `0x8001D064`. `X4Runtime` owns a per-Core BIOS-thread service beneath the
untouched retail scheduler: OpenTh captures entry/SP/GP, ChangeTh preserves both C stacks across
cooperative yields, and CloseTh releases the TCB. The rejected synchronous-task bypass remains removed.
The recorded 9c2e3f1c framework includes 7bd24f2b's field-aware CD time and advances through `0x800128B8`, Capcom-logo
decode, task `0x8001DAF8`, and a coherent title screen. X4
declares the guest `gte` picture as its only player renderer, because this enhancement-class port
deliberately has no PC-native producers. The shared capability resolver removes Native from the menu
and warns before falling back to GTE for an explicit diagnostic request; it never selects the
guaranteed-black producer path.
**The native field seam is the port's heartbeat.** The shared frame shell calls
`X4FrameDriver::stepFrame()` once per field; the driver replaces only retail `VSync(0)` and preserves
the remaining `0x80012024` body in its measured order. EVERY per-field host service lives in
`x4::vsync::deliverField` (`game/core/vsync_sync.cpp`): the retail IRQ-0 delivery (the
SetInterrupt class-0 slot's CURRENT occupant — after SsStart that chains the VBlank walk AND the
libsnd sequencer tick, which is why audio works), pad service, SPU advance, snapshot tick, and the
neutral presentation commit. Full libetc VSync `0x800E4DB0` is a fail-fast PlatformHle trap for every
mode; no guest wait or counter query owns cadence. A per-field service that "has no call site" on this
port is missing because it belongs THERE — that was the whole root cause of both silence and dead
input.

**The framework seam is inherited directly now:** process-lifetime `x4::X4Runtime` derives
`GameRuntime` and owns title render-path selection, a typed `GuestProgramImage`, measured boot
dispatch, and override registration. It binds the legacy `GameConfig`/`GameHooks` only as
compatibility views while generic algorithms migrate; they are not a behavior-bearing base class.
This direct boundary removed the complete `Fps60` implementation from the shipping link. Framework
the recorded pin also includes 7bd24f2b's split of temporal-only game/GPU helpers from neutral translation units, and the
shipping binary dependency gate rejects any regression.
**RE-01, the crt0 boot group, has retained binary evidence and is wired:** claim C005 records the
derivation from `SLUS_005.61`; the typed runtime-image and boot configuration own the measured values.
Boot conformance must exercise the native/Lightrec execution boundary on the authenticated runtime
image.
**RE-06 is verified from the retail InitPAD call:** slot 0 is `0x80166D68`, slot 1 is `0x8012F46C`,
and both capacities are `0x22`; `tools/verify_pad.py --check` scans all 294,400 loaded words and diffs
the unique call's four arguments against the `GameConfig` that ships. Every other guest-address group
remains zero with its open step named in `docs/re-frontier.md`.
**RE-08 is implemented but runtime-partial:** `tools/verify_projection.py --check` proves the only
OFX/OFY/H writes are the one boot setup chain (160/120/512). The pre-migration
`WidescreenController`, owned by `X4Context`, wraps those measured retail publications through the
former address-override seam: it sets
only OFX before SetGeomOffset and only RECT.w after SetDefDrawEnv. The recorded framework gives 16:9
OFX/width 214/428 and exact 4:3 identity. Unit/Clang gates passed before the next framework-policy
migration; old integrated pixels exposed issue #19 instead of completing the step: the all-2D title
remains authored as a 320-wide composition and becomes left-anchored when the guest clip widens.
Fresh matched title/gameplay captures remain mandatory. The dynamic product preserves the same
measured publications through scoped original guest calls.

**RE-10 has one selected native body in progress:** the title state-0 white-logo quad initializer
`0x800D6F94`, derived from `external/mmx4/src/main/title_quad.c` and independently gated against all
49 retail instructions by `tools/re_title_quad.py`. `X4Runtime` installs the retained-super pair and
the hermetic C++ test pins the object/register contract. An exact-pin serialized real-disc run reaches
the body and reports `[mirror-verify] 0x800D6F94 OK (pass #1)`. Do not call it fully verified yet: a
deliberate live mismatch discriminator remains open. The same run's sampled presents were a stable
dark title field, so they do not prove visible title composition. This body changes no pixels and is
not a fix for widescreen issue #19.

There is no static development build/run command. Product execution resumes only through the
native/Lightrec target; historical measurements below remain evidence, not an executable fallback.

The normal CTest gate calls psxport's shared C++ policy checker: every tracked first-party C/C++ file
is checked with this repository's `.clang-format`, the 1,200-line ownership cap is enforced, and
`.clang-tidy` runs against `build/compile_commands.json`. It excludes `external/`;
there is no copied checker and no pre-commit hook. CTest also runs `tools/test_run.py`: the shipping
launcher enters the frozen `uv.lock` environment through `bootstrap.py`, while `run.sh` is only its
stable exec wrapper. It performs no compiler-identity filtering; explicit `CC`/`CXX` pass through
and otherwise CMake owns toolchain discovery. The user launcher explicitly opens the window, audio
device, and paced presenter at its final exec boundary. Agent tools launch the product directly with
explicit headless, silent, and unpaced policy; ambient agent flags never change the player path.

**`external/psxport` is NOT a submodule any more (2026-08-16)** — it is a symlink to the workspace's
shared framework clone when one exists, or a private clone at this repo's `psxport.pin` on a fresh
machine; `tools/psxport_sync.py --auto` establishes whichever applies. The framework's own nested
vendors (`vendor/lucent`, `vendor/beetle-psx/deps/libchdr`) are the SHARED clone's concern — initialized
once there, never per-port (`--recursive` aborts on beetle-psx's url-less `deps/lightning/gnulib`, and
`scripts/sync_submodules.py` refuses to certify an incomplete nested inventory). `CMakeLists.txt` fails with a clear
message if they are missing in the shared clone, and `tools/discdump.py` says the same when its build
fails.

The CMake/product composition accepts only the authenticated runtime image and native/Lightrec target.
The user play launcher has no test path or option and builds under top-level `build/`.

## Start here, every task

```sh
python3 tools/re_frontier.py next            # which RE step is actually ready to work
python3 tools/info.py brief <words>          # what's already proven — and does it still hold?
python3 tools/catalog.py search <symptom>    # has this been hit (or ruled out) before?
python3 tools/behavior.py check              # X4-SPECIFIC: are pc_enh gates comparison-suppressed?
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
  already runs at 60. There is no native producer or temporal decorator to drive, but the host still
  owns the one-step retail loop and timing through `X4FrameDriver`; native loop ownership does not
  imply native rendering. The legacy `GameHooks::frameUpdate` stays fail-fast because it is not this
  title's typed driver seam. Marking native producers/interpolation ⬜ would put those steps on the
  roadmap the USER has ruled out.

  **The neutral presenter, exact field-rate SPU cadence, and field-aware CD time are recorded at
  the recorded 9c2e3f1c pin (introduced at 7bd24f2b).** X4 schedules no
  interpolated pass, constructs no temporal decorator, and calls that current-frame presenter.
  `tools/verify_no_temporal_dependency.py` rejects Fps60 products/includes/calls and temporal hooks
  from shipping title sources and inspects the linked binary. Claim C018 remains the historical
  falsifier; issues #12 and #18 record the ownership migration and its opposite-answer gate. The
  current framework policy API also makes
  X4's derived runtime explicitly answer `guestVramIsPicture=false`; the legacy GameConfig bit is a
  false compatibility mirror, not the policy owner. Do not copy
  the fence into this repo or replace it with raw present plus a separate pacer.
- All three deliverables are the **`pc_enh` behaviour class with `affect: full`** — they deliberately
  change canon guest state. So the RE target of this port is the **PLAYER-OBJECT SYSTEM**, not the
  renderer, and every one of them must be **force-suppressed by the typed comparison-run role** so
  byte-compares stay enhancement-free *by construction*.
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

- **Job A — raw I/O latency:** RESOLVED at the recorded pin (issue #13): the shared emulated-time
  candidate services the retail asynchronous ReadN/callback route onward from LBA 225 and reaches the
  title. The raw WALL-CLOCK load-time number is still unmeasured — quote nothing until it is.
- **Job B — the loading coroutine itself:** LANDED 2026-08-24 per the USER directive. The measured
  direct/archive issuers (0x80013890/0x80013AD8) now own one synchronous operation
  (`game/core/fast_wait.cpp`, `PSXPORT_X4_FASTWAIT`, default on): each runs its untouched setup once,
  feeds table-derived raw sectors through the original ready callback via Lightrec, drains archive postprocess
  after every callback, requires terminal state 2, and returns. The unchanged wait bodies therefore
  run zero yield/draw iterations and loading-presentation wait 0x80013530 is omitted. The discarded
  presentation-withholding experiment and its equal-field RAM dumps are not evidence for this
  implementation. The game's OTHER scripted waits/fade ramps (non-load fades, 21/34 call sites) are
  still unclassified. `pc_enh`, `affect: full`, suppressed in comparison roles —
  docs/behavior-map.md `fastwait`.

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
  claim C005): `.bss` clear `[0x8012F418, 0x80175F38)` = `0x46B20`; `sp = fp =
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
way that reads as a framework bug. Native override addresses must be derived from this exact image
identity and installed only for that identity.

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

`PSXPORT_DIR` defaults to `external/psxport`, so the replacement native/Lightrec target must keep a
bare clone standalone. Maintainer verification may select an in-progress shared psxport checkout
through that one CMake setting after the dynamic target exists; it never uses `run.sh`, and it never
re-spells `external/psxport` at another CMake or tool call site.
