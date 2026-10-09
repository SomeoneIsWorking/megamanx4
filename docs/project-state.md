# Project state

Factual capability coverage for the Mega Man X4 enhancement port. Epic intent lives in
`docs/project-goals.md`, ownership in `docs/codemap.md`, open defects and missing features in
`docs/issues/`, and the reverse-engineering step chain in `docs/re-frontier.md` (read through
`tools/re_frontier.py`).

| ID | Capability | State | Evidence or gap |
|---|---|---|---|
| S001 | USA executable and disc inputs are reproducibly identified and provisioned | verified | `tools/extract_exe.py` + `tools/resolve_disc.py` identify `SLUS_005.61`, SHA-1 `213733031136d095ca275d6957695aa25011cfa5`; no game bytes tracked |
| S002 | The authenticated resident image runs through the native/Lightrec gameplay product | partial | A 30,000-present headless run at `ires=1` exits 0: boot, both STR movies, the title, the title menu, Start through player select, the opening STR movie (skipped by Start), the Hunter H.Q. briefing and the first stage all run through the shipping dispatcher; the attract demo also loops back into the movies. Open: stages other than the first are unreached, and `task_resume_evidence` (excluded from `tools/verify.py`'s test regex) has not been re-measured since the post-movie phase became reachable |
| S003 | Guest field service delivers retail timing, input, and audio work | partial | One field, class-0 dispatch, pad, SPU, snapshot and presentation commit per field; movie cleanup, BGM Setmode and the XA/BGM `CdSync` edges are owned; a task that runs out of turn budget keeps the retail frame open (no draw prefix or tail until it ends the frame), so a frame costing more than a field presents at the retail cadence instead of a half-built ordering table. Pad taps drive the title, menu and stage over the control channel. The memory-card callers and audio during gameplay are unproven |
| S004 | The native/Lightrec product boots and presents the retail front end on the record path | partial | Verified at `ires=1`, `aspect=0`: title, title menu (GAME START / CONTINUE / OPTION), player select, the Hunter H.Q. briefing and the first stage present correct pictures, and a 17,500-present run has 3,806 `recordcheck` lines, all `mismatched=0` (2026-10-09). Open: above `ires=1`, which is what Auto selects, the record picture is corrupt (`docs/issues/0040`); sprite assembly (`docs/issues/0026`) |
| S005 | Player-visible renderer and cadence choices match the title's actual capabilities | verified | `X4Runtime::renderCapabilities()` selects `RenderPath::Record` with no native renderer and no interpolation (`tests/test_x4_runtime.cpp`); the menu exposes no native-renderer or 60fps-interpolation control |
| S006 | Title-owned widescreen composes correct 16:9 title and gameplay pictures | partial | Record path: guest OFX/RECT.w stay 160/320, the cull widens by 54 and the canvas presents 428x240 (`tests/test_x4_runtime.cpp`, psxport `test_guest_widescreen_projection`). Presents 1,284-1,290 at 16:9 equal the 4:3 picture centred with black margins, pixel-identical to the old GTE-path 16:9 capture; no frame with 3D, HUD or gameplay is reachable, and XA BGM holds 4:3 (`docs/issues/0037`, `0038`); the generic Aspect Ratio row does not drive the title policy (`docs/issues/0024`) |
| S007 | Measured loading operations complete without loading-only waits or presentation | partial | Direct/archive owners complete real-disc requests through their retail setup bodies with no guest VSync, including the stage and briefing loads reached on 2026-10-09; destination-byte comparison and captured absence of loading presentation remain open, and unrelated scripted waits and fades are unclassified |
| S008 | A second player can join as the other hunter | missing | Two pads decode and the player/camera/spawn pillars are mapped (`docs/re-player-object.md`), but no second player object, P2 route, camera policy, mid-stage join, or co-op correctness gate exists |
| S009 | Representative gameplay is verified playable end to end | partial | At `ires=1`, a headless session driven by pad taps reaches the first stage with X: holding right moves the player x from 0x0C8 to 0x161 to 0x21E and a jump is drawn (shots `stage_idle`, `stage_right`, `stage_jump`); `recordcheck` stays `mismatched=0`. Audio, saves, loading removal and widescreen are not demonstrated together, and only the first stage is reached |
| S010 | Asset-free hosted verification builds and checks the real supported host product boundary | verified | `tools/verify.py` over the Linux x86_64 product, run in CI (`.github/workflows/ci.yml`); composition only. Windows, macOS and Android remain unsupported hosts, not green jobs |

## Current focus

S004/S009: gameplay beyond the first stage and the record picture above `ires=1`.

- The post-movie phase is reachable: Start from the title opens the menu, Start again opens player select, a
  third Start picks X and plays the opening movie, Start skips it, and Cross taps move through the Hunter H.Q.
  dialogue into the first stage. No title-owned warp option was needed.
- Next: `docs/issues/0040` (corrupt record picture at `ires` above 1; Auto resolves to 3 on the headless sink),
  then the stage select and later stages, then `task_resume_evidence`, whose premise (a window with no budget
  resumes) is now measurable because task `0x8001DAF8` resumes across budget turns at normal frame cost.
- Retired blockers (2026-10-09): the libstr ring refill (psxport `cdc_native.cpp`, Pause kept an announced
  sector), the `0x0113D7D0` dispatch and the SysEnq verifier crash (issue 0036; a twenty-bit stream offset
  read through a sixteen-bit mask in `vram_rect_queue`), the black post-movie picture (issue 0038; a BGM
  `ReadS` was treated as an STR movie), the 512-field guard firing on frames that merely exceed a field
  (`bios_threads::Service::spendBudgetTurn`) and the half-built ordering table presented while a task was
  mid-frame (`X4FrameDriver::stepFrame`).
