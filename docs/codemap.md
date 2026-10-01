# Codemap

Ownership and placement map for the Mega Man X4 port. Capability status belongs in
`docs/project-state.md`; product outcomes in `docs/project-goals.md`; atomic work in `docs/issues/`.

## Architecture

```text
run.sh -> bootstrap.py -> tools/run.py
                           |
                           +-- provision authenticated SLUS_005.61 runtime image
                           +-- CMake -> megamanx4_port
                                        |
                                        +-- game/core/X4Runtime (title policy + composition)
                                        +-- psxport FrameLoopShell -> X4FrameDriver (one retail field)
                                        +-- external/psxport (platform/runtime/render/audio/input)
                                        +-- psxport/Lightrec executor (remaining guest code)
                                        +-- image-aware native overrides + original calls

separate test target -> independent oracle (never linked or selectable by the gameplay product)

external/mmx4 -------------------------------------------------> title-local RE reference only
```

The boot executable is the whole engine; this title has no code overlays. `external/psxport` is the
single shared framework checkout, and `external/mmx4` is an AGPL matching-decomp reference that never
enters psxport.

## Ownership table

| Subsystem | Responsibility | Current / target location | Entry point | Deep doc |
|---|---|---|---|---|
| External dependencies | Keep the shared psxport checkout and AGPL title reference behind explicit repository boundaries | `external/` | `external/psxport`, `external/mmx4` | `LICENSING.md` |
| Player launcher | Resolve dependencies and assets, provision the authenticated runtime image, build, and launch the intended native/Lightrec product | `run.sh`, `bootstrap.py`, `tools/run.py` | `run.sh` | `README.md` |
| Disc resolution | Select one user-supplied disc path consistently | `tools/resolve_disc.py` | `resolve_disc()` | `docs/config.md` |
| Executable provisioning | Extract and verify `SLUS_005.61` | `tools/extract_exe.py`, `tools/discdump.py` | `extract_exe.py` | `docs/references.md` |
| Product command line | Select help, default executable, or one explicit executable path before any runtime/disc side effect; refuse unknown options | `game/core/command_line.{h,cpp}` | `x4::cli::parse()`, `x4::cli::printUsage()` | `README.md` |
| Runtime executable image | Authenticate, load, and expose the resident image as runtime data without emitting guest code | target: `tools/extract_exe.py`, title identity facts, psxport `GuestProgramImage` | `extract_exe.py`, `X4Runtime::guestProgramImage()` | `docs/issues/` |
| Process composition | Install the title runtime and native override table, construct the per-Core Lightrec executor and framework devices, provision the executable, and enter retail boot | target: `game/core/main.cpp` plus shared psxport executor API | `main()` | `CLAUDE.md` |
| Dynamic executor | Translate every non-native guest instruction at runtime, synchronize canonical machine state at service boundaries, invalidate changed executable memory, and make bounded exits explicit | target: shared `external/psxport` Lightrec integration; Lightrec retains its own cache/code memory | target: per-`Core` psxport executor | `docs/issues/` |
| Title runtime | Own executable facts, render capabilities, finite guest-main initialization, image-aware override installation, scoped original calls, and per-Core title context | target: `game/core/x4_runtime.{h,cpp}`, `game/core/x4_context.{h,cpp}`, cohesive native-override registry | `x4::X4Runtime` | `docs/config.md` |
| Frame driver | Execute the measured finite `0x80012024` prefix once, own one VSync-free retail field, and preserve a blocking movie's `UpdateTasks` suspension without restarting gameplay clear/draw work | `game/core/x4_frame_driver.{h,cpp}` | `X4Runtime::createFrameDriver()`, `X4FrameDriver::stepFrame()` | `docs/issues/` |
| Pad receive-buffer facts | Publish the two measured fixed InitPAD buffers to the direct runtime and legacy compatibility view | `game/core/pad_layout.h`, `game/core/x4_runtime.cpp`, `game/core/game_config.cpp` | `X4Runtime::guestPadBufferLayout()` | `docs/issues/` |
| Startup CD transaction | Complete title setup `0x80013588` without borrowing libcd's VSync polling clock, while reaching the original non-wait guest behavior by address through the dynarec | target: `game/core/startup_cd.{h,cpp}` plus psxport original-call API | `startup_cd::run()`, `startup_cd::registerOverride()` | `CLAUDE.md` |
| Native CD controller state | Own the title's one completed controller reset, stock libcd command-state clear, and mode publication used by startup, STR startup, and movie cleanup | `game/core/cd_controller.{h,cpp}` | `cd_controller::reset()`, `clearCommandState()`, `setMode()` | `CLAUDE.md` |
| Blocking CD control boundary | Route title `CdControlB(Pause)` through the synchronous native CD owner while preserving every non-Pause policy through an address-based original call | target: `game/core/cd_control_boundary.{h,cpp}` plus native override/original-call binding | `cd_control_boundary::blocking()` at `0x800E5FF4` | `CLAUDE.md` |
| XA/BGM CD step ownership | Own the state machine reached through the image's own jump table at `0x800F1AB0`: bind the stock libcd `CdSync` leaf `0x800E5D20`, and the `CdControl` step commands at `0x800E5D90` for the measured 6→5→1 edges, to the framework's stock-Sony completion owners. Every other caller of either leaf keeps the original guest body | `game/core/music_cd.{h,cpp}`, registered from `game/core/native_overrides.cpp` | `music_cd::registerOverrides()`, `serveCdSync()`, `serveCdControl()` | `docs/issues/0029-the-post-movie-park-is-an-unowned-stock-libcd-cdsync-leaf.md` |
| Movie cleanup transaction | Preserve the complete retained `0x80018E50` stack/call/state sequence while owning its Pause/reset/Setmode completion and exact 1+3+3 host fields | `game/core/movie_cleanup.{h,cpp}`, `game/core/x4_frame_driver.cpp` | `movie_cleanup::run()`, `movie_cleanup::State` | `CLAUDE.md` |
| GPU timeout deadline | Translate PsyQ set_alarm `0x800ECB38` to the native-owned field counter without a guest VSync query | target: `game/core/gpu_timeout.{h,cpp}` plus psxport original-call binding | `gpu_timeout::setAlarm()` | `CLAUDE.md` |
| Display initialization | Publish X4's two retail draw environments and display flags without its nested guest VSync fence; execute the original body by address where required | target: `game/core/display_init.{h,cpp}` plus psxport original-call binding | `display_init::initialize()` | `CLAUDE.md` |
| STR startup and sector completion | Start the native controller read without guest waits, retain `StCdInterrupt`, and publish the measured per-channel DMA3 callback table that promotes completed libstr ring entries | `game/core/stream_startup.{h,cpp}`, `game/core/stream_interrupt.{h,cpp}`, `game/core/game_config.cpp` | `stream_startup::run()`, `stream_startup::installReadCallbacks()`, `stream_interrupt::run()` | `CLAUDE.md` |
| Player render/cadence capabilities | Declare guest GTE as the player path and exclude native rendering and temporal interpolation | `game/core/x4_runtime.{h,cpp}` consuming psxport `RenderCapabilities` | `X4Runtime::renderCapabilities()` | `docs/project-goals.md` |
| Legacy fact bridge | Supply measured configuration/callback facts to framework algorithms not yet migrated to narrow typed APIs | `game/core/game_config.cpp`, `game/core/game_hooks.cpp`, `game/core/legacy_game_interface.h` | `legacy::measuredConfig`, `legacy::compatibilityHooks` | `CLAUDE.md` |
| Native override dispatch | Key native owners by authenticated image plus guest address, provide scoped dynarec original calls, and invalidate captured decisions when overrides change | target: cohesive title registry under `game/core/` consuming the psxport executor API | target: `X4Runtime` override installation | `docs/issues/` |
| Enhancement policy | Declare title CVars and suppress canon-changing behavior under oracle/SBS | `game/core/enhancements.{h,cpp}` | `x4::enh()` | `docs/behavior-map.md` |
| Widescreen projection | Publish title-owned guest projection/draw width and re-latch 4:3 presentation while a pre-rendered STR owns the picture | `game/core/widescreen_controller.{h,cpp}`, `game/core/native_overrides.cpp`, `game/core/x4_frame_driver.cpp` | `WidescreenController::publishProjection()`, `synchronizePresentation()` | `docs/project-goals.md` |
| Title 2D composition | Own semantic wide placement for title-only quads and logo/menu records | target: title-owned modules beside `game/core/title_quad.{h,cpp}` | address-based native overrides and original calls | `docs/issues/0019-widescreen-title-composition-is-translated-left.md` |
| Field service | Deliver the current VBlank handler, pad, SPU, snapshots, and neutral presentation once per native-owned field | `game/core/vsync_sync.{h,cpp}` | `x4::vsync::deliverField()` | `docs/issues/` |
| Input-path observer | Sample every stage of a pad edge ONCE PER DELIVERED FIELD — the REPL mask, the resolved effective mask, the framework's BIOS-pad gate, and the guest's own libpad packet and decoded trio — from inside the field loop, and write nothing | `game/core/input_path.{h,cpp}`, bracketing `Pad::serviceFrame()` in `x4::vsync::deliverField` | `x4::input_path::observeField()`, channel `x4-input-path` | `docs/re-player-object.md` |
| libetc VSync entry `0x800E4DB0` | Serve **all 42 callers** of the retail entry from the body read out of the image: a negative mode is a query of the measured VBlank counter `0x8011DC50`, mode `n` is `fieldsForMode(n)` host fields, and the return value and the entry's two state words are reproduced. Its own image-scoped override makes it the only answer that address gets | `game/core/vsync_sync.{h,cpp}` | `x4::vsync::serveVSync()`, `x4::vsync::registerOverrides()`, `x4::vsync::yieldField()` | `CLAUDE.md` |
| BIOS threads | Preserve retail cooperative task stacks and TCB lifecycle | `game/core/bios_threads.{h,cpp}` | `x4::bios_threads::install()` | `docs/issues/` |
| Fast loading | Complete measured direct/archive operations and omit only their loading waits | `game/core/fast_wait.{h,cpp}`, `game/core/native_overrides.cpp` | loading issuer overrides | `docs/project-goals.md` |
| Player-object lens | Name measured player, camera, input, and spawn structures without guest writes | `game/core/player_object.h` | typed address/field accessors | `docs/re-player-object.md` |
| Co-op implementation | Own second-player lifecycle, P2 routing, camera, collision/combat, and checkpoint policy | target: cohesive title modules under `game/` after the player-object boundary is grounded | target: title-owned co-op composition | `docs/project-goals.md` |
| Selected native body | Own the readable title white-quad initializer while preserving an address-based original call for differential evidence | target: `game/core/title_quad.{h,cpp}` plus psxport override/original-call binding | `title_quad::initializeWhiteLogoQuad()` | `docs/issues/` |
| VRAM rectangle queue | Own the guest's eight-entry upload queue end to end — clear, upload, and the band appender — and supply the array's real capacity at the two stores the guest leaves unbounded. The RLE decompressor and the BIOS `LoadImage` stay guest calls; this owner owns what the queue DOES with the results, not the formats | `game/core/vram_rect_queue.{h,cpp}`, registered from `game/core/native_overrides.cpp` | `x4::vram_rect::clear()`, `upload()`, `append()`, `reportCensus()` | `docs/issues/0035-the-faulting-store-is-attributed-and-a-native-owner-bounds-the-queue.md` |
| Build composition | Build first-party seams, tests, and the native/Lightrec product against the selected psxport checkout | target: `CMakeLists.txt`, `cmake/megamanx4_port.cmake` | CMake targets | `CLAUDE.md` |
| Verification | Exercise source policy, hermetic title seams, runtime Lightrec/override/original-call/invalidation contracts, no player-selectable interpreter mode, and bounded-fallback policy | target: `tests/`, `cmake/megamanx4_port.cmake`, `tools/verify.py` | native/Lightrec conformance gate | `CLAUDE.md` |
| Runtime-input policy | Execute the authenticated user-provided executable as runtime data and keep provisioning non-executable | CMake, launcher, and repository structure | native/Lightrec conformance gate | `docs/project-state.md` |

