# Config — THIS port's own knob registry

This file exists because the framework's instruction "register every enhancement name in
`docs/config.md`" resolves to `external/psxport/docs/config.md`, **which is inside a submodule a game
repo may not edit.** So the game-local half lives here.

The framework's knobs, the ladder's implementation and the whole `cfg_*` / CVar API are documented in
`external/psxport/docs/config.md` and `runtime/recomp/config_var.h` and are **not restated here**.

## The ladder, quoted from `runtime/recomp/config_var.h`

```
    Default   what the framework compiled in
  < Value     the user's persisted choice (psxport_settings.ini)
  < Override  a launch argument — the PSXPORT_* environment variable. Never persisted.
  < Runtime   a REPL / debug-server command. This run only. Never persisted.
```

A higher layer wins. `Layer` is DERIVED from which slots are set rather than stored, so the
introspection dump can show every layer of a knob at once. Note the deliberate deviation from Dusklight
recorded in that header: Runtime sits ABOVE Override, *"because psxport's runtime layer is a human typing
at a live console after launch, which is later and more specific than the environment the process
started in."*

## This port's knobs

| knob | kind | default | persistable | C++ object | read path |
|---|---|---|---|---|---|
| `PSXPORT_X4_DISC` | path (port fact, not a CVar) | — | — | `GameConfig::discEnvVar` | `tools/resolve_disc.py` host-side; the framework's disc resolver guest-side |
| `PSXPORT_X4_CARD` | path (port fact, not a CVar) | `scratch/saves/megamanx4.mcr` | — | `GameConfig::cardEnvVar` / `cardDefaultPath` | the framework's memory-card backend |
| `PSXPORT_X4_WIDESCREEN` | Bool | `false` | yes | `x4::cv_widescreen` | **`x4::enh(x4::cv_widescreen)`** |
| `PSXPORT_X4_COOP` | Bool | `false` | yes | `x4::cv_coop` | **`x4::enh(x4::cv_coop)`** |
| `PSXPORT_X4_FASTWAIT` | Bool | `false` | yes | `x4::cv_fastwait` | **`x4::enh(x4::cv_fastwait)`** |

`PSXPORT_X4_DISC` is spelled identically in exactly three places and they must not diverge:
`.env.example`, `GameConfig::discEnvVar`, and `tools/resolve_disc.py`'s `ENV_KEY`.

The three enhancement knobs are `persistable = true` deliberately: they are USER PREFERENCES, which is
the class the Value layer exists for (cf. the framework's `cv_fps60`, whose Value layer is the `fps60=`
line the overlay writes).

## The force-suppression rule — NEVER call `.get()` at a feature call site

Every read of an enhancement knob goes through **one** function, `x4::enh()` in
`game/core/enhancements.cpp`. It returns `false`, with a one-time-per-knob `[cfg:warn]`, whenever this
run is a byte-compare run — the three inputs being exactly the ones `runtime/recomp/cfg.cpp:197`'s
`cfg_enh()` uses:

- `PSXPORT_ORACLE` (via `psx::config::cv_oracle`),
- `PSXPORT_SBS` (via `cfg_on`),
- a non-empty `PSXPORT_SBS_MODE` (via `cfg_str`).

Using the same three is what stops the two mechanisms disagreeing about what a byte-compare run *is*; a
divergence there would mean an SBS variant this gate does not recognise, i.e. a contaminated compare
that still looks clean. The warn text follows the framework's own wording so both are greppable
together: `"PSXPORT_X4_COOP SUPPRESSED: oracle/SBS run must stay enhancement-free"`. The one-time flag is
**per knob**, not one global: a run with two enhancements set must name both, or the second reads as
never having been asked for.

Calling `cv_coop.get()` directly at a feature call site is the bug the chokepoint exists to prevent. If
you find one, it is a defect, not a shortcut.

