---
id: 28
title: After both STR movies the guest parks in game state 1 / sub-state 2 on an unfinished CD read
status: open
symptom: Post-movie fields present a flat clear colour and the retail task never ends a turn
tags: frame-loop,cd,vsync,widescreen
created: 2026-09-27
updated: 2026-09-27
---

## What was measured

With the libetc VSync entry owned end-to-end (`game/core/vsync_sync.h`), one headless unpaced
13,400-field run and one 60,000-field run, both `PSXPORT_VK_HEADLESS=1 PSXPORT_NOAUDIO=1
PSXPORT_NOPACE=1`:

- both movies complete: `0x80018E50` entered at display field **974** (`ra=0x800184C4`, entry-one
  driver) and field **13,153** (`ra=0x800181DC`, indexed driver), `movieCleanup.completedFields()` 7/7
  at both, `cd.stream_active` 1 before each;
- `cd.stream_active` reaches **0** between field 13,000 and 13,500, and the guest's own field counter
  `0x80141BD8` leaves its movie-frozen 7 and reaches 351;
- the display-mode init's own `GP1(08)` 15-bit 320x240 switch and its `VSync(-1)` at `0x800E68F4`
  are both passed, and `render_width` **428** is the steady state.

## RETIRED: the DMA-chain reading (this is the issue's main correction)

The previous revision of this issue, and the comment above `kMaxTurnFields` in
`game/core/bios_threads.cpp`, both asserted that the guest "waits at `0x80021858`, which writes DPCR
(`0x1F801064`) and walks a 6,144-byte DMA chain at `0x80173CA0` polling the guest flag byte
`0x801721D7` for a DMA completion the host never raises". **Every element of that is wrong**, and the
errors are the kind that send a reader looking for hardware that does not exist:

1. **`0x1F801064` is not DPCR, and is not a peripheral at all.** `0x80021858` builds its walk cursor
   with `lui $1,0x1f80`, which is **0x1F800000**, and then `sw`/`lw 0x64($1)`. So the cell is
   **scratchpad + 0x64 = 0x1F800064** — ordinary 1 KiB scratchpad RAM. `0x1F801064` would be the result
   of misreading `0x1F800000` as `0x1F801000`.
2. **There is no DMA chain.** The matching decomp's `config/symbols.us.txt` names the function
   `update_misc_objects = 0x80021858` and the array `misc_objects = 0x80173CA0; // size:0x1800`.
   0x1800 = 6144 bytes = **96 records of 0x60 bytes**, which is exactly the stride the loop adds
   (`addiu $2,$2,0x60`) and exactly the bound it compares against (0x80173CA0 + 0x1800 = 0x801754A0).
   Each active record is dispatched by `jalr` through the handler table at `0x800F2980`. It is the
   game's per-frame misc-object update pass.
3. **`0x801721D7` is a guest struct field, not a completion flag.** The decomp names the struct
   `engine_obj = 0x801721C0; // size:0x64` and the field `engine_obj_17 = 0x801721D7`, i.e. **offset
   0x17 of an engine object**. A full scan of the text image finds **four** store sites
   (0x800311B8, 0x80035B20, 0x80035BCC, 0x800C03F8) and **one** load site (0x80021898). Every store is
   ordinary guest code; **no product code writes that address**, and there is no framework path that
   could. So the host is not the writer and is not failing to write.

The `[irq] pending I_STAT&I_MASK=0x004` line stays unadopted: bit 2 is the CD-controller edge, it
appears ~1 s into the run while the movies still work, and nothing here measures a difference between
the movie phase and the post-movie phase that would make it the blocker. `[producers] run-end: OtAttr
spans recorded 0` and `[render-noise:warn] ... the render-region mask is EMPTY` remain unusable in
both directions, for the reasons already recorded (issue 0019's owners; `GameConfig::packetPool*` /
`otRegion*` are deliberately zero on this title).

## The wall, as measured now

