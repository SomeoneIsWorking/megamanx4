# Codemap

Ownership and placement map for the Mega Man X4 port. Capability status belongs in
`docs/project-state.md`; product outcomes in `docs/project-goals.md`; atomic work in `docs/issues/`;
binary evidence order in `docs/re-frontier.md`; and proof in `docs/info/`.

## Architecture

```text
run.sh -> bootstrap.py -> tools/run.py
                           |
                           +-- provisioning / recompilation tools -> generated/ (gitignored)
                           +-- CMake -> megamanx4_port
                                        |
                                        +-- game/core/X4Runtime (title policy + composition)
                                        +-- external/psxport (platform/runtime/render/audio/input)
                                        +-- generated retail code (guest engine)

external/mmx4 -------------------------------------------------> title-local RE reference only
```

The boot executable is the whole engine; this title has no code overlays. `external/psxport` is the
single shared framework checkout, and `external/mmx4` is an AGPL matching-decomp reference that never
enters psxport.

## Ownership table

| Subsystem | Responsibility | Current / target location | Entry point | Deep doc |
|---|---|---|---|---|
| External dependencies | Keep the shared psxport checkout and AGPL title reference behind explicit repository boundaries | `external/` | `external/psxport`, `external/mmx4` | `LICENSING.md` |
| Player launcher | Resolve dependencies and assets, provision, build, and launch the intended product | `run.sh`, `bootstrap.py`, `tools/run.py` | `run.sh` | `README.md` |
| Disc resolution | Select one user-supplied disc path consistently | `tools/resolve_disc.py` | `resolve_disc()` | `docs/config.md` |
| Executable provisioning | Extract and verify `SLUS_005.61` | `tools/extract_exe.py`, `tools/discdump.py` | `extract_exe.py` | `docs/references.md` |
| Recompiler input | Define retail seed/range facts and generate the ignored substrate | `game/recomp_seeds.json`, `tools/ensure_recomp.py`, `tools/verify_recomp_bootstrap.py`, `generated/` | `ensure_recomp.py` | `docs/re-frontier.md` |
| Process composition | Install the title runtime, construct the framework Game/Core, provision the executable, and enter retail boot | `game/core/main.cpp` | `main()` | `CLAUDE.md` |
| Title runtime | Own executable facts, render capabilities, guest-main dispatch, override installation, and per-Core title context | `game/core/x4_runtime.{h,cpp}`, `game/core/x4_context.{h,cpp}` | `x4::X4Runtime` | `docs/config.md` |
| Player render/cadence capabilities | Declare guest GTE as the player path and exclude native rendering and temporal interpolation | `game/core/x4_runtime.{h,cpp}` consuming psxport `RenderCapabilities` | `X4Runtime::renderCapabilities()` | `docs/project-goals.md` |
| Legacy fact bridge | Supply measured configuration/callback facts to framework algorithms not yet migrated to narrow typed APIs | `game/core/game_config.cpp`, `game/core/game_hooks.cpp`, `game/core/legacy_game_interface.h` | `legacy::measuredConfig`, `legacy::compatibilityHooks` | `CLAUDE.md` |
| Generated dispatch bridge | Name generated symbols and install retained-super wrappers | `game/core/recomp_register.cpp` | `x4_install_recomp()` | `docs/re-frontier.md` |
| Enhancement policy | Declare title CVars and suppress canon-changing behavior under oracle/SBS | `game/core/enhancements.{h,cpp}` | `x4::enh()` | `docs/behavior-map.md` |
| Widescreen projection | Publish title-owned guest projection and draw width at measured retail seams | `game/core/widescreen_controller.{h,cpp}`, `game/core/recomp_register.cpp` | `WidescreenController::publishProjection()` | `docs/plans/enhancements.md` |
| Title 2D composition | Own semantic wide placement for title-only quads and logo/menu records | target: title-owned modules beside `game/core/title_quad.{h,cpp}` | retained-super title publications | `docs/issues/0019-widescreen-title-composition-is-translated-left.md` |
| Field service | Deliver VBlank handler, pad, SPU, snapshots, and neutral presentation once per guest field | `game/core/vsync_sync.{h,cpp}` | `x4::vsync::deliver_field()` | `docs/re-frontier.md` |
| BIOS threads | Preserve retail cooperative task stacks and TCB lifecycle | `game/core/bios_threads.{h,cpp}` | `x4::bios_threads::install()` | `docs/re-frontier.md` |
| Fast loading | Complete measured direct/archive operations and omit only their loading waits | `game/core/fast_wait.{h,cpp}`, `game/core/recomp_register.cpp` | loading issuer overrides | `docs/plans/enhancements.md` |
| Player-object lens | Name measured player, camera, input, and spawn structures without guest writes | `game/core/player_object.h` | typed address/field accessors | `docs/re-player-object.md` |
| Co-op implementation | Own second-player lifecycle, P2 routing, camera, collision/combat, and checkpoint policy | target: cohesive title modules under `game/` after the player-object boundary is grounded | target: title-owned co-op composition | `docs/plans/enhancements.md` |
| Selected native body | Own the readable title white-quad initializer while retaining the generated super | `game/core/title_quad.{h,cpp}` | `title_quad::initializeWhiteLogoQuad()` | `docs/re-frontier.md` |
| Build composition | Build first-party seam/tests/product against the selected psxport checkout | `CMakeLists.txt`, `cmake/megamanx4_port.cmake` | CMake targets | `CLAUDE.md` |
| Verification | Exercise source policy, retail evidence, hermetic title seams, and linked-product temporal independence | `tests/`, `tools/verify_*.py`, `tools/re_title_quad.py` | CTest | `CLAUDE.md` |
| Atomic issue registry | Store tasks, defects, findings, and dead ends | `docs/issues/`, `tools/catalog.py` | `catalog.py` | — |
| Evidence ledgers | Store claims and instrument trust | `docs/info/`, `tools/info.py` | `info.py` | — |

## Where does new work go?

| Responsibility | Owner / target |
|---|---|
| A new executable-image or platform-HLE fact | a narrow `X4Runtime` typed interface; keep only unmigrated compatibility facts in `game_config.cpp` |
| A new player-visible renderer or cadence decision | `X4Runtime::renderCapabilities()`; generic UI filtering stays in psxport |
| A game-specific enhancement knob or suppression rule | `game/core/enhancements.*` plus `docs/config.md` and `docs/behavior-map.md` |
| A widescreen camera/projection publication | `WidescreenController` at a measured retail owner |
| Title/HUD/background wide layout | the semantic title subsystem that authors those coordinates, never the shared primitive renderer |
| Per-field host service | `x4::vsync::deliver_field()` or a cohesive service called from it |
| Load-operation behavior | `fast_wait.*`; unrelated scripted timing gets a separate owner after classification |
| Co-op state and policy | new cohesive title modules composed by `X4Runtime`, not the renderer or psxport |
| Framework-generic behavior | `external/psxport` (the shared workspace checkout); no per-game framework copy |
| AGPL-derived X4 implementation | this repository only; never psxport |
