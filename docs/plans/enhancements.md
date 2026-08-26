# The three enhancements — design of record, at the level the evidence supports and no further

**MEASURED vs ASSUMED, up front, because at bootstrap time almost everything here is assumed.** What is
measured about this game is a short list: the executable's identity and PS-EXE header, `SYSTEM.CNF`, the
disc's file inventory, that there are no code overlays, the two InitPAD buffers, and that per-character
data is split per file. Nothing about the player object, the camera, the projection site, the game-side
input route or the game's timers has been measured. **Every design statement below that is not tagged MEASURED is a design intention, and
several of them stop mid-sentence on purpose.** A plan that names a fake offset is worse than a plan that
says "unknown".

USER decision, 2026-08-12, verbatim, which is why this file exists at all:

> "Mega Man doesn't need native producers or lerp or native depth, it's already 60fps. It just needs
> widescreen patches (still hard work) and loading removals (again hard work). And I want to add co-op
> to it, drop-in, if I'm playing with X for example then second player can spawn as Zero."

USER clarification, 2026-08-22: X4 (`SLUS_005.61`) is one of the already-60fps titles that needs
widescreen only; it does not need lerp or anything whose only purpose is to support lerp. `X4Runtime`
now declares the shared widescreen-only capability profile. The framework omits the Native and 60fps
player controls, refuses to activate `PSXPORT_FPS60`/persisted `fps60=1`, and resolves an unsupported
diagnostic renderer without selecting an empty native-producer path. This policy does not alter or cap
the retail game's own 60 Hz cadence.

All three are the framework's `pc_enh` class with `affect: full` — they deliberately change canon guest
state — and all three are read through the single chokepoint `x4::enh()`
(`game/core/enhancements.{h,cpp}`), which force-suppresses them under `PSXPORT_ORACLE`, `PSXPORT_SBS` and
a non-empty `PSXPORT_SBS_MODE`. That is what keeps byte-compares enhancement-free *by construction*
rather than by per-call-site discipline. Knob table: `docs/config.md`. Ledger and gate:
`docs/behavior-map.md` + `tools/behavior.py check`.

---

## 1. Widescreen

**What it changes.** A wider-than-4:3 field of view — genuinely more of the world visible, not a
stretched present.

**Follow the framework's model, do not reinvent it.** psxport already has an `aspect` selector
(0 = Vanilla 4:3, 1 = 16:9, 2 = 21:9, 3 = Auto) and it is a real FOV widening: the engine shifts the
projection centre OFX to `nw/2` rather than scaling the framebuffer, and it is forced OFF under
`PSXPORT_ORACLE` and in the SBS legs. Read that first.

**THE SINGLE MOST IMPORTANT SENTENCE IN THIS FILE — the reclassification.** psxport's widescreen is
`affect: none`: a host-side, read-only overlay driven by a NATIVE renderer, and the standing framework
rule is that the picture comes from GAME STATE, never from what the GTE produced. **X4 has no native
renderer** — the guest draws, on the substrate — so a widescreen change here has nowhere to live except
the **guest's own projection setup**. That makes it `affect: full`, which is why it is a suppressed
`pc_enh` and not a render overlay. Misfiling it as `affect: none` would skip both the suppression
requirement and `behavior.py check`'s only real assertion.

**Measured projection contract.** `tools/verify_projection.py --check` scans all 294,400 loaded retail
words and finds exactly six writes to GTE CR24/25/26, all inside `InitGeom`, `SetGeomOffset`, and
`SetGeomScreen`; those routines are each called exactly once from `func_8001213C`. The final state is
OFX=160, OFY=120, H=512. There is no later scene, camera, HUD, or inline raw writer in the resident
executable, so X4 has one global projection setup rather than several pass-specific ones.

**Implemented contract, pending integrated pixels:** X4's required faithful picture path is `gte`.
The typed framework candidate resolves the explicit 16:9 request from the retail 320x240 geometry to
width 428, horizontal margin 54 and OFX 214; 4:3 is exact 320/160 identity. The title's per-Core
`WidescreenController` latches that plan at the measured SetGeomOffset, changes only OFX before the
untouched retail body, and changes only RECT.w after untouched SetDefDrawEnv. OFY=120 and H=512 remain
retail-owned. The host consumes the same latched plan for clipping/margin coverage/presentation; Psx,
ORACLE and SBS resolve 4:3. Do not replace any part with a stretch, forced-native path, or local
renderer exception.

