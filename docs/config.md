# Config — THIS port's own knob registry

This file exists because the framework's instruction "register every enhancement name in
`docs/config.md`" resolves to `external/psxport/docs/config.md`, **which is inside a submodule a game
repo may not edit.** So the game-local half lives here.

The framework's knobs, the ladder's implementation and the whole `cfg_*` / CVar API are documented in
`external/psxport/docs/config.md` and `runtime/psx/config/config_var.h` and are **not restated here**.

## The ladder, quoted from `runtime/psx/config/config_var.h`

```
    Default   what the framework compiled in
  < Value     the user's persisted choice (psxport_settings.ini)
  < Override  a launch argument — the PSXPORT_* environment variable. Never persisted.
  < Runtime   a REPL / debug-server command. This run only. Never persisted.
```

A higher layer wins. `Layer` is DERIVED from which slots are set rather than stored, so the
introspection dump can show every layer of a knob at once. Runtime sits above Override because it is
a human action at a live console after launch, later and more specific than the process environment.

## This port's knobs

| knob | kind | default | persistable | C++ object | read path |
|---|---|---|---|---|---|
| `PSXPORT_X4_DISC` | path (port fact, not a CVar) | — | — | `kTitleIdentity.discEnvVar` (`game/boot/x4_catalog.cpp`) | `tools/resolve_disc.py` host-side; the framework's disc resolver guest-side |
| `PSXPORT_X4_CARD` | path (port fact, not a CVar) | `scratch/saves/megamanx4.mcr` | — | `X4Runtime::hostIdentity()` (`game/boot/x4_runtime.cpp`) | the framework's memory-card backend |
| `PSXPORT_X4_WIDESCREEN` | Bool | `true` | yes | `x4::widescreenCvar()` | `psx::config::enh(widescreenCvar())` in game/widescreen/widescreen_controller.cpp |
| `PSXPORT_X4_COOP` | Bool | `false` | yes | `x4::coopCvar()` | no reader yet; `x4::reportUnreadEnhancements()` says so each run |
| `PSXPORT_X4_SKIP` | Bool | `true` | yes | `x4::skipCvar()` | `psx::config::enh(skipCvar())` in game/input/sequence_skip_overrides.cpp (Start skips the Hunter H.Q. briefing) |
| `PSXPORT_X4_FASTWAIT` | Bool | `true` | yes | `x4::fastWaitCvar()` | `psx::config::enh(fastWaitCvar())` in game/media/fast_wait.cpp (loading-coroutine conversion) |

## Title render policy: Native and synthetic 60fps are not player options

X4 (`SLUS_005.61`) deliberately consumes neither the framework's PC-native renderer nor its synthetic
interpolated-frame tier. The retail title already owns the target cadence, and the guest's own GP0
work is the picture. `X4Runtime::renderCapabilities()` is the title authority: it declares the record
path (psxport `docs/presentation.md`) as the default, no native renderer, and no temporal interpolation. The shared menu,
settings loader/saver, and runtime render-path resolver consume that same declaration.

The menu therefore offers neither Native rendering nor 60fps interpolation, and this repository's
settings file carries no `fps60` key. An explicit diagnostic request for an unsupported mode remains a
loud refusal or capability-owned fallback; it does not silently enable a product X4 does not own.

The no-argument policy is therefore unambiguous. `PSXPORT_X4_WIDESCREEN` is the product default and only
switches the enhancement off: when it is on, the player's Aspect Ratio row (`Mods::aspect`, the `aspect=`
settings key) chooses 4:3, 16:9, 21:9 or Auto (`x4::WidescreenPolicy::presentationAspect`). The tracked
`psxport_settings.ini` carries `aspect=1` for tool runs; a comparison or recordcheck run passes its own
settings file with `aspect=0` (`docs/issues/0024`).

## Native-override differential checks

Native functions compare against their authenticated original guest bodies through psxport's scoped
Lightrec original-call API. Diagnostic controls exercise the same runtime dispatcher; there is no
generated implementation or static selector in the product.

`PSXPORT_X4_DISC` is spelled identically in exactly three places and they must not diverge:
`.env.example`, `kTitleIdentity.discEnvVar` in `game/boot/x4_catalog.cpp`, and `tools/resolve_disc.py`'s `ENV_KEY`.
The launcher imports that key and publishes an explicit disc argument into the environment used by
both executable extraction and the running CD backend. A command-line disc therefore takes precedence
over an existing title or generic disc setting for the whole session, including relative paths and
paths containing spaces. Without an argument, environment, `.env`, and drop-in resolution are preserved.

The three enhancement knobs are `persistable = true` deliberately: they are USER PREFERENCES, which is
the class the Value layer exists for (cf. the framework's `cv_fps60`, whose Value layer is the `fps60=`
line the overlay writes).

## Comparison-run suppression

Every read of an enhancement knob calls `psx::config::enh(<knob>)`, never `.get()`. That framework
function owns `PSXPORT_DIAGNOSTIC_RUN=product|compare-candidate|compare-reference`: either comparison
role returns false with a per-knob Lucent warning, product mode honours the resolved knob.

Each knob is registered in `docs/behavior-map.md` as `class: pc_enh` / `affect: full` with a `guard`
citing that suppression; `tools/behavior.py check` fails an `affect: full` entry whose guard does not.

## Declared knobs without a reader

A registered CVar with no reader resolves silently and the exit audit reports `0 UNKNOWN`, so a clean
run cannot tell the user that co-op does nothing. `x4::reportUnreadEnhancements()`, called from
`X4Runtime::registerOverrides`, logs one line per run naming every declared knob no feature reads yet
(today `PSXPORT_X4_COOP`, RE-07). Remove a knob from that line in the commit that adds its first reader.

Judge knobs on the exit `[cfg] env audit AT EXIT` line, never the startup audit: the startup audit runs
before late subsystems have read anything.
