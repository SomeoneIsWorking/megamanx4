# Codemap — Mega Man X4

Where X4's code lives and what each owner owns. Feature chains are in `docs/features.md`; the
framework side is `external/psxport/docs/codemap.md`. The boot executable is the whole engine (no
overlays); `external/mmx4` is an AGPL matching-decomp reference that never enters psxport.
`runtime/` and `frame/frame_driver.h` are included through their directory (`"runtime/session.h"`); the other `game/` directories sit on the include path.

## Owners

| owner | path | owns |
|---|---|---|
| `createCatalog` | `game/runtime/catalog.*` | The one-title catalog: `SLUS_005.61` identity, disc key and one `x4::Runtime` |
| `x4::Runtime` | `game/runtime/runtime.*` | The `GameRuntime`: crt0 and boot prefix, stock VSync/DMA-callback/libcd/pad bindings, every native override, session, frame driver, Record path, card identity, `warp`, run report |
| `x4::Session`, `session` | `game/runtime/session.*` | Per-Core title state every owner composes; `stockCdSync`/`stockCdControl` |
| `x4::frame::FrameDriver`, `bootPrefix` | `game/frame/frame_driver.*` | One retail field: armed warp, field service, draw prefix, `UpdateTasks`, suffix; a blocking movie or mid-frame task skips the prefix |
| `deliverField`, `serveVSync` | `game/frame/vsync_sync.*` | The one per-field service (IRQ-0, pad, SPU, snapshot, commit) and libetc VSync `0x800E4DB0` |
| `guest::dispatch`, `guest::call`, `callWithoutKnownReturn` | `game/execution/guest_execution.*` | Guest calls, a retail `jal` site (`CallSite`) and their measured return boundaries |
| `native_overrides::install` | `game/execution/native_overrides.*` | The loading-owner overrides against the authenticated image |
| `bios_threads::Service` | `game/execution/bios_threads.*` | OpenTh/ChangeTh/CloseTh under the retail scheduler, task turn budget, `frameInProgress` |
| `pad` constants | `game/input/pad_layout.h` | The two InitPAD receive buffers |
| `input_path::observeField` | `game/input/input_path.*` | Read-only per-field trace of a pad edge (`x4-input-path` channel) |
| `SequenceSkip` | `game/input/sequence_skip*.*` | Start held in the Hunter H.Q. briefing pages it through the pad route `0x80012328` |
| `cd_controller` | `game/media/cd_controller.*` | Controller reset, libcd command-state clear, published mode |
| `cd_control_boundary` | `game/media/cd_control_boundary.*` | `CdControlB(Pause)` through the synchronous CD owner |
| `startup_cd` | `game/media/startup_cd.*` | The setup transaction at `0x80013588` |
| `stream_startup` | `game/media/stream_startup.*` | STR/MDEC start-up: native read, DMA-3 callback, task parked on the next field |
| `stream_interrupt` | `game/media/stream_interrupt.*` | The `StCdInterrupt` sector-completion boundary |
| `movie_cleanup::State` | `game/media/movie_cleanup.*` | The cleanup at `0x80018E50` with its 1+3+3 fields; `ownsPicture` |
| `music_stream::State` | `game/media/music_stream.*` | XA/BGM Setmode with VSync(3) as three host fields |
| `music_cd` | `game/media/music_cd.*` | XA/BGM 6 -> 5 -> 1 `CdSync`/`CdControl` edges |
| `fast_wait::State` | `game/media/fast_wait.*` | Direct/archive loads as one synchronous call, no loading screen |
| `display_init` | `game/render/display_init.*` | The two retail draw environments without the nested VSync |
| `gpu_timeout` | `game/render/gpu_timeout.*` | `set_alarm` `0x800ECB38` from the native field counter |
| `VisibilityCull`, `WidenedObjects` | `game/render/visibility_cull.*`, `widened_objects.*`, `cull_overrides.*` | Retail cull box and the margin objects lent `on_screen` for the draw pass only |
| `WideBackground` | `game/render/background_tiles.*`, `background_overrides.*` | Margin tile columns from the layer cell ring |
| `HudAnchor` | `game/render/hud_anchor.*`, `hud_overrides.*` | HUD packets moved to their screen edge |
| `vram_rect` | `game/render/vram_rect_queue.*` | The eight-entry VRAM rectangle upload queue |
| `title_quad` | `game/ui/title_quad.*` | The white quad behind the MEGAMAN logo |
| `WidescreenPolicy`, `WidescreenController` | `game/widescreen/widescreen_controller.*` | Requested aspect and the per-Core projection plan and cull margin |
| `StageWarp` | `game/debug/stage_warp.*` | `warp <stage> [part]` through engine state 4, applied at a frame boundary |
| `PlayerLens`, `CameraLayerLens`, `PadLens` | `game/title/player_object.h` | Read-only views of the player, camera layer and pad structures |
| `widescreenCvar`, `coopCvar`, `fastWaitCvar`, `skipCvar` | `game/title/enhancements.*` | The `pc_enh` knobs (`docs/config.md`) and the unread-knob line |
| launcher | `tools/run.py`, `tools/resolve_disc.py`, `tools/extract_exe.py` | Disc resolution, extraction and authentication for the zero-argument launch |
| live driver | `tools/live_play.py`, `tools/title_prompts.py` | Headless control-channel input, front-end census, captures |
| checks | `tools/behavior.py`, `check_license_containment.py`, `verify_decomp_targets.py`, `verify_task_resume.py`, `run_end.py` | Behaviour-map, AGPL containment, decomp target identity, task resume, run-end report parsing |
| disc files | `tools/discdump.py` | Lists or extracts disc files through psxport's `discdump` |
| gate | `tools/verify.py`, `cmake/port.cmake` | Build and CTest: style policy, temporal-dependency checks, `x4_*` seams |
| tests | `tests/` | One hermetic seam per owner; `tests/stub_game.h` is the shared stub runtime |

## Where new work goes

- A guest function X4 replaces → the directory owning its subsystem, installed from `x4::Runtime::registerOverrides`.
- Per-Core title state → `x4::Session`.
- A per-field host service → `deliverField`.
- A cadence decision → `x4::Runtime::interpolates`.
- A widened draw → `game/render/`; the value gameplay reads stays retail.
- A title knob → `game/title/enhancements.*`, `docs/config.md`, `docs/behavior-map.md`.
- A debug route to a screen → `game/debug/`, armed by `titleCommand`, applied by `x4::frame::FrameDriver`.
- Co-op → new owners under `game/input/` over `player_object.h`, composed by `x4::Runtime`.
- Anything every title shares → psxport. AGPL-derived code stays here (`LICENSING.md`).