**The guest is not stalled; it is parked, and it is parked in its own state machine.** Live reads
through the product's own control channel (`PSXPORT_DEBUG_SERVER`), presents 15,006 / 20,023 / 23,218
of a 24,000-present run:

| guest cell | name | value at all three samples |
|---|---|---|
| `0x80173C70` | `game_info` (decomp `game_info = 0x80173C70; // size:0x10`) | `0x00000201` — game state **1**, sub-state **2** |
| `0x80173C84` | the handshake byte sub-state 2 waits on | **1** |
| `0x801721C0` | `engine_obj` (size 0x64) | all zero except `engine_obj_0C` = `0x0E` |
| `0x80173CA0` | `misc_objects` (96 × 0x60) | **1 of 96** records has any of bytes 0/1/3 non-zero, and that one is `0xFF,0xFF,0x00` |
| `0x80141BD4` | `music_stream::kMusicActive` | 2 |
| `0x80139530` | `music_stream::kMachineState` | 6 |
| classified display list | `dbg_server`'s `scene` | `poly=1 rect=0 line=0 fill=0 vramcopy=0 upload=0 env=1` |

Every one of those is **byte-identical across 8,200 presented frames**. That is what "parked" means,
and it is why raising the horizon does not help — a 60,000-present run is not reachable anyway
(below).

The guest's state machine, read from the image:

- `0x8001DAF8` (the task) dispatches `table_0x800F21B0[game_info.byte0]` each iteration, and calls
  `0x800127C8(1)` — which issues `CD_cw(0x1B, 0x7F, 0xFF000000)` at `0x800EDDBC`, a **CD read of
  0x7F sectors** — once per iteration (`PSXPORT_DEBUG=cdcw` shows
  `pc=800EDDBC ra=800127EC` writing the CD controller registers).
- game state 1 is `0x8001E708`, which dispatches sub-state `table_0x800F2294[game_info.byte1]`.
  Sub-state 2 is **`0x8001DDB0`**, and it returns immediately unless `[0x80173C84] == 2`:
  `0x8001DDE0 lbu $3,0x3C84($3)` / `0x8001DEDC bne $3,$2,0x8001DE0C`.
- `[0x80173C84]` is raised to 2 in exactly **one** place, `0x80016BB8`, and only if all three hold:
  the music state is 2 (`0x80016B84`), the status byte has bit 6 clear (`0x80016B94`), and
  **`CdControl(0x1B, 0, $16)` returns non-zero** (`0x80016BA4 jal 0x800E5D90` /
  `0x80016BAC beqz $2,0x80016BC4`). It is cleared to 0 only by the music-stop path at `0x80016F94`.

The CD path itself is **alive and streaming, not wedged**: 14,000 presents produce 129,513
`PSXPORT_DEBUG=cdcr` register accesses, `CdSync` (0x800E5D40) polls the status to 0x19, the data-ready
handler `0x800E7944` runs, and the CD IRQ register reports `0xE0`/`0xE1`. Four archive/direct requests
complete and then no further request is ever issued (requests 64/65/113/51, the same four the earlier
sessions measured).

**So the honest statement of the wall is: the host must complete the guest's `CD_cw(0x1B)` read
transaction, and the framework's synchronous CD model does not deliver the completion the engine's
streaming reader is waiting for.** That is a modelling gap with a named interface, not a flag to
raise. The proper fix is a native CD owner that models the streaming read's completion (the request
accepted, the data delivered, the ring/callback side advanced), and it belongs in
`x4::cd_controller` / the CD boundary — **not** in the frame driver, and **not** by writing
`0x80173C84` or any other guest state byte.

## A second, independent defect found while measuring this

**The guest's display-field clock runs at twice the presented cadence.** Measured with the control
channel's own `step`, so there is no sampling skew: 8 consecutive `step 1` calls each advanced
present `N -> N+1` and advanced the libetc VBlank counter `0x8011DC50` by **exactly 2**, 8/8 and 4/4 in
two separate runs. With `PSXPORT_DEBUG=x4-vsync`, a 200-present run emits exactly 200
`native field A -> A+1` lines, and the `before` values step 0, 2, 4, … 398 — so `deliverField` runs
once per present and the **second increment arrives from outside it**.

