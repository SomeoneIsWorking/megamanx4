# Mega Man X4 — a PC-native enhancement port

A PC-native port of **Mega Man X4** (PS1, USA, `SLUS_005.61`) built on the
[psxport](https://github.com/SomeoneIsWorking/psxport) static-recompilation framework, vendored here as
`external/psxport`.

Unlike psxport's other consumers this is an **enhancement port, not a native-engine rebuild**: X4
already runs at 60fps, so there is no frame interpolation, no native producer and no native renderer to
build. The three deliverables are widescreen, drop-in co-op (P2 spawns as the other hunter), and
collapsing the game's own scripted wait states — all of them deliberate guest-state changes, gated by
CVars and force-suppressed under the byte-compare oracle. See `docs/plans/enhancements.md`.

## Status: guest runtime reaches the front end; playability is not yet verified

Created 2026-08-12. The retail executable emits a native `megamanx4_port` substrate and boots through
InitHeap into guest `gameMain`, the retail task handoff, and the front-end archive path. The recorded
framework pin preserves X4's alternating framebuffer pages: a real GTE capture renders the Mega Man X
logo instead of the prior all-black frame. Forced START reaches the game's held/previous/edge globals,
and headless WAV capture contains non-zero samples after restoring the live libsnd VBlank tick chain.
These are measured runtime boundaries, not a claim that gameplay, audible device playback, widescreen,
or co-op is complete. What exists:

- disc → executable provisioning from **your own** disc image (nothing game-derived is in this repo),
- the measured CRT0 and pad groups, resident routing range, generated-substrate registry, and three
  enhancement CVars,
- a default-on synchronous direct/archive load owner whose measured requests finish in one issuer
  call, plus removal of the measured loading-presentation task; exact destination-byte comparison and
  a capture proving no loading frame reaches presentation remain open,
- the project registries (`docs/re-frontier.md`, `docs/codemap.md`, `docs/behavior-map.md`,
  `docs/config.md`, `docs/info/`, `docs/issues/`),
- a vendored **AGPL-3.0 matching decompilation** of this exact executable, `external/mmx4`, whose
  declared build target is the same SHA-1 as the image extracted from this disc.

`docs/codemap.md` is the honest inventory; `docs/re-frontier.md` is the ordered RE chain.

## Getting started

```sh
git clone <this repo> && cd megamanx4
git submodule update --init external/mmx4           # optional matching-decomp reference
cp .env.example .env && $EDITOR .env                # point it at your own disc image (.env is gitignored)
./run.sh                                             # provision, emit, build, launch
./run.sh --prepare-only                              # same cold path, but stop before launch
uv run --frozen python tools/re_frontier.py next    # what to work on
```

`tools/psxport_sync.py` resolves the framework and initializes its required direct vendors without
recursing into Beetle's URL-less `gnulib` path. Do not recursively initialize `external/mmx4`; its
nested build-tool submodules are not needed by this port.

`run.sh` is the play launcher. It enters the repository's frozen `uv.lock` environment through
`bootstrap.py`; non-trivial policy lives in `tools/run.py` and `tools/ensure_recomp.py`. This player
entry point only provisions, builds, and launches the current game target. Maintainer verification
is a separate Clang workflow.

## Requirements

`uv`, cmake ≥ 3.21, pkg-config, SDL3, zlib, zstd, and a C/C++ toolchain CMake can use. Maintainer
verification separately uses Clang, clang-format, and clang-tidy. Missing packaged tools and SDL3
are refused with the exact supported platform install command; the launcher does not run privileged
package managers itself.

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