Temporal camera/object capture, interpolated replay, native depth, and PC-native producers are not
requirements of X4 widescreen. X4 creates no temporal decorator and calls the recorded neutral
presenter; the title dependency gate rejects operational Fps60 regressions. Issue #12 stays
open only because framework landing/pin/no-temporal-link/real-disc verification remains.

**Suppression.** `x4::enh(x4::cv_widescreen)`; `PSXPORT_X4_WIDESCREEN`.

---

## 2. Loading removals — TWO JOBS, separated before either is estimated

Conflating these is the failure mode. Do not quote one "load time" number for both.

### Job A — raw I/O latency and the stock-path timing diagnosis

The retail front-end uses asynchronous ReadN/callback state, not a synchronous file shortcut. The
recorded framework pin advances CDC deadlines only through sparse executed-instruction ticks, so the
loader's yielded VSync fields starve time and cause its real 601-poll timeout after LBA224. The shared
field-aware emulated-time candidate fixes that clock owner and reaches the title screen on the stock
path. The optional fast-loading enhancement now deliberately takes a different route: it owns the two
measured title issuers and reads their table-bounded sectors synchronously, bypassing CDC deadlines and
deliberate I/O latency while retaining the generated title callbacks. The boot exe holds a
161-entry literal path table (138 ARC + 11 STR + 11 XA + the build's own EXE) at file offset `0xDED4E`,
and its 138 ARC names match the disc's 138 ARC files exactly in both directions — so the complete asset
manifest is already in the binary, which is a ready-made index if a prefetch design is ever wanted.

Caveat, stated because it is arithmetic and not a measurement: `PL00_U.ARC` is 796,672 B and only
~565 KB of RAM remains after `.text` + `.bss`, so `.ARC` files are presumably parsed or streamed in
pieces rather than loaded whole. **HYPOTHESIS.** `RE-04` confirms or kills it, and the answer changes what
"the load is fast" even means.

### Job B — remove only waits owned by the measured loading operations

RE-09 locates direct/archive issuers 0x80013890/0x80013AD8, their callbacks, wait predicates
0x80014C70/0x80014A90, loading-presentation wait 0x80013530, and archive consumer 0x80014780. The
synchronous issuer owner pumps that consumer after every ready callback—the producing handlers reject
seven outstanding records and retail drains once per main loop—then returns with the load state already
terminal. The wait predicates execute zero yield/draw iterations and 0x80013530 is omitted. No display
field is advanced or hidden and there is no presenter dependency.

This is a `pc_enh`, `affect: full` change, not a byte-exact acceleration. A real-disc run still must
verify complete destination bytes and the absence of presented loading frames. Other scripted fades
and frame-count timers remain open: a transition whose end triggers game state is not loading latency,
and must not be collapsed merely because it looks like a wait.

**Suppression.** `x4::enh(x4::cv_fastwait)`; `PSXPORT_X4_FASTWAIT`.

---

## 3. Drop-in co-op — and this design STOPS where the player-object layout stops

> "And I want to add co-op to it, drop-in, if I'm playing with X for example then second player can
> spawn as Zero."

**What it changes.** A second player joins mid-play and controls the other hunter.

**The engine assumptions it breaks** — expected, not verified: **one player struct, one camera, one input
route**. A single-player engine typically holds the player as a singleton (a fixed address or slot 0 of
an object table), points the camera at it unconditionally, and routes pad slot 0 into it directly. Each
of those is a separate piece of RE and a separate design decision.

**So the RE target is the PLAYER-OBJECT SYSTEM (`RE-07`), not the renderer.** This is the step the whole
port turns on, and it is the most invasive `pc_enh` in the workspace.

**THE ONE PIECE OF GOOD NEWS THAT IS MEASURED.** The framework already reads two pad slots —
`external/psxport/runtime/recomp/pad_input.cpp:550`:

```cpp
uint32_t bufs[2] = { c->cfg->padSlot0Buf, c->cfg->padSlot1Buf };
```

RE-06 has now landed those fixed buffers from the retail InitPAD call: slot 0 `0x80166D68`, slot 1
`0x8012F46C`, both capacity `0x22`. So co-op's **host input destination exists**. **Do not read a
working second pad as co-op being close** — the game-side route and player-object half are supported by
nothing.

**A LEAD, not a finding.** Per-character data is already split per file on the disc: `PL00_U.ARC` /
`PL01_U.ARC` / `PL02_U.ARC` (796,672 / 741,376 / 796,672 B) for the three playable characters, plus `_X`
and `_Z` variants of the per-stage collision and stage archives (`COL0B_0X` vs `COL0B_0Z`, `ST0B_0X` vs
`ST0B_0Z`). That is a hint the engine already parameterises by character, which would make "spawn the
other hunter" cheaper than it sounds. **It was not verified in code, and it is not evidence that two
player objects can coexist** — per-character *data* files are equally consistent with an engine that
loads exactly one character's set per session, which the `_X`/`_Z` STAGE variants arguably suggest.

### THE DESIGN STOPS HERE, AND SAYS SO

Everything past this point depends on the player-object layout, which **was unknown when this
plan was written**. It stopped on purpose rather than inventing an offset. RE-07 has now
measured it — `docs/re-player-object.md` (2026-08-24) carries the per-item evidence; its
answers to this plan's questions:

1. Singleton or table? BOTH: the player is a dedicated singleton (`g_Player = 0x801418C8`,
   0xE4 bytes) OUTSIDE the general main-object pool (48×0x9C @ `0x8013BED0`), with a twin
   PlayerObj (`g_Entity = 0x80175D58`) used for the enemy/boss side.
2. Camera owner? Three layer structs @ `0x801419B0` (stride 0x54); layer scroll x/y at
   +0xA/+0xE; a mode-dispatched follow (table `0x800F3134`, driver `func_80027850`) reads the
   player's position halves directly — hardcoded target, not a target pointer. A second camera
   would be a second layer-array consumer, not a free parameter.
3. Input route? Retail decodes pad 1 AND pad 2 every frame in `func_80012328`
   (P2 held/prev/edge at `0x80166D50/D52/D54`) but NOTHING consumes the P2 state. The route
   into gameplay reads pad-1 products only; whether it can be parameterised per player object
   is exactly the unmeasured part.
4. Spawn path? `func_80035240` builds the player from the engine character byte
   (`0x80172203`) + stage scratch at stage load. That it can run MID-STAGE (a drop-in join)
   is NOT measured — callers attributed so far are stage-load-side only.
5. Per-character state split? Partially measured: character selects the anim-table pointer at
   struct+0x30 from one of two tables (X `0x80119DF0` / Zero `0x8011AFF0`); which OTHER state
   lives in globals vs struct is still open, and remains where a second player breaks first.

So the layout half of the design resumes from measurement, while the co-op-specific unknowns —
mid-stage spawn, second-camera ownership, P2 routing, and what evidence proves co-op correct
(still ❓ open) — are unchanged by RE-07 and stay gating below.

### The verification consequence, stated explicitly rather than glossed

**With co-op ON the run is not byte-comparable to the oracle by design.** A clean SBS compare with co-op
ON means *the suppression fired*, not that co-op is correct — that is a third fake-green trap on top of
the two the framework's porting doc already names. Therefore:

- the SBS gate runs with **all enhancements OFF**, and that is what `x4::enh()` guarantees;
- **the co-op path needs its own evidence, and what that evidence is, is an OPEN QUESTION (❓).** It is
  not a differential byte-compare, because there is nothing to compare against. It is probably some
  combination of "single-player play with co-op compiled in but off is still byte-exact" (which the SBS
  gate gives for free) plus a behavioural assertion on the co-op path that nobody has designed yet.
  **This file will not invent that gate.** Design it when RE-07 has made it designable, and record it
  here and in `docs/behavior-map.md` when it exists.

**Suppression.** `x4::enh(x4::cv_coop)`; `PSXPORT_X4_COOP`.
