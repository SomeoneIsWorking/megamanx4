# Mega Man X4 — a PC-native enhancement port (bootstrap stage)

A PC-native port of **Mega Man X4** (PS1, USA, `SLUS_005.61`) built on the
[psxport](https://github.com/SomeoneIsWorking/psxport) static-recompilation framework, vendored here as
`external/psxport`.

Unlike psxport's other consumers this is an **enhancement port, not a native-engine rebuild**: X4
already runs at 60fps, so there is no frame interpolation, no native producer and no native renderer to
build. The three deliverables are widescreen, drop-in co-op (P2 spawns as the other hunter), and
collapsing the game's own scripted wait states — all of them deliberate guest-state changes, gated by
CVars and force-suppressed under the byte-compare oracle. See `docs/plans/enhancements.md`.

## Status: first resident substrate boots into the guest

Created 2026-08-12. The retail executable now emits 6,192 binary-rooted entries and 7,533 recompiled
functions, builds `megamanx4_port` with Clang, and boots through InitHeap into guest `gameMain`. The
current stop is the CD-init IRQ2 callback contract, not a recompiler seed miss or a blocking VSync.
The retail VBlank wait route is measured and installed, but boot only queries `VSync(-1)` before the
CD loop. What exists:

- disc → executable provisioning from **your own** disc image (nothing game-derived is in this repo),
- the measured CRT0 and pad groups, resident routing range, generated-substrate registry, and three
  enhancement CVars,
- the project registries (`docs/re-frontier.md`, `docs/codemap.md`, `docs/behavior-map.md`,
  `docs/config.md`, `docs/info/`, `docs/issues/`),
- a vendored **AGPL-3.0 matching decompilation** of this exact executable, `external/mmx4`, whose
  declared build target is the same SHA-1 as the image extracted from this disc.

`docs/codemap.md` is the honest inventory; `docs/re-frontier.md` is the ordered RE chain.

## Getting started

```sh
git clone <this repo> && cd megamanx4
python3 tools/psxport_sync.py --auto                # shared workspace checkout or private pin clone
git submodule update --init external/mmx4           # optional matching-decomp reference
cp .env.example .env && $EDITOR .env                # point it at your own disc image (.env is gitignored)
./run.sh                                             # provision, emit, Clang-build, verify, launch
python3 tools/verify_recomp_bootstrap.py --selftest # static positive + bad-seed refusal
python3 tools/re_frontier.py next                   # what to work on
```

`tools/psxport_sync.py` resolves the framework and initializes its required direct vendors without
recursing into Beetle's URL-less `gnulib` path. Do not recursively initialize `external/mmx4`; its
nested build-tool submodules are not needed by this port.

`run.sh` is the play launcher. Non-trivial policy lives in `tools/run.py` and
`tools/ensure_recomp.py`; the shell file is only the stable exec wrapper.

## Requirements

cmake ≥ 3.21, pkg-config, SDL3, zlib, zstd, python3, Clang/clang-format/clang-tidy.

## Legal

**No game content is distributed here.** The disc image, the executable extracted from it and the
recompiled substrate derived from it are all yours and are gitignored. `tools/go_public.py` audits the
full history for disc-derived material and machine-specific paths.

### Licensing

This repo is **AGPL-3.0-or-later** (`LICENSE`), because it may contain code derived from
[sozud/mmx4](https://github.com/sozud/mmx4), an AGPL-3.0 decompilation of this executable. The
per-component breakdown — including the fact that `external/mmx4/include/psy-q-4.0/` is Sony's SDK and
not the decomp's to relicense, and that the framework's own terms are currently **unstated** — is in
`LICENSING.md`.

**psxport is not AGPL, and no code from this repo may be pushed upstream into it.** The framework is
vendored by five ports; copyleft landing there would pull all of them in. That firewall is stated in
`CLAUDE.md` and `docs/references.md` and checked by `tools/check_license_containment.py`.