## Where does new work go?

| Responsibility | Owner / target |
|---|---|
| A new executable-image or platform-HLE fact | a narrow `X4Runtime` typed interface; keep only unmigrated compatibility facts in `game_config.cpp` |
| New guest instruction semantics, machine synchronization, bounded exit, or invalidation behavior | shared `external/psxport`; Lightrec owns only its embedded dynarec internals |
| A new native function owner | a cohesive title module plus the image-and-address-keyed override registry; call the original guest body through psxport's scoped dynarec original-call API |
| A new player-visible renderer or cadence decision | `X4Runtime::renderCapabilities()`; generic UI filtering stays in psxport |
| A game-specific enhancement knob or suppression rule | `game/core/enhancements.*` plus `docs/config.md` and `docs/behavior-map.md` |
| A widescreen camera/projection publication | `WidescreenController` at a measured retail owner |
| Title/HUD/background wide layout | the semantic title subsystem that authors those coordinates, never the shared primitive renderer |
| Per-field host service | `X4FrameDriver` composes `x4::vsync::deliverField()`; the shared shell adds no title service |
| Finite startup CD/controller setup | `startup_cd.*`; keep later load operations in `fast_wait.*` and do not put setup polling in the frame driver |
| Blocking movie-stream release | `cd_control_boundary.*` owns only `CdControlB(Pause)`; `movie_cleanup.*` owns the complete caller transaction and its seven fields |
| Completed title CD reset/mode state | `cd_controller.*`; callers preserve their distinct sequencing and field policy |
| A stock libcd leaf the framework's config-shaped `PlatformHle` does not bind (`CdSync` has no binding in that shape at all) | `music_cd.*` for the XA/BGM state machine, composing the framework's own `cd_sync_stock_sync` / `cd_control_sync`; never a re-implementation of CD policy. Broadening that shape's bindings belongs in `external/psxport`, not here |
| Load-operation behavior | `fast_wait.*`; unrelated scripted timing gets a separate owner after classification |
| Co-op state and policy | new cohesive title modules composed by `X4Runtime`, not the renderer or psxport |
| Framework-generic behavior | `external/psxport` (the shared workspace checkout); no per-game framework copy |
| AGPL-derived X4 implementation | this repository only; never psxport |
| A post-movie motion / picture measurement | `tools/live_play.py` — it drives a headless run and reads the control channel's frames; the frame driver never answers this |
| A guest disassembly or address reading | `llvm-objdump` over the text bytes, plus `external/mmx4/config/symbols.us.txt` for names. **Not Ghidra**: its `MIPS:BE:32:default` sleigh decodes this image wrong (measured), so an instrument built on it would render `addiu` as `ldc2` |
| "WHICH instruction writes this guest word" | decode it statically — a MIPS store is ONE word (`op(6) base(5) rt(5) imm(16)`), so a scan needs no dataflow and no control flow and is exhaustive over direct stores. **`PSXPORT_WWATCH` cannot answer it**: the built Lightrec emits translated stores to main RAM as direct host writes that never reach `Core::mem_w32`, and its `pc`/`ra` are the executor segment boundary, not the store's site. `PSXPORT_STORE_OBSERVE` is the runtime witness, and it wants the store's own PC, never a data address | `PSXPORT_STORE_OBSERVE=<store PCs>` | — | `docs/issues/0035-the-faulting-store-is-attributed-and-a-native-owner-bounds-the-queue.md` |
