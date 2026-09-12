# Mega Man X4 — repository-specific instructions

This is the USA `SLUS_005.61` enhancement port. The authenticated executable is runtime data;
`external/psxport` owns PSX and Lightrec execution, while this repository owns title identity,
measured native behavior, and widescreen, loading removal, and X/Zero co-op. Read
`external/psxport/CLAUDE.md` for the framework contract. Use `docs/project-goals.md` for scope,
`docs/project-state.md` for current capability status, `docs/re-frontier.md` for measured guest
facts and the next evidence step, `docs/issues/` for atomic work, and `docs/codemap.md` for ownership.

## Title boundaries

- `x4::X4Runtime` is the process-lifetime title owner. It composes the measured boot, image-scoped
  native overrides, render-path policy, and `X4FrameDriver`. `GameConfig` and `GameHooks` are
  compatibility views through `x4::legacy::{measuredConfig,compatibilityHooks}`; add behavior to
  typed owners instead of extending those views.
- `X4FrameDriver::stepFrame()` owns one retail field. The per-field host services belong in
  `x4::vsync::deliverField` (`game/core/vsync_sync.cpp`): retail IRQ-0 delivery, pad service, SPU
  advance, snapshot tick, and presentation commit. Full guest libetc VSync `0x800E4DB0` remains a
  fail-fast trap; do not alter movie bodies to simulate suspension or progress.
- The guest GTE picture is the player renderer. X4 already runs at 60 fps, so native producers,
  frame interpolation, and native depth are outside this port's scope. Do not link temporal
  `Fps60` machinery or select a guaranteed-black native render path.
- Widescreen, loading removal, and co-op are `pc_enh` changes with `affect: full`. Typed comparison
  runs suppress them. Route every enhancement read through `x4::enh()` in
  `game/core/enhancements.cpp`, not direct CVar `.get()` calls. `docs/config.md` owns the knobs;
  `docs/behavior-map.md` owns their divergence and comparison behavior.
- Keep raw CD I/O latency and removal of the retail loading coroutine as separate measurements.
  A combined “load time” number does not establish either. `docs/behavior-map.md` records the
  `fastwait` contract and `docs/re-frontier.md` records the binary evidence. Co-op needs its own
  evidence; a comparison run with co-op suppressed proves only baseline parity.

## Evidence and source boundaries

- Bind every guest address and native override to the exact `SLUS_005.61` image identity. A
  matching-decomp symbol is a lead until the repository's verifier measures it against these bytes.
  Leave an unmeasured compatibility field at zero with its frontier step named; never guess a value.
- `external/mmx4` is an AGPL-3.0 matching decompilation. AGPL-derived title code stays in this
  repository and never enters psxport; `LICENSING.md` and `tools/check_license_containment.py` own
  that boundary. Sony PSY-Q headers in the reference are not available for copying. Fetch only
  `external/mmx4`, without recursively initializing its build-tool submodules.
- `external/psxport` resolves to the shared writable checkout or a private clone at `psxport.pin`.
  `tools/psxport_sync.py --auto` establishes it; framework changes land in psxport and a verified
  consumer pin is updated with `tools/psxport_sync.py --bump`.
- Disc resolution is implemented once in `tools/resolve_disc.py`: explicit argument,
  `PSXPORT_X4_DISC`, `.env`, then an unambiguous repository-root CHD. The exact executable must pass
  `tools/extract_exe.py` identity validation. Do not package game data.

Start non-trivial work with `tools/info.py brief <terms>`, `tools/re_frontier.py next`, and
`tools/catalog.py search <symptom>`. Check `tools/behavior.py check` when touching an enhancement.
The RE frontier, claims, and issues hold the historical measurements; a past native run is not
Lightrec gameplay evidence. Verify the shipping dispatcher, including a reached native override
and its scoped original call, before claiming dynarec behavior.
