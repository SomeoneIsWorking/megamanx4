# Mega Man X4 — repository-specific instructions

This is the USA `SLUS_005.61` enhancement port. The authenticated executable is runtime data;
`external/psxport` owns PSX and Lightrec execution, while this repository owns title identity,
measured native behavior, and widescreen, loading removal, and X/Zero co-op. Read
`external/psxport/CLAUDE.md` for the framework contract. Use `docs/project-goals.md` for scope,
`docs/project-state.md` for current capability status, `docs/issues/` for open bugs and missing
features, and `docs/codemap.md` for ownership.

## Title boundaries

- `x4::X4Runtime` is the process-lifetime title owner. It composes the measured boot, image-scoped
  native overrides, render-path policy, and `X4FrameDriver`. `GameConfig` and `GameHooks` are
  compatibility views through `x4::legacy::{measuredConfig,compatibilityHooks}`; add behavior to
  typed owners instead of extending those views.
- `X4FrameDriver::stepFrame()` owns one retail field. The per-field host services belong in
  `x4::vsync::deliverField` (`game/core/vsync_sync.cpp`): retail IRQ-0 delivery, pad service, SPU
  advance, snapshot tick, and presentation commit. Full guest libetc VSync `0x800E4DB0` is served by
  the image-scoped override in the same file; do not alter movie bodies to simulate suspension or
  progress.
- The guest GTE picture is the player renderer. X4 already runs at 60 fps, so native producers,
  frame interpolation, and native depth are outside this port's scope. Do not link temporal
  `Fps60` machinery or select a guaranteed-black native render path.
- Widescreen, loading removal, and co-op are `pc_enh` changes with `affect: full`. Typed comparison
  runs suppress them. Route every enhancement read through `x4::enh()` in
  `game/core/enhancements.cpp`, not direct CVar `.get()` calls. `docs/config.md` owns the knobs;
  `docs/behavior-map.md` owns their divergence and comparison behavior, and
  `tools/behavior.py check` is its machine gate.
- Keep raw CD I/O latency and removal of the retail loading coroutine as separate behaviors. A
  combined "load time" number establishes neither. Co-op needs its own evidence: a comparison run
  with co-op suppressed proves only baseline parity.

## Evidence and source boundaries

- Bind every guest address and native override to the exact `SLUS_005.61` image identity
  (SHA-1 `213733031136d095ca275d6957695aa25011cfa5`). A matching-decomp symbol is a lead until this
  repository measures it against these bytes. Leave an unmeasured compatibility field at zero with
  its open step named; never guess a value.
- `external/mmx4` is an AGPL-3.0 matching decompilation. AGPL-derived title code stays in this
  repository and never enters psxport; `LICENSING.md` and `tools/check_license_containment.py` own
  that boundary. Sony PSY-Q headers in the reference are not available for copying. Fetch only
  `external/mmx4`, without recursively initializing its build-tool submodules.
- `external/psxport` resolves to the shared writable checkout or a private clone at `psxport.pin`.
  `tools/psxport_fetch.py --auto` establishes it; framework changes land in psxport and a verified
  consumer pin is updated with `external/psxport/tools/psxport_sync.py --repo . --bump`.
- Disc resolution is implemented once in `tools/resolve_disc.py`: explicit argument,
  `PSXPORT_X4_DISC`, `.env`, then an unambiguous repository-root CHD. The exact executable must pass
  `tools/extract_exe.py` identity validation. Do not package game data.

## Working in this repository

- `tools/verify.py` is the gate (`uv run --frozen python tools/verify.py`). It configures the build,
  builds `megamanx4_port`, and runs the CTest set: the C++ style policy, the temporal-dependency
  source and shipping-binary checks, the `x4_*` hermetic seam tests, and the live psxport pin check.
- `tools/live_play.py` and `tools/title_prompts.py` drive a headless run over the control channel:
  input, front-end state, presents, and frame captures. That is how the product is exercised.
- `tools/verify_task_resume.py` runs the product to its frame cap and asserts a non-frozen picture.
- A past native run is not Lightrec gameplay evidence. Verify the shipping dispatcher, including a
  reached native override and its scoped original call, before claiming dynarec behavior.