# Codemap

Ownership and placement map for the Mega Man X4 port. Capability status belongs in
`docs/project-state.md`; product outcomes in `docs/project-goals.md`; atomic work in `docs/issues/`;
the measured evidence chain in `docs/re-frontier.md`.

A reader must be able to answer "where does a key press go?" and "who owns the frame turn while a
movie blocks?" from this file alone. Each directory owns one subsystem; each subsystem owns its
addresses, its state, and its seam to the guest.

## Architecture

```text
run.sh -> bootstrap.py -> tools/run.py
                           |
                           +-- provision authenticated SLUS_005.61 runtime image
                           +-- CMake -> megamanx4_port
                                        |
                                        +-- game/boot     X4Runtime (title policy + composition)
                                        +-- game/frame    X4FrameDriver + the per-field service
                                        +-- game/execution guest-call seam, override registry, BIOS tasks
                                        +-- game/input    pad layout facts, the input-path observer, the sequence skip
                                        +-- game/media    CD, streaming, movies, loading
                                        +-- game/render   display/GPU/cull/VRAM-rect owners
                                        +-- game/ui       title menu + logo composition
                                        +-- game/widescreen projection policy + per-Core controller
                                        +-- game/title    measured executable facts + enhancement policy
                                        |
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

## Source tree: directory -> namespace -> owner

### `game/boot/` — process composition (namespace `x4`, `x4::cli`)

| Unit | Owner | Responsibility |
|---|---|---|
| `main.cpp` | `x4::g_runtime`, `main()` | The process entry point: parse the command line, install `X4Runtime`, self-provision the executable from a disc, bring up the PSX devices, attach the control channel, enter the framework spine, report the run-end censuses |
| `command_line.{h,cpp}` | `x4::cli::Options`, `parse()`, `printUsage()` | Select help, the default executable, or one explicit path before any runtime or disc side effect; refuse an unknown option |
| `x4_runtime.{h,cpp}` | `x4::X4Runtime` | The process-lifetime title owner: the framework-facing runtime seam (render capabilities: the record path, program image, pad buffers, widescreen aspect policy), the per-`Core` context, and the registration of every native owner |
| `x4_context.{h,cpp}` | `x4::X4Context`, `context()` | The per-`Core` state every owner composes: BIOS threads, fast-wait, movie cleanup, music stream, widescreen, widened objects |

### `game/frame/` — the field turn (namespace `x4::frame`, `x4::vsync`)

| Unit | Owner | Responsibility |
|---|---|---|
| `x4_frame_driver.{h,cpp}` | `x4::frame::X4FrameDriver`, `bootPrefix()` | One retail field: the finite guest-main prefix, the preserved draw/drain suffix, and the ownership signals that keep a blocking movie, or a task that ran out of turn budget, from restarting the outer loop |
| `vsync_sync.{h,cpp}` | `x4::vsync::deliverField()`, `serveVSync()`, `yieldField()`, `registerOverrides()` | The ONE display-field service (IRQ-0 delivery, pad, SPU, snapshot, presentation commit) and the sole owner of the libetc VSync entry 0x800E4DB0 for every mode the retail body defines |

### `game/execution/` — guest execution (namespaces `x4::guest`, `x4::native_overrides`, `x4::bios_threads`)

| Unit | Owner | Responsibility |
|---|---|---|
| `guest_execution.{h,cpp}` | `x4::guest::callWithoutKnownReturn()`, `callWithRegisterReturn()`, `dispatch()` | This title's guest-call entry points: measured which entries have a known return address, and which registers must be checked before one is used as a boundary |
| `native_overrides.{h,cpp}` | `x4::native_overrides::install()` | Install the widescreen projection and the loading owners against the active authenticated image |
| `bios_threads.{h,cpp}` | `x4::bios_threads::Service`, `install()` | The BIOS cooperative-task context underneath the untouched retail scheduler: OpenTh / ChangeTh / CloseTh, the field boundary a task parks on, the per-task over-budget turn count (`spendBudgetTurn`, restarted by the task's own ChangeTh yield) and `frameInProgress()`, and the resume census |

### `game/input/` — input (namespaces `x4::pad`, `x4::input_path`, `x4::sequence_skip`)

| Unit | Owner | Responsibility |
|---|---|---|
| `pad_layout.h` | `x4::pad` constants | The two measured fixed InitPAD receive buffers and their capacities, published to the runtime and the legacy view |
| `input_path.{h,cpp}` | `x4::input_path::observeField()` | A read-only, per-delivered-field observer of every stage of a pad edge; writes nothing, inert unless the `x4-input-path` channel is on |
| `sequence_skip.{h,cpp}` | `x4::sequence_skip::SequenceSkip` | The skip rule: while Start is held in the Hunter H.Q. briefing (engine state 3, sub-state 9) the guest's Cross edge is raised every fourth field, so the retail briefing owner pages itself to its end |
| `sequence_skip_overrides.{h,cpp}` | `x4::sequence_skip::registerOverrides()` | The retail pad route `0x80012328` with the skip applied to its held/edge words after the original call, behind `x4::enh(skipCvar())` |

### `game/media/` — CD, streaming, movies, loading

| Unit | Owner | Responsibility |
|---|---|---|
| `cd_controller.{h,cpp}` | `x4::cd_controller::reset()`, `clearCommandState()`, `setMode()` | The title's one completed controller reset, the stock libcd command-state clear, and the published mode |
| `cd_control_boundary.{h,cpp}` | `x4::cd_control_boundary::blocking()`, `control()` | Route `CdControlB(Pause)` through the synchronous native CD owner; every other command keeps the existing loading/retail policy |
| `startup_cd.{h,cpp}` | `x4::startup_cd::run()`, `registerOverride()` | The finite title setup transaction at 0x80013588, without borrowing libcd's VSync polling clock |
| `stream_startup.{h,cpp}` | `x4::stream_startup::run()`, `awaitField()`, `installReadCallbacks()` | The STR/MDEC startup: start the native controller read without guest waits, publish the DMA3 callback table, and park the task on the next field |
| `stream_interrupt.{h,cpp}` | `x4::stream_interrupt::run()`, `consumeCompletedCallback()` | The libstr sector-completion boundary, retaining the original `StCdInterrupt` body |
| `movie_cleanup.{h,cpp}` | `x4::movie_cleanup::State`, `run()` | The complete retained cleanup transaction at 0x80018E50 and its exact 1+3+3 host fields, and `ownsPicture()` (`streaming()` from `stream_startup::run` until `complete()`, or a pending cleanup): the one word that says an STR movie owns the picture |
| `music_stream.{h,cpp}` | `x4::music_stream::State`, `setMode()` | The XA/BGM Setmode transition: the retained state-7 body with its VSync(3) replaced by a finite host-field yield |
| `music_cd.{h,cpp}` | `x4::music_cd::registerOverrides()`, `serveCdSync()`, `serveCdControl()` | The measured 6 -> 5 -> 1 edges of the XA/BGM machine, bound to the framework's own stock-Sony completion owners; every other caller of either leaf keeps the guest body |
| `fast_wait.{h,cpp}` | `x4::fast_wait::State`, `load_synchronously()`, `archive_cd_setup()`, `direct_cd_setup()`, `loading_presentation_wait()` | The measured direct/archive load operations, completed without their loading waits, and the scoped SDK leaves they virtualize |

### `game/render/` — render producers (namespaces `x4::display_init`, `x4::gpu_timeout`, `x4::cull`, `x4::background`, `x4::hud`, `x4::vram_rect`)

| Unit | Owner | Responsibility |
|---|---|---|
| `display_init.{h,cpp}` | `x4::display_init::initialize()` | Publish X4's two retail draw environments and display flags, omitting the nested guest VSync fence |
| `gpu_timeout.{h,cpp}` | `x4::gpu_timeout::setAlarm()` | PsyQ `set_alarm` 0x800ECB38, sourced from the native field counter instead of a guest VSync query |
| `visibility_cull.{h,cpp}` | `x4::cull::ScreenWindow`, `VisibilityCull` | The recovered retail cull predicate; `VisibilityCull::retail()` is the 4:3 box gameplay reads, the plan's box is widened only horizontally |
| `widened_objects.{h,cpp}` | `x4::cull::WidenedObjects` | The objects the widened box admits and the retail box culls; `raise()` / `lower()` lend them `on_screen = 1` for the draw pass only |
| `cull_overrides.{h,cpp}` | `x4::cull::registerOverrides()` | The four flag-writing cull sites (store the retail flag, record the widened verdict) and the object draw pass `0x80023DB8` (raise, original call, lower); the off-screen-verdict sites stay retail |
| `background_tiles.{h,cpp}` | `x4::background::WideBackground` | The tile-layer ring model and sprite writer: margin columns of the cell ring and their tile sprites, linked into the retail OT buckets |
| `background_overrides.{h,cpp}` | `x4::background::registerOverrides()` | `0x80026AA0` (draw layer) and `0x8002728C` (ring edge fill) with the retail body run first through the scoped original call |
| `hud_anchor.{h,cpp}` | `x4::hud::HudAnchor` | Moves the HUD packets a pass appended to its own screen edge by the margin |
| `hud_overrides.{h,cpp}` | `x4::hud::registerOverrides()` | `0x80024E70` (HUD pass) with the retail body run first through the scoped original call |
| `vram_rect_queue.{h,cpp}` | `x4::vram_rect::clear()`, `upload()`, `append()`, `reportCensus()` | The guest's eight-entry VRAM rectangle upload queue end to end, including its real capacity; `bandCount` / `streamAddress` are the one decode of the animation word (twenty-bit stream offset) |

### `game/ui/` — title logo composition (namespace `x4::title_quad`)

| Unit | Owner | Responsibility |
|---|---|---|
| `title_quad.{h,cpp}` | `x4::title_quad::initializeWhiteLogoQuad()` | The readable native body for the white quad that becomes the MEGAMAN logo |

### `game/widescreen/` — projection (namespace `x4`)

| Unit | Owner | Responsibility |
|---|---|---|
| `widescreen_controller.{h,cpp}` | `x4::WidescreenPolicy`, `x4::WidescreenController` | The requested presentation aspect (process-lifetime: the player's Aspect Ratio row, 4:3 while an STR plays or enhancements are suppressed) and the per-`Core` projection plan: the guest projection / draw-environment publication (retail on the record path) and the margin the cull reads, re-latched every field |

### `game/title/` — measured facts and enhancement policy (namespace `x4`, `x4::legacy`, `x4::guest`)

| Unit | Owner | Responsibility |
|---|---|---|
| `game_config.cpp` | `x4::legacy::measuredConfig()`, `measuredProgramImage()` | The measured SLUS_005.61 facts: crt0 group, disc and card keys, pad buffers, HLE windows, pacing. A zero is a measurement, not a gap |
| `game_hooks.cpp` | `x4::legacy::compatibilityHooks()` | Bounded compatibility callbacks for the framework algorithms not yet migrated: honest neutral bodies, and fail-fast for paths this port has not stood up |
| `legacy_game_interface.h` | `x4::legacy` declarations | The compatibility views above, and nothing else |
| `player_object.h` | `x4::guest::PlayerLens`, `CameraLayerLens`, `PadLens` | Typed read-only access to the measured player, camera-layer and pad structures |
| `enhancements.{h,cpp}` | `x4::enh()`, `x4::audit_declared_enhancements()`, the three CVars | The three pc_enh gates and the ONE chokepoint every enhancement read passes through; announces a knob no feature reads yet |

### `tests/`, `tools/`, `cmake/`

| Unit | Owner | Responsibility |
|---|---|---|
| `tests/test_x4_*.cpp` | one per subsystem | Hermetic seams: each links its own owner and no guest dispatcher |
| `tools/live_play.py` | the live/headless product driver | Drives a headless run over the control channel: input, front-end census, presents, captures |
| `tools/title_prompts.py` | the front-end model | Which screen is up, which button it wants, and the guest addresses it reads (checked against the owners' declarations) |
| `tools/verify.py`, `cmake/megamanx4_port.cmake` | the product gate | Configure, build and the CTest set: source policy, temporal-dependency checks, hermetic title seams |

## Who owns it

One chain per flow, hop by hop. A hop that is not in its owner's file is the defect to look for first.
Framework hops name psxport files so a reader can follow them into `external/psxport`.

### Process boot -> the first field

| Hop | Owner | What it decides |
|---|---|---|
| Command line | `x4::cli::parse()` (`game/boot/command_line.cpp`) | Help, the default executable, or one explicit path — before any runtime or disc side effect |
| Title runtime installed | `psxport_install_game(g_runtime)` (`game/boot/main.cpp`) | The runtime `Core` snapshots at construction, so this precedes the first `Game` |
| Executable provisioned | `Fs::exists` -> `disc_extract_file(kDiscExePath)` | `SLUS_005.61` from `$PSXPORT_X4_DISC`, `.env`, or a repository-root CHD |
| Devices | `gte_init` / `mdec_init` / `spu_init` / `Game::spu_audio::init` / `Game::gpu::gpu_native_init` / `Game::cd::overridesInit` / `Game::platform_hle::initBuiltins` / `Game::pad::overridesInit` | The framework's PSX devices in the measured order; `r[4] = 1`, `r[5] = 0` as the BIOS leaves them |
| Title owners installed | `X4Runtime::registerOverrides()` -> each `registerOverride(s)` (`game/boot/x4_runtime.cpp`) | Which guest addresses are native, keyed by authenticated image plus address |
| Control channel | `Game::dbg_server::attach` + `store_observe_attach` (`game/boot/main.cpp`) | Whether a client drives this run, and the frame cap it must use |
| Finite boot prefix | `X4Runtime::bootInit()` -> `x4::frame::bootPrefix()` (`game/frame/x4_frame_driver.cpp`) | Executes the measured prefix of guest main 0x80012024 once, then the host shell owns repetition |
| The loop | `native_boot_run` -> `psx::Machine::run` -> `FrameLoopShell::step` -> `psx::FieldTurn::beginField`/`endField` | Pause, watchdog and one serviced control command per field, around the title's body |

### The frame turn

| Hop | Owner | What it decides |
|---|---|---|
| One field | `X4FrameDriver::stepFrame()` (`game/frame/x4_frame_driver.cpp`) | The order of the turn: account the guest's two instructions of back-edge, service pending DMA work, re-latch presentation, then the field service, then the retail body |
| Plan re-latch | `X4Runtime::createFrameDriver`'s `synchronizePresentation` -> `WidescreenController::synchronizePresentation()` | Re-reads the aspect policy so the cull margin is 0 while an STR plays and wide again when the stream releases |
| The field itself | `x4::vsync::deliverField()` (`game/frame/vsync_sync.cpp`) | IRQ-0 delivery (with the counter advance as the proof it happened), pad service, SPU advance, snapshot tick, presentation commit — once per field |
| The retail body | `runRetailFramePrefix` / `kUpdateTasks` / `runRetailFrameSuffix` | The preserved draw prefix, the retail task entry, and the drain/finish suffix, each a guest call through `x4::guest::callWithoutKnownReturn` |
| A guest call that outlives its turn | `psx::cpu::ResumableGuestCall` via `x4::guest::dispatch` | The boundary latched into `r[31]`; one display field per segment; refusals name the owner |
| The run's measure of those calls | `Core::guestCallCensus().log()` (`game/boot/main.cpp`, run end) | Completed, resumed, deepest turn, with denominators |

### Host input -> pad -> guest buffer

| Hop | Owner | What it decides |
|---|---|---|
| SDL events | `psx::input::HostInput::drainEvents` (psxport) | The ONE drain of the event queue |
| Key/controller state | `HostInput::poll` (psxport) | The active-low PSX mask for this turn |
| Debug edges | `HostInput::takePauseRequest` / `takeFrameStepRequest` -> `DbgServer` (psxport) | The key is detected here; the action stays in the control channel |
| Effective mask | `Pad::pollHostInput` -> `Pad::serviceFrame` (psxport) | Force / hold, REPL drive, host suppression, session record-replay; edges latched last |
| The frame's service point | `x4::vsync::deliverField` -> `c->game->pad.serviceFrame()` | The exact point in the turn the pad is read, and the same point the observer brackets |
| Stage-by-stage evidence | `x4::input_path::observeField()` before and after the service (`game/input/input_path.cpp`) | The REPL mask, the resolved mask, the BIOS-pad gate and the guest packet buffer, once per delivered field; writes nothing |
| Sequence skip | `x4::sequence_skip::SequenceSkip` via `sequence_skip_overrides` (`game/input/`) | Which guest pad words the briefing sees while Start is held |
| Guest buffers | `x4::pad::kSlot0Buffer` / `kSlot1Buffer` -> `X4Runtime::guestPadBufferLayout()` (`game/input/pad_layout.h`, `game/boot/x4_runtime.cpp`) | Which two fixed buffers the framework's 4-byte packet lands in |
| Control-channel input | `DbgServer` command -> `Pad::driveTap` (psxport), applied by `tools/live_play.py` | An offered edge, replayable, so a headless run can exercise the same path a player drives |

### Movies

| Hop | Owner | What it decides |
|---|---|---|
| Movie start-up | `x4::stream_startup::run()` at 0x80018788 (`game/media/stream_startup.cpp`) | Starts the native controller read, publishes the DMA3 callback table, and parks the task with `awaitField` rather than a guest VSync wait |
| While a movie blocks | `X4FrameDriver::stepFrame()` + `movie_cleanup::State::pending()` + `Game::cd::stream_active` | The frame driver does NOT replay the 16-bit gameplay draw prefix while a movie owns the picture; only the blocked task transaction is resumed. `stream_startup::run` sets `movie_cleanup::State::streaming()`; `Game::cd::stream_active` is the CD pump's word and also covers XA/BGM, so it is not read for this |
| While a task is mid-frame | `X4FrameDriver::stepFrame()` + `bios_threads::Service::frameInProgress()` | A task parked on an exhausted turn budget is still inside retail's UpdateTasks, so the next field runs only the field service and UpdateTasks, and the tail waits for the field in which the task ends its frame |
| Picture | psxport record path (`gpu_vk_record_present.cpp`) | A 24-bit STR display is shown from the device VRAM the MDEC LoadImage slices wrote; `WidescreenPolicy::presentationAspect` holds it at 4:3 |
| Movie skip | This title has NO movie-skip owner: the pad is served by `deliverField` once per field for the whole run, movie included, and `tools/live_play.py` offers the pad edges. A skip rule would have to live in `game/media/movie_cleanup.*` or `game/frame/` | — |
| Cleanup transaction | `x4::movie_cleanup::run()` at 0x80018E50 (`game/media/movie_cleanup.cpp`) | The retained stack/call/state sequence plus its three finite host-field fences, released on the same field policy the frame driver uses |
| CD release | `x4::cd_control_boundary::blocking()` at 0x800E5FF4 | `CdControlB(Pause)` crosses to the synchronous native CD owner; every other command keeps the existing policy |

### CD, streaming and loading

| Hop | Owner | What it decides |
|---|---|---|
| Setup transaction | `x4::startup_cd::run()` (`game/media/startup_cd.cpp`) | The finite controller setup at 0x80013588, reaching the non-wait guest behaviour by address through the dynarec |
| Controller state | `x4::cd_controller::{reset,clearCommandState,setMode}` (`game/media/cd_controller.cpp`) | The one completed reset, the libcd command-state clear and the published mode, shared by startup, STR startup and movie cleanup |
| Load operation | `x4::fast_wait::load_synchronously` (+ `archive_cd_setup` / `direct_cd_setup`) (`game/media/fast_wait.cpp`) | The measured issuer initialization, then consecutive raw sectors fed to the measured guest callback, with no loading presentation |
| Loading presentation | `x4::fast_wait::loading_presentation_wait` at 0x80013530 | Removed with the enhancement on; the authenticated guest body remains the authority when it is off |
| Streaming read | `x4::stream_interrupt::run()` / `consumeCompletedCallback()` (`game/media/stream_interrupt.cpp`) | The sector-completion boundary, retaining `StCdInterrupt` and keeping its timeout loop from re-querying a completed command |
| XA/BGM steps | `x4::music_cd::serveCdSync` / `serveCdControl` (`game/media/music_cd.cpp`) | The measured 6 -> 5 -> 1 edges, completed through the framework's stock-Sony owners |
| XA/BGM Setmode | `x4::music_stream::setMode` (`game/media/music_stream.cpp`) | The state-7 body with its VSync(3) replaced by three host fields |

### Guest draw -> presentation

| Hop | Owner | What it decides |
|---|---|---|
| Render path | `X4Runtime::renderCapabilities()` (`game/boot/x4_runtime.cpp`) | `RenderPath::Record`: the device's GP0 work replayed from the frame record; this 60 Hz title pulls in no native producer, no interpolation and no native depth |
| Projection | `x4::WidescreenPolicy::presentationAspect` + `WidescreenController::publishProjection` / `publishDrawEnvironment` (`game/widescreen/widescreen_controller.cpp`) | The guest OFX / draw-environment width from the framework plan, written through the measured retail owners with an original call; retail 160 / 320 on the record path |
| Coverage | `x4::cull::WidenedObjects` via `cull_overrides` (`game/render/`) | Which extra objects the guest's own draw pass may see: retail `on_screen` stays what gameplay reads, the widened-only objects are raised for `0x80023DB8` alone |
| Background | `x4::background::WideBackground` via `background_overrides` (`game/render/`) | The tile columns the margins show, drawn after each retail layer pass |
| HUD | `x4::hud::HudAnchor` via `hud_overrides` (`game/render/`) | The gauge packets, moved to the screen edge they hug at 4:3 |
| Margins | psxport `RecordRasterizer` canvas (`gpu_vk_record_raster.cpp`), margin from `gpu_vk_latch_record_display` | What the guest draws outside its 320-column buffer lands in the canvas margins; guest 2D stays as drawn, centred |
| VRAM uploads | `x4::vram_rect::{clear,upload,append}` (`game/render/vram_rect_queue.cpp`) | The guest's rectangle queue, including its real capacity |
| Present | `deliverField` -> `c->game->presentation.commit(c, 1)` | Capture, present, pacing and ledger rotation at one display field per step |

### Audio

| Hop | Owner | What it decides |
|---|---|---|
| Mixing | `deliverField` -> `Game::spu_audio::frame()` | Exactly one field of samples mixed per delivered field |
| Device | `psxport` SpuAudio sink; `PSXPORT_NOAUDIO` / `PSXPORT_WAV` select the sink | Where the samples go; this title owns no audio mixing policy |
| CD-side music | `x4::music_cd` and `x4::music_stream` (`game/media/`) | The CD commands and state transitions behind XA/BGM playback |

### The debug / control channel

| Hop | Owner | What it decides |
|---|---|---|
| Attachment | `Game::dbg_server::attach(c, cfg_int("PSXPORT_NATIVE_FRAMES", 0))` (`game/boot/main.cpp`) | Whether a client drives the run, on loopback, before the frame loop starts |
| Per-field service | `psx::FieldTurn::beginField` / `endField` (psxport, via `native_boot_run`) | Pause, watchdog re-arm, one serviced command per field |
| Commands | `psxport`'s `DbgServer` (runtime/psx/debug/) | Reads, writes, `frame`, `pause`, `tap`, `cvars`, `quit` |
| The live driver | `tools/live_play.py` + `tools/title_prompts.py` | Input edges, front-end census, frame captures, and the census's own denominators |
| Store observation | `store_observe_attach` (psxport, armed by this title's spine) | Which guest word was written, with the store's own PC |
| Title debug options | none: `x4::legacy::compatibilityHooks()` `devWarp` is a fail-fast stub, because this title has no debug warp | A future warp would be a title-owned module here, not a framework hook |

## Where does new work go?

| Responsibility | Owner / target |
|---|---|
| A new executable-image or platform-HLE fact | a narrow `X4Runtime` typed interface; only unmigrated compatibility facts stay in `game/title/game_config.cpp` |
| A new guest instruction semantic, machine synchronization, bounded exit or invalidation | `external/psxport` |
| A new native function owner | a module in the directory that owns its subsystem, plus the image-and-address-keyed override registry; call the original guest body through psxport's scoped original-call API |
| A new per-field host service | `x4::vsync::deliverField` — it is the only per-field service, and `X4FrameDriver` composes it |
| A new player-visible renderer or cadence decision | `X4Runtime::renderCapabilities()`; generic UI filtering stays in psxport |
| A HUD element that must move at 16:9 | `x4::hud::HudAnchor` (`game/render/hud_anchor.*`) for the HUD pass; any other element gets its own anchored producer (psxport `presentation.md`, Widescreen), never a layout hook that shifts guest 2D |
| A background or object draw that must reach the 16:9 margins | `game/render/background_tiles.*` for tiles, `widened_objects.*` for objects; the retail value gameplay reads stays untouched |
| A game-specific enhancement knob or suppression rule | `game/title/enhancements.*` plus `docs/config.md` and `docs/behavior-map.md` |
| A widescreen projection publication | `WidescreenController`, at a measured retail owner |
| Finite startup CD/controller setup | `game/media/startup_cd.*`; later load operations belong to `fast_wait.*` and never to the frame driver |
| A blocking movie-stream release | `cd_control_boundary.*` owns only `CdControlB(Pause)`; `movie_cleanup.*` owns the whole caller transaction and its fields |
| Completed title CD reset/mode state | `cd_controller.*`; callers keep their own sequencing and field policy |
| Load-operation behavior | `fast_wait.*`; unrelated scripted timing gets its own owner after classification |
| Co-op state and policy | new modules under `game/input/` and `game/title/player_object.h` consumers, composed by `X4Runtime` — not the renderer and not psxport |
| Framework-generic behavior | `external/psxport`; no per-game framework copy |
| AGPL-derived X4 implementation | this repository only, never psxport (`LICENSING.md`) |
| A post-movie motion / picture measurement | `tools/live_play.py` — the frame driver never answers this |
| A guest disassembly or address reading | `llvm-objdump` over the text bytes, plus `external/mmx4/config/symbols.us.txt` for names. **Not Ghidra**: its `MIPS:BE:32:default` sleigh decodes this image wrongly (measured), so an instrument built on it renders `addiu` as `ldc2` |
| "WHICH instruction writes this guest word" | decode it statically: a MIPS store is ONE word (`op(6) base(5) rt(5) imm(16)`), so a scan needs no dataflow and no control flow. `PSXPORT_STORE_OBSERVE` is the runtime witness and wants the store's own PC | `docs/issues/0035-the-faulting-store-is-attributed-and-a-native-owner-bounds-the-queue.md` |

## Deep docs

| Area | Document |
|---|---|
| Enhancement knobs and their divergence | `docs/config.md`, `docs/behavior-map.md` |
| Player-object structures and the co-op boundary | `docs/re-player-object.md` |
| Disc, decomp and image identity | `docs/references.md` |
| Measured evidence chain | `docs/re-frontier.md` |