The only writer of `0x8011DC50` in the whole text image is `trapIntrVSync` (0x800E56FC,
`0x800E5728 sw $2,-0x23B0($1)` with `lui $2,0x8012`); the zeroing store is `startIntrVSync`
(0x800E56C8). The chain is not self-referential: class-0 slot `0x8011CB98` = `0x800DD7FC`
(`_SsTrapIntrVSync`), its saved previous handler `0x8011C944` = `0x800E56FC`, SS tick `0x8011C940` =
`0x800DD88C`, and the eight-slot callback table `0x8011DC30` is all zeros. So `trapIntrVSync` is
reached a second time per presented frame by the framework's own interrupt service:
`Timing::raiseVBlank` (framework `runtime/psx/core/timing.cpp`) sets `I_STAT` bit 0 every display field and
`Hle::irqPoll` delivers it whenever the guest has bit 0 unmasked **and** a chain element. The
framework's own comment on that function says a title whose vblank work the port already owns
natively "leaves VBlank masked" and "sees no behavior change at all". **X4 does not leave it masked**,
and `x4::vsync::deliverField` already delivers the guest's whole class-0 handler chain itself.

This is a **framework/title interaction, and the two candidate fixes are opposite**, so it is reported
rather than guessed at:
- *title-side*: `x4::vsync::deliverField` owns the field boundary, so it is the component that must
  decide the guest must not also receive a framework VBlank edge. It cannot simply clear I_MASK bit 0
  — that is a framework register and the guest's own interrupt-driven work may depend on the bit.
- *framework-side*: `Hle::irqPoll` cannot know that a title already delivers class 0, so the decision
  belongs to the title, expressed through a declared contract rather than a bare register poke.

**Not established**: that this doubling is the cause of the empty post-movie object list. It is a real
defect with a measured consequence (guest time runs 2× the presented cadence, and it is why
`kMaxTurnFields` reaches 512 display fields at present ~23,900 and aborts the product), but the
post-movie stall is measured to be a parked CD transaction, and the two have not been causally joined.

## The measure

`tools/probe_post_movie_motion.py` (new, this session) captures CONSECUTIVE presents in each leg's own
process and reports per-frame non-black counts, distinct-colour counts and the frame-to-frame
difference with denominators. It exists because the previous discriminator was wrong: the post-movie
clear colour is RGB(8,8,16), which is not (0,0,0), so a non-black count of 61.89% reads as "something
is on screen" for a picture that never changes.

Measured at presents 15,000..15,003, wide leg (1284x720) and narrow leg (960x720):

- every frame is **2 distinct colours**: `#080810` and `#000000`. There is no third colour and no
  scene.
- every consecutive pair **DIFFERS**: 2,394/924,480 pixels (0.259%) wide, 2,871/691,200 (0.415%) narrow,
  in a **798×3 band at y=717..719** (x from 162), with mean |delta| 10.67/255 and worst channel
  16/255. 5,031 black pixels on one frame alternate with 2,160 on the next.
- present 14,000 is **100% black, 1 colour**, on both legs.

So the earlier "byte-identical across four checkpoints" reading is **falsified**: the picture is not
frozen. What is true is stronger and different: the only thing that changes is a three-pixel band at
the bottom edge, alternating on a two-present period, while the rest of the frame is one flat colour.
**The guest does not animate a scene.** The two prims it submits per frame are a full-screen black
`GP0(0x60)` rectangle and a full-screen `GP0(0x28)` Gouraud triangle in RGB(8,8,16)
(`PSXPORT_PRIMDUMP=15000` → `scratch/logs/prims_f15000.csv`, 2 prims, `env=1`).

## The widescreen pair is still REFUSED, and that is now the correct answer

