# Project state

Factual capability coverage for the Mega Man X4 enhancement port. Epic intent lives in
`docs/project-goals.md`, ownership in `docs/codemap.md`, open defects and missing features in
`docs/issues/`, and the reverse-engineering step chain in `docs/re-frontier.md` (read through
`tools/re_frontier.py`).

| ID | Capability | State | Evidence or gap |
|---|---|---|---|
| S001 | USA executable and disc inputs are reproducibly identified and provisioned | verified | `tools/extract_exe.py` + `tools/resolve_disc.py` identify `SLUS_005.61`, SHA-1 `213733031136d095ca275d6957695aa25011cfa5`; no game bytes tracked |
| S002 | The authenticated resident image runs through the native/Lightrec gameplay product | partial | Boot, both STR movies and the archive loads complete through the shipping dispatcher, but a run still stops on a guest dispatch to the non-guest word `0x0113D7D0` from `kUpdateTasks` (`docs/issues/0028`, `0029`); translated-block and fallback counts unreported at the stop. `task_resume_evidence` is EXCLUDED from `tools/verify.py`'s test regex by design, so it is not covered by the green gate: run directly it reports 0 task turns resumed, because retail `DecDCTvlc` (`0x800ED574`, 1.082 fields) never appears in a run that decodes STR frames. That is "not measured", not "fine", and it is the same unreached post-movie phase S002 already records |
| S003 | Guest field service delivers retail timing, input, and audio work | partial | One field, class-0 dispatch, pad, SPU, snapshot and presentation commit per field; movie cleanup, BGM Setmode and the XA/BGM `CdSync` edges are owned; the later state 6/5/1 Setfilter/SeekL/ReadS/GetlocP chain and the memory-card callers are unproven |
| S004 | The native/Lightrec product boots and presents the retail front end on the record path | partial | Boot, both STR movies and the dark title field are presented; a 1,500-present headless run has 264 15-bit presents, all `recordcheck` mismatched=0 against the device (2026-10-07). From the XA BGM `ReadS` (between presents 1,290 and 1,295) the frame driver treats the stream as a movie and skips the retail draw prefix; presents 1,287 to 1,400 are pixel-identical (`docs/issues/0038`); the post-movie park (S002) and sprite assembly (`docs/issues/0026`) stay open |
| S005 | Player-visible renderer and cadence choices match the title's actual capabilities | verified | `X4Runtime::renderCapabilities()` selects `RenderPath::Record` with no native renderer and no interpolation (`tests/test_x4_runtime.cpp`); the menu exposes no native-renderer or 60fps-interpolation control |
| S006 | Title-owned widescreen composes correct 16:9 title and gameplay pictures | partial | Record path: guest OFX/RECT.w stay 160/320, the cull widens by 54 and the canvas presents 428x240 (`tests/test_x4_runtime.cpp`, psxport `test_guest_widescreen_projection`). Presents 1,284-1,290 at 16:9 equal the 4:3 picture centred with black margins, pixel-identical to the old GTE-path 16:9 capture; no frame with 3D, HUD or gameplay is reachable, and XA BGM holds 4:3 (`docs/issues/0037`, `0038`); the generic Aspect Ratio row does not drive the title policy (`docs/issues/0024`) |
| S007 | Measured loading operations complete without loading-only waits or presentation | partial | Direct/archive owners complete real-disc requests through their retail setup bodies with no guest VSync; destination-byte comparison and captured absence of loading presentation remain open, and unrelated scripted waits and fades are unclassified |
| S008 | A second player can join as the other hunter | missing | Two pads decode and the player/camera/spawn pillars are mapped (`docs/re-player-object.md`), but no second player object, P2 route, camera policy, mid-stage join, or co-op correctness gate exists |
| S009 | Representative gameplay is verified playable end to end | missing | No native/Lightrec session demonstrates and inspects representative stage gameplay with input, audio, saves, loading removal and widescreen together on any released host |
| S010 | Asset-free hosted verification builds and checks the real supported host product boundary | verified | `tools/verify.py` over the Linux x86_64 product, run in CI (`.github/workflows/ci.yml`); composition only. Windows, macOS and Android remain unsupported hosts, not green jobs |

## Current focus

S002: the guest's post-movie dispatch to the non-guest word `0x0113D7D0` — the remaining blocker to a
post-movie picture and therefore to gameplay evidence (S004, S009).

- `task_resume_evidence` measured 2026-10-04: the gate's premise is stale and its blocker is deeper than
  the resume. The task-turn census is now published at the run end by its owner
  (`x4::bios_threads::Service::reportCensus`, called from `game/boot/main.cpp`), and the gate's own
  200-present window reads **0 of 0 turns dispatched** — the retail task `0x8001D064` is still inside
  its first `dispatchGuest` for the whole window, so the budget path is unreached *and now measured as
  unreached* rather than absent from the log. Measured the same day against psxport as of 17:41–18:00,
  that same window was 603 turns, all field boundaries, 600 of them the STR per-field pull's retry
  continuation `0x80018BC4` at **58 guest cycles** against a 564,480-cycle host-turn budget, because the
  libstr ring never refills and `StGetNext` (`0x800E83F4`) fails all 601 of the guest's own retries; its
  single host-turn budget exit was the STR decode (`DecDCTvlc` `0x800ED574`, 610,746 cycles), which
  belongs to the NATIVE owner `x4::stream_startup::run` (`psx::cpu::ResumableGuestCall`, return
  `0x80018AA0`), not to a task turn. The task-level budget path is NOT dead: from presented field ~1,010
  task `0x8001DAF8` resumes 306 times in a row, reproducibly (3/3), and the product then dies
  deterministically at presented field ~2,848 (exit 139, SysEnq element `0x8013BBF8` VERIFIER word
  `0x0313AE20`, `docs/issues/0036`), with every sampled present from 100 to 2,830 at 0.00% non-black. No
  window satisfies the gate; it stays out of `tools/verify.py`. It also still runs a STALE binary — its
  default `--product` is `build/bin/megamanx4_port`, a different tree from the gate's `build/ci`.