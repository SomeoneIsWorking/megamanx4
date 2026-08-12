# Mega Man X4 — a PC-native enhancement port (bootstrap stage)

A PC-native port of **Mega Man X4** (PS1, USA, `SLUS_005.61`) built on the
[psxport](https://github.com/SomeoneIsWorking/psxport) static-recompilation framework, vendored here as
`external/psxport`.

Unlike psxport's other consumers this is an **enhancement port, not a native-engine rebuild**: X4
already runs at 60fps, so there is no frame interpolation, no native producer and no native renderer to
build. The three deliverables are widescreen, drop-in co-op (P2 spawns as the other hunter), and
collapsing the game's own scripted wait states — all of them deliberate guest-state changes, gated by
CVars and force-suppressed under the byte-compare oracle. See `docs/plans/enhancements.md`.

## Status: scaffolding. It does not run

Created 2026-08-12. There is no recompiled substrate, no port binary, and nothing about the game is
reverse-engineered yet. What exists:

- disc → executable provisioning from **your own** disc image (nothing game-derived is in this repo),
- the framework seam (`GameConfig` / `GameHooks`) plus the three enhancement CVars, compiling against
  the pinned framework, with every guest address honestly `0`,
- the project registries (`docs/re-frontier.md`, `docs/codemap.md`, `docs/behavior-map.md`,
  `docs/config.md`, `docs/info/`, `docs/issues/`),
- a vendored **AGPL-3.0 matching decompilation** of this exact executable, `external/mmx4`, whose
  declared build target is the same SHA-1 as the image extracted from this disc.

`docs/codemap.md` is the honest inventory; `docs/re-frontier.md` is the ordered RE chain and every
entry in it is `todo`, `blocked` or `skip-by-design`.

## Getting started

```sh
git clone <this repo> && cd megamanx4
git submodule update --init external/psxport external/mmx4          # the two direct submodules
git -C external/psxport submodule update --init vendor/lucent vendor/beetle-psx   # and psxport's own
cp .env.example .env && $EDITOR .env                # point it at your own disc image (.env is gitignored)
python3 tools/extract_exe.py                        # extract + identity-check SLUS_005.61
python3 tools/verify_decomp_targets.py              # does the vendored decomp target our bytes?
cmake -S . -B build && cmake --build build --target megamanx4_seam -j"$(nproc)"
python3 tools/re_frontier.py next                   # what to work on
```

**The second line is not optional and `--recurse-submodules` does not replace it.** psxport's own
`vendor/lucent` (the logger) and `vendor/beetle-psx/deps/libchdr` (CHD access) are what `cmake` and the
provisioning tools need, and initialising `external/psxport` alone leaves them empty:

- `git clone --recurse-submodules` (of this repo or of psxport) **aborts** with `fatal: No url found for
  submodule path 'vendor/beetle-psx/deps/lightning/gnulib'` and leaves `vendor/lucent` empty,
- `external/psxport/scripts/sync-submodules.sh` prints *"all at this repo's recorded gitlinks"* while
  `vendor/lucent` is still empty — it certifies pins it never reached
  (`external/psxport/docs/workspace/KNOWN-DEFECT-sync-submodules.md`),
- so the **per-path, non-recursive** form above is the one that works. It sidesteps the url-less
  `gnulib` path entirely. `CMakeLists.txt` checks for both vendors and fails with that exact command
  rather than letting an `add_subdirectory` error surface from inside the framework.

Do **not** use `--recurse-submodules` on `external/mmx4` itself either: it declares three nested
build-tool submodules we never need.

`run.sh` is the eventual play launcher; today it does every real step and then stops, naming what
blocks the recompile.

## Requirements

cmake ≥ 3.21, pkg-config, SDL3, zlib, zstd, python3, a C++20 toolchain.

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
