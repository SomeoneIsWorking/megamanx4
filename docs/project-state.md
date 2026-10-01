# Project state

Factual capability coverage for the Mega Man X4 enhancement port. Epic intent lives in
`docs/project-goals.md`, ownership in `docs/codemap.md`, open defects and missing features in
`docs/issues/`.

| ID | Capability | State | Evidence or gap |
|---|---|---|---|
| S001 | USA executable and disc inputs are reproducibly identified and provisioned | verified | `tools/extract_exe.py` + `tools/resolve_disc.py` identify `SLUS_005.61`, SHA-1 `213733031136d095ca275d6957695aa25011cfa5`; no game bytes tracked |
| S002 | The authenticated resident image runs through the native/Lightrec gameplay product | partial | Boot, both STR movies and the archive loads complete through the shipping dispatcher, but a run still stops on a guest dispatch to the non-guest word `0x0113D7D0` from `kUpdateTasks` (`docs/issues/0028`, `0029`); translated-block and fallback counts unreported at the stop |
| S003 | Guest field service delivers retail timing, input, and audio work | partial | One field, class-0 dispatch, pad, SPU, snapshot and presentation commit per field; movie cleanup, BGM Setmode and the XA/BGM `CdSync` edges are owned; the later state 6/5/1 Setfilter/SeekL/ReadS/GetlocP chain and the memory-card callers are unproven |
| S004 | The native/Lightrec product boots and presents the retail front end through guest GTE rendering | partial | Front end, logo decode, title task `0x8001DAF8` and the wide plan at `render_width=428` are reached; the post-movie turn parks at game state 1 / sub-state 2 with an unfinished CD read, so no gameplay picture (S002), and guest sprite assembly is visibly wrong (`docs/issues/0026`) |
| S005 | Player-visible renderer and cadence choices match the title's actual capabilities | verified | Guest-GTE-only capability profile; the menu exposes no native-renderer or 60fps-interpolation control |
| S006 | Title-owned widescreen composes correct 16:9 title and gameplay pictures | partial | One global projection writer; 4:3 identity and OFX/width 214/428 proven in product. Title 2D quads do not consume OFX and the composition translates left (`docs/issues/0019`); the generic Aspect Ratio row does not drive the guest projection (`docs/issues/0024`); matched wide/4:3 gameplay margins are unverified |
| S007 | Measured loading operations complete without loading-only waits or presentation | partial | Direct/archive owners complete real-disc requests through their retail setup bodies with no guest VSync; destination-byte comparison and captured absence of loading presentation remain open, and unrelated scripted waits and fades are unclassified |
| S008 | A second player can join as the other hunter | missing | Two pads decode and the player/camera/spawn pillars are mapped (`docs/re-player-object.md`), but no second player object, P2 route, camera policy, mid-stage join, or co-op correctness gate exists |
| S009 | Representative gameplay is verified playable end to end | missing | No native/Lightrec session demonstrates and inspects representative stage gameplay with input, audio, saves, loading removal and widescreen together on any released host |
| S010 | Asset-free hosted verification builds and checks the real supported host product boundary | verified | `tools/verify.py` over the Linux x86_64 product, run in CI (`.github/workflows/ci.yml`); composition only. Windows, macOS and Android remain unsupported hosts, not green jobs |

## Current focus

S002: the guest's post-movie dispatch to the non-guest word `0x0113D7D0` — the remaining blocker to a
post-movie picture and therefore to gameplay evidence (S004, S009).