`external/psxport/tools/port/widescreen_pair.py`, 4:3 leg and 16:9 leg in their own processes,
`PSXPORT_PRESENT_SHOT_AT=15000..15003`, verbatim:

    scratch/motion/43_15000.png 960x720  vs  scratch/motion/169_15000.png 1284x720
      predicted offset for a pure widening : +162
      best translation                     :     5.32 at dx=+2
      next best translation                :     5.32
      worst of 341 offsets tried          :    10.86 at dx=+332
      stretch hypothesis                   :    11.98
      left  margin 162px wide          :   0.0% non-black, 1 colours, 161/161 repeated columns   <- NOT SCENE
      right margin 162px wide          :   0.0% non-black, 1 colours, 161/161 repeated columns   <- NOT SCENE
    REFUSED: a 1284-column capture with a 162-column margin leaves too few ordinary column pairs beside a join to say what this picture's column-to-column variation normally is, so a discontinuity could not be told from the scene's own texture. NOTHING WAS COMPARED at the joins.

The steady-state `render_width` from each log tail (the announcement prints on change only, so the last
line is the steady state). Both legs' logs are **deleted before the run** by
`tools/probe_post_movie_motion.py`, because `PSXPORT_LOG_FILE` appends and a previous run's change lines
otherwise survive into the tail — which produced a wrong 24-transition tail on this tool's first use
and is the same class of error the "mid-run sample is not the steady state" caveat warns about:

- 4:3 leg: one `[wide]` line in the whole run, `render_width=320` — 4:3 identity holds and does not move.
- 16:9 leg, six lines, `320 → 428 → 320 → 428 → 320 → 428`; **the last line is `render_width=428`**, and
  it is the run's last `[wide]` event. Every transition is 1:1 correlated, within 1–13 ms, with the
  **guest's own `GP1(08)` display-mode switch**:

      08:45:46.181  [wide] render_width=428
      08:45:46.224  [gpu]  display depth -> 24-BIT (GP1(08)=08000011, 320x240)
      08:45:46.233  [wide] render_width=320
      08:45:49.594  [gpu]  display depth -> 15-bit (GP1(08)=08000001, 320x240)
      08:45:49.595  [wide] render_width=428
      08:45:49.608  [gpu]  display depth -> 24-BIT (GP1(08)=08000011, 320x240)
      08:45:49.610  [wide] render_width=320
      08:46:22.410  [gpu]  display depth -> 15-bit (GP1(08)=08000001, 320x240)
      08:46:22.411  [wide] render_width=428        <- last event of the run

  So the plan is not a half-duty latch: it is re-latched from the guest's display mode, and the guest's
  last act in the run is to leave 24-bit mode, which is why the tail is 428. **Not determined**: what in
  `WidescreenController::presentationAspect` makes those two correlate. Its only per-field-varying
  inputs are `cd.stream_active` and `movieCleanup.pending()`, and neither was measured per field, so no
  mechanism is claimed here and `widescreen_controller.*` is left unedited.

## Falsifier

This closes when a post-movie present contains scene: more than a handful of distinct colours with a
centre band that is not one flat clear colour, and two consecutive post-movie presents that differ by
substantially more than a three-row edge band. Until then "a post-movie gameplay frame exists" is
false, and no widescreen claim about one may be made.

## What the seven widened cull owners (issue 0019) now have

Still **no product evidence — not a negative result, an absent measurement**, and this session
strengthens the reason. There is a measurable amount of prim traffic post-movie: `PSXPORT_DEBUG=pool`
reports 13–17 ordering-table nodes walked per present from present ~13,000 onward (never zero), and
`PSXPORT_PRIMDUMP` accounts for exactly 2 of them as geometry, with the rest resolving to terminators
or non-primitive nodes. So the cull owners are neither being handed a scene to reject nor being
proved correct on one: the guest has nothing to submit yet. Issue 0019 stays open with its hermetic
pinning and gains no product evidence from this session.