Each knob is also registered in `docs/behavior-map.md` as `class: pc_enh` / `affect: full` with a `guard`
that cites the suppression — and that text is **machine-checked**: `tools/behavior.py check` fails an
`affect: full` entry whose guard does not match `oracle|sbs|suppress`. The chokepoint plus that check is
this port's whole "enhancement-free by construction" story.

## This port does NOT use `PSXPORT_ENH` / `cfg_enh()`

Two reasons, both concrete:

1. **USER ruling: CVars.** `cfg_enh` cannot satisfy it — it reads
   `lucent::config::text("PSXPORT_ENH")` directly into a function-local seeded static, so it is env-only:
   no Value (settings-file) layer, no Runtime (REPL) layer, and it never appears in the CVar registry
   dump. The framework's `docs/config-migration.md` "Qualification 2" explains why it was never
   migrated (*"a SUPPRESSION rule, not a layer"*) and lists `PSXPORT_ENH` as still pending.
2. **`cfg_enh` has zero call sites anywhere in the workspace.** X4 is the first real consumer of the
   `pc_enh` class; the two names registered in the framework's own `docs/config.md`
   (`expanded-load-range`, `faster-transitions`) are both `planned`.

The duplication of the suppression rule in `x4::enh()` is therefore deliberate and commented as such.
The proper fix is upstream — migrate `PSXPORT_ENH` onto the ladder, keeping the suppression as an
explicit resolve-time hook with its own log line — and a game repo may not make it. Hand it to the
operator.

## Audit discipline — judge a knob on the EXIT audit, never the startup line

A knob that is set but matches nothing is named at startup as:

```
[cfg:warn] UNKNOWN knob X is set and matched nothing — it did NOTHING in this run
```

**Read only the exit audit:**

```
[cfg] env audit AT EXIT (everything that was going to be read has been): N set -> ... 0 UNKNOWN
```

The startup audit runs *before* late-initialising subsystems have read anything, so it reports every
not-yet-read knob as UNKNOWN — a claim about the run, made before the run. Measured elsewhere in this
workspace: 6 knobs set → 4 UNKNOWN at startup, 0 at exit, and all four had worked. Gate on the exit line
only.

Declaring these three as CVars rather than reading them with `cfg_on` is precisely what keeps them out of
that UNKNOWN list and puts them in the REPL `cvars` dump.

**AND THAT IS A COST, NOT ONLY A WIN — so this port pays it back explicitly.** All three features are
still `planned` (RE-07/08/09) and `grep -rn 'x4::enh' game/` finds no call site outside
`enhancements.{h,cpp}`. `UNKNOWN … it did NOTHING in this run` is precisely the signal the framework had
for "you set a knob and nothing consumed it", and registering a name is what silences it: a registered
CVar with zero consumers resolves silently to `true`, the exit audit says `0 UNKNOWN`, and a user or a
future session can read a clean startup as "co-op is on". The suppression path is loud; the
not-implemented path was silent — the inverse of this repo's own "a diagnostic that can print nothing is
lying" rule.

So `game/core/enhancements.cpp` carries a `kUnimplemented` list (knob → frontier step), and
`x4::audit_declared_enhancements()` — called once from `main.cpp` right after the seam install — pushes
every knob the user turned ON through the chokepoint, producing one line per knob:

```
[cfg:warn] PSXPORT_X4_COOP is DECLARED but NO feature reads it yet (RE-07) — this run did NOTHING with it. Enabling it is not evidence that the enhancement works.
```

The audit exists because the read-time check alone cannot fire: a knob nothing reads never reaches
`enh()`. On a compare run the SUPPRESSED line replaces it (both verified 2026-08-12 against the real
objects: nothing set → silent; all three set → three DECLARED-but-unread lines; all three set with
`PSXPORT_ORACLE=1` / `PSXPORT_SBS=1` / `PSXPORT_SBS_MODE=ab` → three SUPPRESSED lines and `enh()` false).
**Deleting an entry from `kUnimplemented` belongs in the same commit that adds that feature's first real
call site** — that is what makes the warning shrink to nothing on its own.
