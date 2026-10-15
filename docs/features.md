# Features — Mega Man X4

Title hops only. Each row is where X4 joins a psxport feature hop (`psxport F-X.n`); a feature with
no row runs on the framework alone.

## F-BOOT

| hop | joins | owner |
|---|---|---|
| 1 | psxport F-BOOT.1 | `game/runtime/catalog.cpp:createCatalog` — `SLUS_005.61` identity, `PSXPORT_X4_DISC`, and one `x4::Runtime` |
| 2 | psxport F-BOOT.5 | `game/runtime/runtime.cpp:x4::Runtime::startProgram` — crt0 (`kCrt0`), then `frame::bootPrefix`, the measured prefix of guest main `0x80012024` |
| 3 | psxport F-BOOT.6 | `game/runtime/runtime.cpp:x4::Runtime::registerOverrides` — binds `StockVSync` (`0x800E4DB0`, counter `0x8011DC50`; `vsync::serveVSync` owns the entry and answers VSync(<0) through it), `StockDmaCallbacks` (`0x8011DC5C`), `StockLibcd` and the BIOS task service, then every native override |
| 4 | psxport F-BOOT.6 | `game/runtime/session.h:x4::Session` — per-Core BIOS tasks, fast-wait, movie cleanup, music stream, widescreen, sequence skip, stage warp |

## F-TURN

| hop | joins | owner |
|---|---|---|
| 1 | psxport F-TURN.2 | `game/frame/frame_driver.cpp:x4::frame::FrameDriver::stepFrame` — an armed warp, then the field service and the retail draw prefix, `UpdateTasks`, suffix |
| 2 | psxport F-TURN.2 | `game/frame/vsync_sync.cpp:deliverField` — IRQ-0, pad, SPU, snapshot and presentation commit once per field |
| 3 | psxport F-TURN.3 | `game/execution/bios_threads.cpp:Service` — OpenTh/ChangeTh/CloseTh under the untouched retail scheduler |
| 4 | psxport F-TURN.4 | `game/runtime/runtime.cpp:x4::Runtime::reportRun` — VRAM-rect queue and task-turn censuses |

## F-INPUT

| hop | joins | owner |
|---|---|---|
| 1 | psxport F-INPUT.1 | `game/runtime/runtime.cpp:x4::Runtime::deliverPad` — `StockPadBuffers` at `0x80166D68`/`0x8012F46C` |
| 2 | psxport F-INPUT.1 | `game/input/sequence_skip_overrides.cpp:registerOverrides` — Start held in the Hunter H.Q. briefing raises the guest's Cross edge |

## F-CD

| hop | joins | owner |
|---|---|---|
| 1 | psxport F-CD.1 | `game/runtime/runtime.cpp:x4::Runtime` — `StockLibcd`; `x4::stockCdSync`/`stockCdControl` are its bodies for the title wrappers |
| 2 | psxport F-CD.1 | `game/media/fast_wait.cpp:load_synchronously` — each measured load completes in one call, no loading screen |
| 3 | psxport F-CD.1 | `game/media/stream_startup.cpp:run` — the STR read, completed through the DMA-3 entry of `StockDmaCallbacks` |

## F-WIDE

| hop | joins | owner |
|---|---|---|
| 1 | psxport F-WIDE.1 | `game/widescreen/widescreen_controller.cpp:WidescreenPolicy` — the player's aspect, 4:3 while an STR plays |
| 2 | psxport F-WIDE.2 | `game/render/cull_overrides.cpp:registerOverrides` — objects in the margin drawn; gameplay's on-screen byte stays retail |
| 3 | psxport F-WIDE.2 | `game/render/background_overrides.cpp:registerOverrides` — margin tile columns |
| 4 | psxport F-WIDE.2 | `game/render/hud_overrides.cpp:registerOverrides` — HUD packets moved to their screen edge |

## F-SAVE

| hop | joins | owner |
|---|---|---|
| 1 | psxport F-SAVE.1 | `game/runtime/runtime.cpp:x4::Runtime::hostIdentity` — card `PSXPORT_X4_CARD` (`scratch/saves/megamanx4.mcr`), user data under `megamanx4` |

## F-DEBUG

| hop | joins | owner |
|---|---|---|
| 1 | psxport F-DEBUG.1 | `game/runtime/runtime.cpp:x4::Runtime::titleCommand` — `warp <stage> [part]` |
| 2 | psxport F-DEBUG.1 | `game/debug/stage_warp.cpp:StageWarp::applyArmed` — engine state 4 with the stage and part, applied by the frame driver at a frame boundary |
| 3 | psxport F-DEBUG.2 | `game/debug/stage_warp.cpp:StageWarp` — the picker's 13 stages, legal while a stage is running |
